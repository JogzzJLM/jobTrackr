"""Durable ntfy outbox with deduplication and retries."""
import json
import os
import re
import time
import threading
import hashlib
import requests
from datetime import date, datetime
from . import store
LOCK=threading.RLock()

def topic():return os.getenv('NTFY_TOPIC') or 'applicationtrackr_alerts_har'
def base():return os.getenv('APP_BASE_URL','http://192.168.0.136:5001').rstrip('/')
def enqueue(event, title, message, url=None):
 payload={'title':title,'message':message,'url':url or base()}
 with store.connect() as c:c.execute('INSERT OR IGNORE INTO outbox(id,payload) VALUES(?,?)',(event,json.dumps(payload)))

def new_listing(job):
 enqueue('listing:'+job['id'],f"New finance role: {job['company']} - {job['title']}",
 f"{job['title']}\n{job['company']} | {job['location']}\nSalary: {job.get('salary') or 'Not published'}\nDeadline: {job.get('deadline') or 'Not published'}\nStudy support: {'Mentioned' if job.get('study_support') else 'Not confirmed'}\n"+'; '.join(job.get('reasons',[]))+('\nCheck before applying: '+'; '.join(job.get('requirements',[])) if job.get('requirements') else '')+f"\nVerified and saved to JobTrackr.\n{job['link']}",job['link'])

def flush():
 if os.getenv('NOTIFICATIONS_DISABLED')=='1':return
 with LOCK:
  with store.connect() as c: pending=c.execute("SELECT * FROM outbox WHERE delivered IS NULL AND id NOT LIKE 'reminder:%' AND next_retry<=? ORDER BY rowid LIMIT 10",(time.time(),)).fetchall()
  for item in pending:
   payload=json.loads(item['payload'])
   try:
    target=topic()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',target):raise ValueError('Invalid ntfy topic')
    headers={'Title':payload['title'].encode('ascii','ignore').decode()[:180], 'Click':payload['url'], 'Tags':'briefcase', 'Priority':'3'}
    token=os.getenv('NTFY_TOKEN','')
    if token:headers['Authorization']='Bearer '+token
    r=requests.post(os.getenv('NTFY_BASE_URL','https://ntfy.sh').rstrip('/')+'/'+target,headers=headers,data=payload['message'].encode(),timeout=10)
    r.raise_for_status();receipt=r.json()
    if not receipt.get('id') or receipt.get('event')!='message':raise ValueError('No notification receipt')
    with store.connect() as c:c.execute('UPDATE outbox SET delivered=? WHERE id=?',(store.now(),item['id']))
    store.set_setting('notification_health',{'ok':True,'last_sent':store.now(),'receipt':receipt['id'],'topic':target})
   except (requests.RequestException,ValueError):
    attempts=item['attempts']+1
    with store.connect() as c:c.execute('UPDATE outbox SET attempts=?,next_retry=? WHERE id=?',(attempts,time.time()+min(3600,60*2**min(attempts,6)),item['id']))
    store.set_setting('notification_health',{'ok':False,'error':'Publish failed; queued for retry','topic':topic(),'last_attempt':store.now()})

def scheduled():
 # Closing-date alerts use verified listings, never old personal reminders.
 from zoneinfo import ZoneInfo
 local=datetime.now(ZoneInfo('Europe/London'));today=local.date().isoformat()
 items=store.jobs()
 for job in items:
  deadline=job.get('deadline','')[:10]
  try:days=(date.fromisoformat(deadline)-local.date()).days
  except ValueError:continue
  if days in (1,3) and job['status'] in ('New','Saved') and job.get('verification',{}).get('state')=='verified':
   enqueue(f"deadline:{job['id']}:{days}:{deadline}",f'Job closes in {days} day(s)',f"{job['company']} — {job['title']}\nCloses {deadline}\n{job['link']}",job['link'])
 if local.hour>=18:
  day='daily:'+today
  recent=[j for j in items if j['created'][:10]==today and j.get('verification',{}).get('state')=='verified' and j['status'] not in ('Dismissed','Rejected','Withdrawn')]
  if recent:
   enqueue(day,'JobTrackr daily summary',f"{len(recent)} verified finance opportunities found today.\n"+'\n'.join(f"{j['company']}: {j['title']}" for j in recent[:6])+f"\n{base()}")
 flush()
