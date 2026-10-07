"""Application evidence and explicit rounds; dates are suggestions, never invented."""
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from . import store

def occurred_at(record):
 try:
  value=parsedate_to_datetime(record.get('date',''))
  return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
 except (ValueError,TypeError,OverflowError):return store.now()

def details(record, status):
 text=record.get('subject','')+' '+record.get('snippet','')
 label=status
 if status in ('Interview','Assessment'):
  round_match=re.search(r'\b(?:(first|second|third|fourth|1st|2nd|3rd|4th|final)\s+(?:round\s+)?'+status+r'|'+status+r'\s+(?:round\s*)?(\d+)|round\s+(\d+)\s+'+status+r')\b',text,re.I)
  if round_match:
   value=next(v for v in round_match.groups() if v)
   number={'first':'1','second':'2','third':'3','fourth':'4','1st':'1','2nd':'2','3rd':'3','4th':'4'}.get(value.lower(),value.lower())
   label=status+(' (final)' if number=='final' else ' '+number)
  elif status=='Interview' and re.search(r'\bassessment cent(?:re|er)\b',text,re.I):label='Assessment centre'
 suggestions=[]
 for match in re.finditer(r'\b(?:deadline|complete\s+(?:it\s+)?by|due(?:\s+date)?|interview(?:\s+(?:on|date))?|assessment(?:\s+(?:on|date))?)\s*[:,-]?\s*(?:is\s+)?(\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}(?:\s+20\d{2})?)\b',text,re.I):
  suggestions.append({'text':match.group(0)[:160],'confirmed':False})
 return {'label':label,'status':status,'subject':record.get('subject','')[:300],'sender':record.get('sender','')[:300],'reason':record.get('reason','Email confirmed by you'),'date_suggestions':suggestions[:3],'source':'email'}
