"""Polite shared GET pacing and HTTP 429 cooldown across feeds and verification."""
import threading
import time
from urllib.parse import urlparse
import requests
_LOCK=threading.Lock()
_HOSTS={}

def get(url, **kwargs):
 from .source_policy import blocked_url
 if blocked_url(url):raise requests.RequestException('Excluded source')
 host=(urlparse(url).hostname or '').lower()
 with _LOCK:state=_HOSTS.setdefault(host,{'lock':threading.Lock(),'last':0,'until':0})
 with state['lock']:
  if time.monotonic()<state['until']:raise requests.RequestException('Host rate-limited; waiting for cooldown')
  spacing=0.15
  delay=spacing-(time.monotonic()-state['last'])
  if delay>0:time.sleep(delay)
  try:
   response=requests.get(url,**kwargs)
   if response.status_code==429:
    try:cooldown=int(response.headers.get('Retry-After','1800'))
    except (ValueError,TypeError):cooldown=1800
    state['until']=time.monotonic()+max(60,min(86400,cooldown))
   return response
  finally:state['last']=time.monotonic()
