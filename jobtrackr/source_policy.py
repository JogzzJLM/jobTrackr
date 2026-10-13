"""Source exclusions apply to collection, persisted discovery and notifications."""
from urllib.parse import urlparse
from functools import lru_cache
from datetime import date
import json
APPLICATION_STAGES=('Applied','Assessment','Interview','Offer','Rejected','Withdrawn')
def blocked_url(url):
 host=(urlparse(str(url or '')).hostname or '').lower().rstrip('.')
 return host=='reed.co.uk' or host.endswith('.reed.co.uk')
def excluded(job):
 return any(blocked_url(job.get(k)) for k in ('link','apply_url','verification_url','employer_url')) or str(job.get('source','')).lower().startswith('reed ')
def sanitise(job):
 job=dict(job)
 for key in ('link','apply_url','verification_url','employer_url'):
  if blocked_url(job.get(key)):job[key]=''
 job['alternate_links']=[x for x in job.get('alternate_links',[]) if not blocked_url(x)]
 return job

@lru_cache(maxsize=2048)
def _decision(title,description,location,country,deadline,source,profile_json,today):
 from .eligibility import evaluate
 return evaluate({'title':title,'description':description,'location':location,'country':country,'deadline':deadline,'source':source},json.loads(profile_json))


def visible_jobs(jobs):
 from .eligibility import displayable
 from .store import setting
 profile=dict(setting('profile'));profile.update(setting('school_grades',{}));profile_json=json.dumps(profile,sort_keys=True);today=date.today().isoformat()
 result=[]
 for job in jobs:
  tracked=job.get('status') in APPLICATION_STAGES
  if excluded(job) and not tracked:continue
  if not tracked:
   decision=_decision(*(str(job.get(k) or '') for k in ('title','description','location','country','deadline','source')),profile_json,today)
   if not displayable(decision):continue
   job={**job,**decision}
  result.append(sanitise(job))
 return result
