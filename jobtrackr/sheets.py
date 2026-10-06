"""Optional private Google Sheet mirror. SQLite remains the source of truth."""
import hashlib
import json
import os
import requests
from . import store
FIELDS=('id','company','title','location','link','status','notes','reminder','deadline','source')
def edit_url():
 from urllib.parse import urlparse
 url=os.getenv('GOOGLE_SHEET_EDIT_URL','')
 return url if urlparse(url).scheme=='https' and urlparse(url).hostname=='docs.google.com' else ''
def snapshot():
 # Scanner timestamps are deliberately excluded: rechecking a page is not a sheet edit.
 return [{k:j.get(k,'') for k in FIELDS} for j in sorted(store.jobs(),key=lambda j:j['id'])]
def sync():
 url=os.getenv('GOOGLE_SHEET_WEBHOOK_URL','');token=os.getenv('GOOGLE_SHEET_SYNC_TOKEN','')
 if not url or not token:
  store.set_setting('sheet_health',{'ok':False,'configured':False,'message':'Google Sheets not connected.'});return False
 rows=snapshot();fingerprint=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
 if fingerprint==store.setting('sheet_fingerprint'):return True
 try:
  response=requests.post(url,json={'token':token,'jobs':rows},timeout=30);response.raise_for_status();receipt=response.json()
  if receipt.get('ok') is not True or receipt.get('count')!=len(rows):raise ValueError('Sheet did not confirm all records')
  store.set_setting('sheet_fingerprint',fingerprint);store.set_setting('sheet_health',{'ok':True,'configured':True,'last_synced':store.now(),'message':'Google Sheet mirror up to date. Application changes are saved here.'});return True
 except (requests.RequestException,ValueError):
  store.set_setting('sheet_health',{'ok':False,'configured':True,'message':'Sheet sync delayed; local records are safe. Retrying automatically.'});return False

def loop(stop):
 while not stop.is_set():
  sync();stop.wait(60)
