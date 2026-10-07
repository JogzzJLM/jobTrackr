"""Independent, persistent JobTrackr records; no spreadsheet dependency."""
import json
import os
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(os.getenv('DATA_DIR', 'data')).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / 'jobtrackr.sqlite3'
LOCK = threading.RLock()
DEFAULT_PROFILE = {'degree': 'Accounting and Finance Bachelors', 'university': '',
 'classification': '', 'graduation_year': None, 'experience_years': None, 'uk_citizen': None,
 'relocate': True, 'acca_status': 'Not confirmed', 'a_level_points': None, 'a_level_grades_confirmed': False,
 'gcse_maths': '', 'gcse_english': '', 'name': 'Finance graduate', 'award': '', 'work_experience': ''}

STATUSES = ('New', 'Saved', 'Applied', 'Assessment', 'Interview', 'Offer', 'Rejected', 'Withdrawn', 'Dismissed')

def now(): return datetime.now(timezone.utc).isoformat()
class ClosingConnection(sqlite3.Connection):
 def __exit__(self,*args):
  try:return super().__exit__(*args)
  finally:self.close()

def connect():
 c = sqlite3.connect(DB, timeout=30,factory=ClosingConnection); c.row_factory = sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL'); return c

def init():
 with connect() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'New', notes TEXT NOT NULL DEFAULT '', reminder TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, event TEXT NOT NULL, timestamp TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_retry REAL NOT NULL DEFAULT 0, delivered TEXT);
