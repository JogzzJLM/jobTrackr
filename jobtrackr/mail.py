"""Opt-in mailbox listener with job-specific matching and uncertain-message review."""
import email
import hashlib
import imaplib
import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from . import store, alerts
from .verifier import plain
from .normalization import normalize_url, normalize_company, normalize_role, clean_company_display_name, extract_ats_post_id, finance_same_listing
from email.utils import parseaddr
from . import events
LOCK=threading.Lock()
APPLICATION_STAGES=('Applied','Assessment','Interview','Offer','Rejected','Withdrawn')
GENERIC_SENDERS={'gmail','googlemail','outlook','hotmail','yahoo','workday','myworkday','myworkdayjobs','greenhouse','greenhouse-mail','lever','smartrecruiters','icims','tal','successfactors','reed','indeed','noreply','notifications'}

def employer_from_email(subject, sender, body):
 # Forwarded messages and ATS mail must not be named after the forwarding service.
 for pattern in (r'(?m)^\s*([A-Z][A-Za-z0-9&.\x27 -]{2,55}?)\s+(?:Talent Acquisition|Recruitment|Early Careers) Team\b',
                 r'\b(?:your application|applying)\s+(?:to|with|at)\s+([A-Z][A-Za-z0-9&.\x27 -]{2,55}?)(?=[.!\n]|$)'):
  found=re.search(pattern,body)
  if found:return clean_company_display_name(found.group(1).strip(' .,|-'))
 forwarded=re.search(r'(?im)^From:\s*(.+)$',body)
 address=parseaddr(forwarded.group(1) if forwarded else sender)[1]
 host=address.partition('@')[2].lower()
 labels=[part for part in host.split('.') if part not in ('www','mail','email','careers','recruitment','jobs')]
 if labels and labels[0] not in GENERIC_SENDERS:
  return clean_company_display_name(labels[0])
 found=re.search(r'^(?:Re:|Fwd:|Fw:)?\s*(.+?)\s+(?:[-–:]\s*)?(?:Application received|Application update)$',subject,re.I)
 return clean_company_display_name(found.group(1)) if found else ''

def role_from_email(subject, body):
 found=re.search(r'\b(?:application for|applying for|applied for)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9 /&()\x27-]{3,100}?)(?=\s+(?:at|with)\s|[.!\n]|$)',subject+'\n'+body,re.I)
 title=found.group(1).strip() if found else ''
 return title if title.lower() not in ('role','position','job','opportunity') else ''

@dataclass
class Match:
 status: str
 job_id: str = ''
 certain: bool = False
 candidates: tuple = ()
 reason: str = ''

def classify(text):
 text=text.lower()
 if not re.search(r'\b(application|role|position|job|recruitment|interview|assessment|employment|applying)\b',text):return ''
 rules=[('Rejected',r'(?:not (?:be )?(?:progressing|proceeding|moving forward)|unsuccessful|regret to inform|not been successful|not to (?:progress|proceed)|will not be (?:progressing|proceeding))'),
 ('Offer',r'(?:pleased to offer you|offer of employment|employment offer|offer you (?:the|a) (?:role|position|job))'),
 ('Interview',r'(?:invite.{0,70}interview|interview.{0,40}(?:invitation|scheduled|booking|availability)|schedule.{0,40}interview|invited.{0,50}assessment cent(?:re|er))'),
 ('Assessment',r'(?:invite.{0,70}(?:assessment|online test|numerical reasoning)|(?:complete|take).{0,70}(?:assessment|online test|numerical reasoning)|assessment invitation)'),
 ('Applied',r'(?:thank(?: you|s) for (?:your application|applying)|application (?:has been |was |successfully )?received|received your application|application (?:has been |was )?submitted)')]
 return next((status for status,pattern in rules if re.search(pattern,text,re.S)), '')

