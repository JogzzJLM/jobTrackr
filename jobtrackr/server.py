import csv
import io
import json
import os
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from . import store, discovery, alerts, mail, sheets, flow
from .eligibility import evaluate, displayable
from .verifier import verify_listing
from .normalization import normalize_url, canonical_url
import hashlib

ROOT=Path(__file__).parent/'assets'
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,value,status=200,mime='application/json; charset=utf-8'):
  body=value if isinstance(value,bytes) else (json.dumps(value) if 'json' in mime else value).encode()
  self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  path=urlparse(self.path).path
  if path in ('/','/jobs','/applications','/saved','/settings','/status','/closed'):
   return self.reply((ROOT/'index.html').read_bytes(),mime='text/html; charset=utf-8')
  if path in ('/assets/style.css','/assets/app.js'):
   return self.reply((ROOT/path.split('/')[-1]).read_bytes(),mime='text/css; charset=utf-8' if path.endswith('.css') else 'text/javascript; charset=utf-8')
  if path=='/api/state':
   data={'jobs':store.jobs(),'scan':store.setting('scan',{}),'sources':store.setting('sources',{}),'notifications':store.setting('notification_health',{}),'mail':store.setting('mail_health',{'connected':False,'message':'Not connected'}),'email_updates':mail.updates(),'topic':alerts.topic(),'statuses':[s for s in store.STATUSES if s!='Saved'],'scan_interval':discovery.SCAN_INTERVAL,'sheet_url':sheets.edit_url(),'sheets':store.setting('sheet_health',{})}
   with store.connect() as c:data['pending_notifications']=c.execute('SELECT COUNT(*) FROM outbox WHERE delivered IS NULL').fetchone()[0]
   return self.reply(data)
  if path=='/sankey-embed':return self.reply(flow.html(),mime='text/html; charset=utf-8')
  if path=='/assets/plotly.js':
   from plotly.offline import get_plotlyjs
   return self.reply(get_plotlyjs(),mime='text/javascript; charset=utf-8')
  if path=='/api/health':return self.reply({'ok':True,'version':'finance-graduate-v1','scan':store.setting('scan',{})})
  if path.startswith('/api/history/'):
   return self.reply(store.history(path.rsplit('/',1)[-1]))
  if path=='/api/export':
   output=io.StringIO();writer=csv.DictWriter(output,fieldnames=['company','title','location','link','status','notes','reminder','deadline','source','created','updated'],extrasaction='ignore');writer.writeheader();writer.writerows(store.jobs())
   return self.reply(output.getvalue(),mime='text/csv; charset=utf-8')
  self.reply({'error':'Not found'},404)
 def do_POST(self):
  origin=self.headers.get('Origin')
  if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.reply({'error':'Cross-site request blocked'},403)
  try:
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<=100000:return self.reply({'error':'Invalid request size'},400)
   data=json.loads(self.rfile.read(size));path=urlparse(self.path).path
   if path=='/api/job':store.update_job(str(data.get('id','')),data)
   elif path=='/api/email/resolve':
    if data.get('ignore'):
     with store.connect() as c:c.execute('UPDATE email_updates SET resolved=? WHERE id=?',('ignored',str(data.get('id',''))))
    else:mail.apply_update(str(data.get('id','')),str(data.get('job_id','')),str(data.get('status','')))
   elif path=='/api/rescan':threading.Thread(target=discovery.scan,daemon=True).start()
   elif path=='/api/test-notification':
    import uuid
    alerts.enqueue('test:'+str(uuid.uuid4()),'JobTrackr notifications working','This is a test. Future alerts include the role, company, location, deadline, study support and application link.');alerts.flush()
    return self.reply({'ok':store.setting('notification_health',{}).get('ok',False),'notification':store.setting('notification_health',{})})
   elif path=='/api/manual':
    url=canonical_url(str(data.get('link','')));parsed=urlparse(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname:raise ValueError('Enter a full application webpage URL')
    if parsed.hostname in ('localhost','127.0.0.1','::1') or not '.' in parsed.hostname:raise ValueError('Use a public job listing URL')
    import ipaddress
    try:
     if not ipaddress.ip_address(parsed.hostname).is_global:raise ValueError('Use a public job listing URL')
    except ValueError as e:
     if str(e)=='Use a public job listing URL':raise
    job=discovery.candidate(str(data.get('company','')),str(data.get('title','')),str(data.get('location','')),url,'Added manually',str(data.get('description','')))
    job,check=discovery.enrich(job,force=True);decision=evaluate(job)
    if check['state']!='verified' or not displayable(decision):
     store.review(job,'; '.join(decision['requirements']) or check.get('reason','Cannot verify'),decision['state'] if decision['state']!='eligible' else check['state'])
     return self.reply({'ok':True,'review':True,'message':'Listing could not be confirmed as suitable, so it has not been added to Jobs.'})
    job.update(decision);job['id']=hashlib.sha256(job['link'].encode()).hexdigest()[:24]
    if store.upsert(job):alerts.new_listing(job)
    alerts.flush()
   else:return self.reply({'error':'Not found'},404)
   return self.reply({'ok':True})
  except (ValueError,TypeError,KeyError) as e:return self.reply({'error':str(e)},400)
  except Exception:return self.reply({'error':'Could not save. Your existing records remain unchanged.'},500)

def main():
 stop=threading.Event();server=ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','5001'))),Handler)
 if os.getenv('DISABLE_SCHEDULER')!='1':
  threading.Thread(target=discovery.loop,args=(stop,),daemon=True).start()
  threading.Thread(target=mail.loop,args=(stop,),daemon=True).start()
  threading.Thread(target=sheets.loop,args=(stop,),daemon=True).start()
 print('JobTrackr finance graduate dashboard is ready',flush=True)
 try:server.serve_forever()
 finally:stop.set();server.server_close()