CREATE TABLE IF NOT EXISTS email_updates(id TEXT PRIMARY KEY, payload TEXT NOT NULL, resolved TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS application_events(id TEXT PRIMARY KEY, job_id TEXT NOT NULL, payload TEXT NOT NULL, occurred_at TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews(url TEXT PRIMARY KEY, payload TEXT NOT NULL);''')
  c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)', ('profile', json.dumps(DEFAULT_PROFILE)))

def setting(key, default=None):
 with connect() as c: row=c.execute('SELECT payload FROM settings WHERE key=?',(key,)).fetchone()
 return json.loads(row[0]) if row else default

def set_setting(key, value):
 with connect() as c: c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value)))

def jobs(include_duplicates=False):
 from .normalization import clean_company_display_name
 with connect() as c: rows=c.execute('SELECT * FROM jobs ORDER BY created DESC').fetchall()
 result=[{**json.loads(r['payload']), 'id':r['id'],'status':r['status'],'notes':r['notes'], 'reminder':r['reminder'], 'created':r['created'], 'updated':r['updated']} for r in rows]
 for job in result:job['company']=clean_company_display_name(job.get('company',''))
 if include_duplicates:return result
 from .normalization import collapse_finance_jobs
 return collapse_finance_jobs(result)

def application_from_email(email_id, company, title, link=''):
 """A confirmed application may be recorded even after its listing has closed."""
 import hashlib
 from urllib.parse import urlparse
 from .normalization import clean_company_display_name, canonical_url
 company=clean_company_display_name(company.strip());title=title.strip();link=link.strip()
 if company=='Unknown' or not title:raise ValueError('Enter the employer and role title')
 if link:
  parsed=urlparse(link)
  if parsed.scheme not in ('https','http') or not parsed.hostname:raise ValueError('Use a full application URL, or leave it blank')
  link=canonical_url(link)
 identity=link or 'email:'+email_id
 job_id=hashlib.sha256(identity.encode()).hexdigest()[:24]
 payload={'id':job_id,'company':company,'title':title,'link':link,'location':'',
  'source':'Application email','description':'Application recorded from an email confirmed by you.',
  'verification':{'state':'application_record','reason':'Application history; not a newly verified vacancy'},'category':''}
 with connect() as c:
  existing=c.execute('SELECT id FROM jobs WHERE url=?',(identity,)).fetchone()
  if existing:return existing['id']
  timestamp=now()
  c.execute('INSERT INTO jobs(id,url,payload,created,updated) VALUES(?,?,?,?,?)',(job_id,identity,json.dumps(payload),timestamp,timestamp))
  c.execute('INSERT INTO history(job_id,event,timestamp) VALUES(?,?,?)',(job_id,'Application recorded from email',timestamp))
 return job_id

def upsert(job):
 timestamp=now()
 with LOCK,connect() as c:
  existing=c.execute('SELECT id FROM jobs WHERE url=?',(job['link'],)).fetchone()
  if not existing:
   from .normalization import finance_same_listing
   existing=next((r for r in c.execute('SELECT id,payload FROM jobs') if finance_same_listing(job,json.loads(r['payload']))),None)
  if existing:
   record=c.execute('SELECT payload FROM jobs WHERE id=?',(existing['id'],)).fetchone();previous=json.loads(record['payload'])
   links=list(dict.fromkeys(previous.get('alternate_links',[])+job.get('alternate_links',[])+[previous.get('link',''),job.get('link','')]))
   if previous.get('route_type')=='Direct employer' and job.get('route_type')!='Direct employer':job={**previous,'alternate_links':links}
   else:job['alternate_links']=links
   job['id']=existing['id']; c.execute('UPDATE jobs SET payload=?,updated=? WHERE id=?',(json.dumps(job),timestamp,job['id'])); return False
  c.execute('INSERT INTO jobs(id,url,payload,created,updated) VALUES(?,?,?,?,?)',(job['id'],job['link'],json.dumps(job),timestamp,timestamp))
  c.execute('INSERT INTO history(job_id,event,timestamp) VALUES(?,?,?)',(job['id'],'Discovered and verified',timestamp))
 return True

def update_job(job_id, data, expected_status=None, stage_label=None):
 with connect() as c:
  row=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
  if not row: raise ValueError('Job not found')
  status=data.get('status',row['status'])
  if status not in STATUSES: raise ValueError('Invalid application status')
  notes=str(data.get('notes',row['notes']))[:20000]; reminder=str(data.get('reminder',row['reminder']))
  if reminder:
   from datetime import date
   date.fromisoformat(reminder)
  sql='UPDATE jobs SET status=?,notes=?,reminder=?,updated=? WHERE id=?'
  parameters=(status,notes,reminder,now(),job_id)
  if expected_status is not None:
   sql+=' AND status=?';parameters+=(expected_status,)
  if not c.execute(sql,parameters).rowcount:return False
  if status != row['status'] or stage_label:
   c.execute('INSERT INTO history(job_id,event,timestamp) VALUES(?,?,?)',(job_id,f'Status: {stage_label or status}',now()))

def history(job_id):
 with connect() as c:return [dict(r) for r in c.execute('SELECT id,event,timestamp FROM history WHERE job_id=? ORDER BY id DESC',(job_id,))]

def review(job, reason, state='needs_check'):
 with connect() as c:c.execute('INSERT OR REPLACE INTO reviews VALUES(?,?)',(job['link'],json.dumps({**job,'reason':reason,'review_state':state,'checked_at':now()})))

def reviews():
 with connect() as c:return [json.loads(r[0]) for r in c.execute('SELECT payload FROM reviews')]

def clear_review(url):
 with connect() as c:c.execute('DELETE FROM reviews WHERE url=?',(url,))

def load_json_safe(path, default):
 try:return json.loads(Path(path).read_text())
 except (OSError,ValueError):return default

def atomic_write_json(path, value):
 with LOCK:
  target=Path(path);tmp=target.with_suffix(target.suffix+'.tmp');tmp.write_text(json.dumps(value));tmp.replace(target)

init()
# Optional one-time private configuration; never returned to the website.
if os.getenv('JOBTRACKR_PROFILE_JSON'):
 configured=json.loads(os.environ['JOBTRACKR_PROFILE_JSON'])
 if not isinstance(configured,dict):raise ValueError('JOBTRACKR_PROFILE_JSON must be an object')
 profile=setting('profile',DEFAULT_PROFILE).copy()
 profile.update({k:v for k,v in configured.items() if k in DEFAULT_PROFILE})
 set_setting('profile',profile)


def application_events(job_id):
 with connect() as c:
  return [{'id':r['id'],**json.loads(r['payload']),'occurred_at':r['occurred_at']} for r in c.execute('SELECT * FROM application_events WHERE job_id=? ORDER BY occurred_at DESC,created DESC',(job_id,))]

def history_cursors():
 with connect() as c:return {r['job_id']:r['cursor'] for r in c.execute('SELECT job_id,MAX(id) AS cursor FROM history GROUP BY job_id')}