def match_message(subject, sender, body, jobs):
 display_sender=parseaddr(sender)[0] if '@' in sender else sender
 text=f'{subject} {display_sender} {body}'.lower();status=classify(subject+' '+body)
 if not status:return Match(status,reason='No application-status evidence')
 urls=re.findall(r'https?://[^\s<>"\)]+',subject+' '+body)
 def specific_link(job):
  return any(finance_same_listing({'link':u.rstrip('.,')},job) for u in urls)
 active=[job for job in jobs if job.get('status')!='Dismissed']
 exact=[job for job in active if specific_link(job)]
 if len(exact)==1:return Match(status,exact[0]['id'],True,(exact[0]['id'],),'Specific application URL')
 if len(exact)>1:return Match(status,candidates=tuple(j['id'] for j in exact),reason='Several application URLs; choose the matching role')
 employer=normalize_company(employer_from_email(subject,sender,body))
 candidates=[]
 for job in jobs:
  if job.get('status')=='Dismissed':continue
  company=job.get('company','').lower().strip()
  if not company:continue
  key=normalize_company(company)
  words=[w for w in re.findall(r'[a-z0-9]+',clean_company_display_name(company).lower()) if w not in ('uk','limited','ltd','llp','plc','the')]
  mentioned=bool(words) and all(re.search(r'\b'+re.escape(w)+r'\b',text) for w in words)
  if mentioned or key==employer:candidates.append(job)
 norm_text=' '+normalize_role(subject+' '+body)+' '
 roles=[job for job in candidates if normalize_role(job.get('title','')) and ' '+normalize_role(job['title'])+' ' in norm_text]
 if len(roles)==1:return Match(status,roles[0]['id'],True,tuple(j['id'] for j in candidates[:5]),'Distinct employer and role title')
 # Company-only matching is restricted to one existing application, as in ApplicationTrackr.
 if len(candidates)==1 and candidates[0].get('status') in APPLICATION_STAGES:
  return Match(status,candidates[0]['id'],True,(candidates[0]['id'],),'Single recorded application for this employer')
 return Match(status,candidates=tuple(j['id'] for j in candidates[:5]),reason='Several jobs or incomplete role evidence; choose manually' if candidates else 'Application not in the tracker; select a job or record it from this email')

def updates():
 with store.connect() as c:return [{'id':r['id'],**json.loads(r['payload']),'resolved':r['resolved']} for r in c.execute("SELECT * FROM email_updates WHERE resolved='' ORDER BY created DESC")]

def advance_update(update_id, job, status):
 order={'New':0,'Saved':0,'Applied':1,'Assessment':2,'Interview':3,'Offer':4,'Rejected':5,'Withdrawn':5}
 can_advance=job['status'] not in ('Rejected','Withdrawn') and order.get(status,0)>=order.get(job['status'],0)
 apply_update(update_id,job['id'],status,change_stage=can_advance)

def reconcile_updates():
 # An email may arrive before discovery saves the corresponding job.
 jobs=store.jobs()
 with store.connect() as c:pending=c.execute("SELECT id,payload FROM email_updates WHERE resolved='' ORDER BY created").fetchall()
 for row in pending:
  record=json.loads(row['payload'])
  decision=match_message(record.get('subject',''),record.get('sender',''),record.get('snippet',''),jobs)
  if decision.certain:
   job=next(j for j in jobs if j['id']==decision.job_id)
   advance_update(row['id'],job,decision.status)
   jobs=store.jobs()

