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
 'relocate': True, 'acca_status': 'Not confirmed', 'a_level_points': None,
 'gcse_maths': '', 'gcse_english': '', 'name': 'Finance graduate', 'award': '', 'work_experience': ''}

STATUSES = ('New', 'Saved', 'Applied', 'Assessment', 'Interview', 'Offer', 'Rejected', 'Withdrawn', 'Dismissed')

def now(): return datetime.now(timezone.utc).isoformat()
def connect():
 c = sqlite3.connect(DB, timeout=30); c.row_factory = sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL'); return c

def init():
 with connect() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'New', notes TEXT NOT NULL DEFAULT '', reminder TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, event TEXT NOT NULL, timestamp TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_retry REAL NOT NULL DEFAULT 0, delivered TEXT);
CREATE TABLE IF NOT EXISTS email_updates(id TEXT PRIMARY KEY, payload TEXT NOT NULL, resolved TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews(url TEXT PRIMARY KEY, payload TEXT NOT NULL);''')
  c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)', ('profile', json.dumps(DEFAULT_PROFILE)))

def setting(key, default=None):
 with connect() as c: row=c.execute('SELECT payload FROM settings WHERE key=?',(key,)).fetchone()
 return json.loads(row[0]) if row else default

def set_setting(key, value):
 with connect() as c: c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value)))

def jobs():
 with connect() as c: rows=c.execute('SELECT * FROM jobs ORDER BY created DESC').fetchall()
 return [{**json.loads(r['payload']), 'id':r['id'],'status':r['status'],'notes':r['notes'], 'reminder':r['reminder'], 'created':r['created'], 'updated':r['updated']} for r in rows]

def upsert(job):
 timestamp=now()
 with connect() as c:
  existing=c.execute('SELECT id FROM jobs WHERE url=?',(job['link'],)).fetchone()
  if existing:
   job['id']=existing['id']; c.execute('UPDATE jobs SET payload=?,updated=? WHERE id=?',(json.dumps(job),timestamp,job['id'])); return False
  c.execute('INSERT INTO jobs(id,url,payload,created,updated) VALUES(?,?,?,?,?)',(job['id'],job['link'],json.dumps(job),timestamp,timestamp))
  c.execute('INSERT INTO history(job_id,event,timestamp) VALUES(?,?,?)',(job['id'],'Discovered and verified',timestamp))
 return True

def update_job(job_id, data):
 with connect() as c:
  row=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
  if not row: raise ValueError('Job not found')
  status=data.get('status',row['status'])
  if status not in STATUSES: raise ValueError('Invalid application status')
  notes=str(data.get('notes',row['notes']))[:20000]; reminder=str(data.get('reminder',row['reminder']))
  if reminder:
   from datetime import date
   date.fromisoformat(reminder)
  c.execute('UPDATE jobs SET status=?,notes=?,reminder=?,updated=? WHERE id=?',(status,notes,reminder,now(),job_id))
  event=f"Status: {status}" if status != row['status'] else 'Notes or reminder updated'
  c.execute('INSERT INTO history(job_id,event,timestamp) VALUES(?,?,?)',(job_id,event,now()))

def history(job_id):
 with connect() as c:return [dict(r) for r in c.execute('SELECT event,timestamp FROM history WHERE job_id=? ORDER BY id DESC',(job_id,))]

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
