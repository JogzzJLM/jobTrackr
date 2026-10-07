"""Optional private Google Sheet mirror. SQLite remains the source of truth."""
import hashlib
import json
import os
import requests
from . import store
APPLICATION_STAGES=('Applied','Assessment','Interview','Offer','Rejected','Withdrawn')
def edit_url():
 from urllib.parse import urlparse
 url=store.setting('sheet_health',{}).get('sheet_url') or os.getenv('GOOGLE_SHEET_EDIT_URL','')
 return url if urlparse(url).scheme=='https' and urlparse(url).hostname=='docs.google.com' else ''
def snapshot():
 rows=[]
 saved=store.setting('sheet_stages',{})
 for job in sorted(store.jobs(),key=lambda j:j['id']):
  stages=[]
  for event in reversed(store.history(job['id'])):
   stage=event['event'].removeprefix('Status: ')
   if stage in APPLICATION_STAGES and (not stages or stages[-1]!=stage):stages.append(stage)
  if job['id'] in saved:stages=list(saved[job['id']])
  current=job.get('status','')
  if current in APPLICATION_STAGES and (not stages or canonical_stage(stages[-1])!=current):stages.append(current)
  if not stages:continue
  if stages[0]!='Applied':stages.insert(0,'Applied')
  rows.append({'id':job['id'],'company':job.get('company',''),'title':job.get('title',''),
   'status':current,'stages':stages[:9]+[stages[-1]] if len(stages)>10 else stages})
 return rows
def canonical_stage(value):
 text=value.lower().strip()
 if 'reject' in text or 'unsuccessful' in text:return 'Rejected'
 if 'withdraw' in text:return 'Withdrawn'
 if 'offer' in text or 'secured' in text:return 'Offer'
 if 'interview' in text or 'assessment centre' in text:return 'Interview'
 if 'assessment' in text or text in ('oa','online test') or 'test' in text:return 'Assessment'
 if text in ('applied','application submitted','application received'):return 'Applied'
 return ''

def import_applications(rows):
 from .normalization import normalize_company, normalize_role
 jobs=store.jobs();saved={};flow=[]
 for row in rows:
  if not isinstance(row,dict):continue
  company=str(row.get('company','')).strip();title=str(row.get('title','')).strip()
  stages=[str(stage).strip()[:150] for stage in row.get('stages',[])[:10] if str(stage).strip()]
  if not company or not title or not stages:continue
  job=next((j for j in jobs if row.get('id') and j['id']==row['id']),None)
  if not job:
   matches=[j for j in jobs if normalize_company(j.get('company',''))==normalize_company(company) and normalize_role(j.get('title',''))==normalize_role(title)]
   if len(matches)==1:job=matches[0]
  if not job:
   identity='sheet:'+normalize_company(company)+':'+normalize_role(title)
   job_id=store.application_from_email(identity,company,title);job=next(j for j in store.jobs() if j['id']==job_id)
  job_id=job['id'];current=job['status']
  if company!=job.get('company') or title!=job.get('title'):
   with store.connect() as c:
    record=c.execute('SELECT payload FROM jobs WHERE id=?',(job_id,)).fetchone()
    payload=json.loads(record['payload']);payload.update({'company':company,'title':title})
    c.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),job_id))
  stage=next((canonical_stage(s) for s in reversed(stages) if canonical_stage(s)), 'Applied')
  if current!=stage:store.update_job(job_id,{'status':stage})
  saved[job_id]=stages;flow.append({**row,'id':job_id,'stages':stages})
 store.set_setting('sheet_stages',saved);store.set_setting('sheet_rows',flow)

def sync():
 url=os.getenv('GOOGLE_SHEET_WEBHOOK_URL','');token=os.getenv('GOOGLE_SHEET_SYNC_TOKEN','')
 if not url or not token:
  store.set_setting('sheet_health',{'ok':False,'configured':False,'message':'Google Sheets not connected.'});return False
 rows=snapshot();fingerprint=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
 try:
  response=requests.post(url,json={'token':token,'layout':'applications-v3','jobs':rows,'baseline':store.setting('sheet_sent_rows',rows)},timeout=30);response.raise_for_status();receipt=response.json()
  if receipt.get('ok') is not True or receipt.get('count')!=len(rows) or receipt.get('layout')!='applications-v3' or not isinstance(receipt.get('applications'),list):raise ValueError('Sheet did not confirm all records')
  import_applications(receipt['applications'])
  store.set_setting('sheet_sent_rows',snapshot())
  store.set_setting('sheet_fingerprint',fingerprint);store.set_setting('sheet_health',{'ok':True,'configured':True,'last_synced':store.now(),'sheet_url':receipt.get('sheet_url',edit_url()),'message':'Applications Sheet up to date. Only recorded applications are included.'});return True
 except (requests.RequestException,ValueError):
  store.set_setting('sheet_health',{'ok':False,'configured':True,'message':'Sheet sync delayed; local records are safe. Retrying automatically.'});return False

def loop(stop):
 while not stop.is_set():
  sync();stop.wait(60)