def apply_update(update_id, job_id, status, change_stage=True):
 if status not in APPLICATION_STAGES:raise ValueError('Select an application stage')
 with store.connect() as c:row=c.execute('SELECT payload,resolved FROM email_updates WHERE id=?',(update_id,)).fetchone()
 if not row:raise ValueError('Message not found')
 payload=json.loads(row[0]);job=next((j for j in store.jobs() if j['id']==job_id),None)
 if not job:raise ValueError('Select a tracked job')
 evidence=events.details(payload,status);timestamp=events.occurred_at(payload)
 with store.connect() as c:
  old=c.execute('SELECT job_id FROM application_events WHERE id=?',(update_id,)).fetchone()
  if old and old['job_id']!=job_id:raise ValueError('This message is already matched to another application')
  if old and row['resolved']=='matched:'+job_id:return
  if not old:c.execute('INSERT INTO application_events VALUES(?,?,?,?,?)',(update_id,job_id,json.dumps(evidence),timestamp,store.now()))
 label=evidence['label'];specific=label!=status
 if change_stage:
  last=next((h['event'].removeprefix('Status: ') for h in store.history(job_id) if h['event'].startswith('Status: ')), '')
  store.update_job(job_id,{'status':status},stage_label=label if specific and last!=label else None)
 with store.connect() as c:c.execute('UPDATE email_updates SET resolved=? WHERE id=?',('matched:'+job_id,update_id))
 # Backfill evidence belongs in the timeline, not a burst of old notifications.
 recent=(datetime.now(timezone.utc)-datetime.fromisoformat(timestamp)).total_seconds()<7*86400
 if recent and change_stage and (job['status']!=status or specific):
  alerts.enqueue('email:'+update_id,'JobTrackr application update',f"{job['company']} — {job['title']}\n{label}\n{payload.get('subject','')}\nUpdated from an application email. Sheet sync follows automatically.",alerts.base()+'/#applications')

def decode(value):
 try:return str(make_header(decode_header(value or '')))
 except (ValueError,LookupError):return str(value or '')

def message_body(message):
 parts=[]
 for part in message.walk():
  if part.get_content_maintype()=='multipart' or part.get_content_disposition()=='attachment':continue
  if part.get_content_type() not in ('text/plain','text/html'):continue
  content=part.get_payload(decode=True) or b''
  try:text=content.decode(part.get_content_charset() or 'utf-8',errors='replace')
  except LookupError:text=content.decode('utf-8',errors='replace')
  parts.append(plain(text) if part.get_content_type()=='text/html' else text)
 return '\n'.join(parts)[:30000]

def mailbox_folder(client):
 configured=os.getenv('JOBTRACKR_IMAP_FOLDER','')
 if configured:return configured
 # Gmail All Mail includes archived/labelled received mail; never Spam or Trash.
 result=client.list()
 if isinstance(result,tuple) and len(result)==2 and result[0]=='OK':
  for raw in result[1] or []:
   if isinstance(raw,bytes) and b'\\All' in raw:
    found=re.search(rb'"([^"\n]+)"\s*$',raw)
    if found:return '"'+found.group(1).decode('ascii')+'"'
 return 'INBOX'

