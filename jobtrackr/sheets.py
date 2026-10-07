"""Optional private Google Sheet mirror. SQLite remains the source of truth."""
import hashlib
import json
import os
import requests
from . import store
APPLICATION_STAGES=('Applied','Assessment','Interview','Offer','Rejected','Withdrawn')
def edit_url():
 from urllib.parse import urlparse
 url=os.getenv('GOOGLE_SHEET_EDIT_URL','')
 return url if urlparse(url).scheme=='https' and urlparse(url).hostname=='docs.google.com' else ''
def snapshot():
 rows=[]
 for job in sorted(store.jobs(),key=lambda j:j['id']):
  stages=[]
  for event in reversed(store.history(job['id'])):
   stage=event['event'].removeprefix('Status: ')
   if stage in APPLICATION_STAGES and (not stages or stages[-1]!=stage):stages.append(stage)
  current=job.get('status','')
  if current in APPLICATION_STAGES and (not stages or stages[-1]!=current):stages.append(current)
  if not stages:continue
  if stages[0]!='Applied':stages.insert(0,'Applied')
  rows.append({'id':job['id'],'company':job.get('company',''),'title':job.get('title',''),
   'status':current,'stages':stages[:9]+[stages[-1]] if len(stages)>10 else stages})
 return rows
def sync():
 url=os.getenv('GOOGLE_SHEET_WEBHOOK_URL','');token=os.getenv('GOOGLE_SHEET_SYNC_TOKEN','')
 if not url or not token:
  store.set_setting('sheet_health',{'ok':False,'configured':False,'message':'Google Sheets not connected.'});return False
 rows=snapshot();fingerprint=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
 if fingerprint==store.setting('sheet_fingerprint'):return True
 try:
  response=requests.post(url,json={'token':token,'layout':'applications-v2','jobs':rows},timeout=30);response.raise_for_status();receipt=response.json()
  if receipt.get('ok') is not True or receipt.get('count')!=len(rows) or receipt.get('layout')!='applications-v2':raise ValueError('Sheet did not confirm all records')
  store.set_setting('sheet_fingerprint',fingerprint);store.set_setting('sheet_health',{'ok':True,'configured':True,'last_synced':store.now(),'message':'Applications Sheet up to date. Only recorded applications are included.'});return True
 except (requests.RequestException,ValueError):
  store.set_setting('sheet_health',{'ok':False,'configured':True,'message':'Sheet sync delayed; local records are safe. Retrying automatically.'});return False

def loop(stop):
 while not stop.is_set():
  sync();stop.wait(60)
