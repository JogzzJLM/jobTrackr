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
LOCK=threading.Lock()

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
 ('Interview',r'(?:invite.{0,70}interview|interview.{0,40}(?:invitation|scheduled|booking|availability)|schedule.{0,40}interview)'),
 ('Assessment',r'(?:invite.{0,70}(?:assessment|online test)|(?:complete|take).{0,70}(?:assessment|online test)|assessment invitation)'),
 ('Applied',r'(?:thank you for (?:your application|applying)|application (?:has been )?received|received your application)')]
 return next((status for status,pattern in rules if re.search(pattern,text,re.S)), '')

def match_message(subject, sender, body, jobs):
 text=f'{subject} {sender} {body}'.lower();status=classify(subject+' '+body)
 if not status or ('unsubscribe' in text and 'application' not in text):return Match(status,reason='No application-status evidence')
 matches=[]
 for job in jobs:
  if job['status']=='Dismissed':continue
  company=job.get('company','').lower().strip()
  if not company:continue
  words=[w for w in re.findall(r'[a-z0-9]+',company) if w not in ('uk','limited','ltd','llp','the')]
  company_match=bool(words) and all(re.search(r'(?<![a-z0-9])'+re.escape(w)+r'(?![a-z0-9])',text) or w in sender.lower() for w in words)
  link=job.get('link','').lower()
  exact=bool(link and link in text)
  title_words=set(re.findall(r'[a-z0-9]+',job.get('title','').lower()))-{'the','and','of','in','with','programme','program','2026','2027','september','january','graduate'}
  hits=sum(bool(re.search(r'\b'+re.escape(w)+r'\b',text)) for w in title_words)
  ratio=hits/max(1,len(title_words))
  if exact or (company_match and hits>=1):
   score=100 if exact else 40+40*ratio+min(hits,5)*3
   matches.append((score,job['id'],exact,ratio))
 matches.sort(reverse=True)
 if not matches:return Match(status,reason='Company or role cannot be matched to a saved job')
 top=matches[0];margin=top[0]-(matches[1][0] if len(matches)>1 else 0)
 certain=top[2] or (top[0]>=78 and top[3]>=.65 and margin>=12)
 return Match(status,top[1] if certain else '',certain,tuple(x[1] for x in matches[:5]),'Exact listing URL' if top[2] else 'Distinct company and role match' if certain else 'Several jobs or incomplete role evidence; choose manually')

def updates():
 with store.connect() as c:return [{'id':r['id'],**json.loads(r['payload']),'resolved':r['resolved']} for r in c.execute('SELECT * FROM email_updates ORDER BY created DESC LIMIT 100')]

def apply_update(update_id, job_id, status):
 if status not in store.STATUSES:raise ValueError('Invalid status')
 with store.connect() as c:row=c.execute('SELECT payload FROM email_updates WHERE id=?',(update_id,)).fetchone()
 if not row:raise ValueError('Message not found')
 payload=json.loads(row[0]);job=next((j for j in store.jobs() if j['id']==job_id),None)
 if not job:raise ValueError('Select a tracked job')
 notes=job.get('notes','')+'\nEmail update: '+payload.get('subject','')
 store.update_job(job_id,{'status':status,'notes':notes.strip()})
 with store.connect() as c:c.execute('UPDATE email_updates SET resolved=? WHERE id=?',('matched:'+job_id,update_id))
 alerts.enqueue('email:'+update_id,'JobTrackr application update','An application record has been updated from a matched email. Open JobTrackr to view it.',alerts.base()+'/#applications')

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

def poll():
 user=os.getenv('JOBTRACKR_IMAP_USER','');password=os.getenv('JOBTRACKR_IMAP_PASSWORD','').replace(' ','');host=os.getenv('JOBTRACKR_IMAP_HOST','imap.gmail.com')
 if not user or not password:
  store.set_setting('mail_health',{'connected':False,'message':'Not connected. Configure your brother’s mailbox separately.'});return
 if not LOCK.acquire(blocking=False):return
 client=None
 try:
  client=imaplib.IMAP4_SSL(host,timeout=20);client.login(user,password);client.select('INBOX',readonly=True)
  validity=(client.response('UIDVALIDITY')[1] or [b'unknown'])[0]
  account=hashlib.sha256((host+'|'+user+'|'+str(validity)).encode()).hexdigest()[:16]
  since=(datetime.now(timezone.utc)-timedelta(days=14)).strftime('%d-%b-%Y')
  typ,data=client.uid('search',None,'SINCE',since)
  if typ!='OK':raise ValueError('Mailbox search failed')
  for uid in (data[0] or b'').split()[-100:]:
   mid=account+':'+uid.decode()
   with store.connect() as c:seen=c.execute('SELECT 1 FROM email_updates WHERE id=?',(mid,)).fetchone()
   if seen:continue
   typ,raw=client.uid('fetch',uid,'(BODY.PEEK[])')
   if typ!='OK':continue
   payload=next((x[1] for x in raw if isinstance(x,tuple)),None)
   if not payload:continue
   message=email.message_from_bytes(payload);subject=decode(message['Subject']);sender=decode(message['From']);body=message_body(message)
   decision=match_message(subject,sender,body,store.jobs())
   record={'subject':subject[:300],'sender':sender[:300],'date':decode(message['Date'])[:100],'snippet':body[:1200] if decision.status else '', 'status':decision.status,'candidates':list(decision.candidates),'reason':decision.reason}
   resolved='ignored' if not decision.status else ''
   if not decision.status:record={'status':'','reason':'Not an application update'}
   with store.connect() as c:c.execute('INSERT OR IGNORE INTO email_updates VALUES(?,?,?,?)',(mid,json.dumps(record),resolved,store.now()))
   if decision.certain:
    job=next(j for j in store.jobs() if j['id']==decision.job_id)
    order={'New':0,'Saved':0,'Applied':1,'Assessment':2,'Interview':3,'Offer':4,'Rejected':5,'Withdrawn':5}
    if order.get(decision.status,0)>order.get(job['status'],0):apply_update(mid,decision.job_id,decision.status)
    else:
     with store.connect() as c:c.execute('UPDATE email_updates SET resolved=? WHERE id=?',('no-stage-change:'+decision.job_id,mid))
  store.set_setting('mail_health',{'connected':True,'last_checked':store.now(),'message':'Mailbox checked. Ambiguous matches await review.'})
 except (imaplib.IMAP4.error,OSError,ValueError):store.set_setting('mail_health',{'connected':False,'message':'Mailbox connection failed. Check the separate JobTrackr credentials.','last_checked':store.now()})
 finally:
  if client:
   try:client.logout()
   except Exception:pass
  LOCK.release()

def loop(stop):
 while not stop.is_set():
  try:poll()
  except Exception:store.set_setting('mail_health',{'connected':False,'message':'Email check failed; will retry.'})
  stop.wait(300)