def poll():
 user=os.getenv('JOBTRACKR_IMAP_USER','');password=os.getenv('JOBTRACKR_IMAP_PASSWORD','').replace(' ','');host=os.getenv('JOBTRACKR_IMAP_HOST','imap.gmail.com')
 if not user or not password:
  store.set_setting('mail_health',{'connected':False,'message':'Not connected. Configure your brother’s mailbox separately.'});return
 if not LOCK.acquire(blocking=False):return
 client=None
 try:
  client=imaplib.IMAP4_SSL(host,timeout=20);client.login(user,password);folder=mailbox_folder(client)
  selected=client.select(folder,readonly=True)
  if isinstance(selected,tuple) and selected[0]!='OK':raise ValueError('Mailbox folder unavailable')
  validity=(client.response('UIDVALIDITY')[1] or [b'unknown'])[0]
  account=hashlib.sha256((host+'|'+user).encode()).hexdigest()[:16]
  cursor_key='mail_cursor:'+hashlib.sha256((account+'|'+folder+'|'+str(validity)).encode()).hexdigest()[:24]
  cursor=store.setting(cursor_key,0)
  if cursor:typ,data=client.uid('search',None,'UID',str(cursor+1)+':*')
  else:
   days=max(14,min(365,int(os.getenv('JOBTRACKR_MAIL_LOOKBACK_DAYS','90'))))
   since=(datetime.now(timezone.utc)-timedelta(days=days)).strftime('%d-%b-%Y')
   typ,data=client.uid('search',None,'SINCE',since)
  if typ!='OK':raise ValueError('Mailbox search failed')
  uids=sorted({int(uid) for uid in (data[0] or b'').split() if int(uid)>cursor})
  batch=max(1,min(500,int(os.getenv('JOBTRACKR_MAIL_BATCH_SIZE','200'))));processed=0
  for numeric_uid in uids[:batch]:
   uid=str(numeric_uid).encode();typ,raw=client.uid('fetch',uid,'(BODY.PEEK[])')
   if typ!='OK':raise ValueError('Message fetch incomplete; checkpoint retained')
   payload=next((x[1] for x in raw if isinstance(x,tuple)),None)
   if not payload:raise ValueError('Empty message fetch; checkpoint retained')
   message=email.message_from_bytes(payload);message_id=message.get('Message-ID','').strip()
   mid=account+':'+hashlib.sha256((message_id or folder+'|'+str(validity)+'|'+str(numeric_uid)).encode()).hexdigest()[:32]
   with store.connect() as c:seen=c.execute('SELECT 1 FROM email_updates WHERE id=?',(mid,)).fetchone()
   if not seen:
    subject=decode(message['Subject']);sender=decode(message['From']);body=message_body(message)
    decision=match_message(subject,sender,body,store.jobs()) if parseaddr(sender)[1].lower()!=user.lower() else Match('',reason='Outgoing email')
    if decision.certain and decision.reason=='Single recorded application for this employer':
     matched=next(j for j in store.jobs() if j['id']==decision.job_id)
     age=(datetime.fromisoformat(matched['created'])-datetime.fromisoformat(events.occurred_at({'date':decode(message['Date'])}))).total_seconds()
     if age>14*86400:decision.certain=False;decision.reason='Older employer-only email; confirm which role it belongs to'
    record={'subject':subject[:300],'sender':sender[:300],'date':decode(message['Date'])[:100],'snippet':body[:30000] if decision.status else '', 'status':decision.status,'candidates':list(decision.candidates),'reason':decision.reason,'company':employer_from_email(subject,sender,body),'title':role_from_email(subject,body)}
    resolved='ignored' if not decision.status else ''
    if not decision.status:record={'status':'','reason':'Not an application update'}
    with store.connect() as c:c.execute('INSERT OR IGNORE INTO email_updates VALUES(?,?,?,?)',(mid,json.dumps(record),resolved,store.now()))
    if decision.certain:
     job=next(j for j in store.jobs() if j['id']==decision.job_id);advance_update(mid,job,decision.status)
   store.set_setting(cursor_key,numeric_uid);processed+=1
   if processed%20==0:
    remaining=max(0,len(uids)-processed)
    store.set_setting('mail_health',{'connected':True,'last_checked':store.now(),'folder':folder.strip('"'),'remaining':remaining,'message':f'Processing mailbox without marking messages read. {remaining} messages remaining.'})
  reconcile_updates();remaining=max(0,len(uids)-processed)
  store.set_setting('mail_health',{'connected':True,'last_checked':store.now(),'folder':folder.strip('"'),'remaining':remaining,'message':f'Mailbox checked without marking messages read. {remaining} messages awaiting the next batch.' if remaining else 'Mailbox checked without marking messages read. Uncertain matches await review.'})
 except (imaplib.IMAP4.error,OSError,ValueError):store.set_setting('mail_health',{'connected':False,'message':'Email check interrupted; saved checkpoints will retry automatically.','last_checked':store.now()})
 finally:
  if client:
   try:client.logout()
   except Exception:pass
  LOCK.release()

def loop(stop):
 while not stop.is_set():
  try:poll()
  except Exception:store.set_setting('mail_health',{'connected':False,'message':'Email check failed; will retry.'})
  stop.wait(10 if store.setting('mail_health',{}).get('remaining',0) else 300)
