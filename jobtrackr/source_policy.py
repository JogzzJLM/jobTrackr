"""Source exclusions apply to collection, persisted discovery and notifications."""
from urllib.parse import urlparse
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

def visible_jobs(jobs):
 from .eligibility import evaluate,displayable
 result=[]
 for job in jobs:
  tracked=job.get('status') in APPLICATION_STAGES
  if excluded(job) and not tracked:continue
  if not tracked:
   decision=evaluate(job)
   if not displayable(decision):continue
   job={**job,**decision}
  result.append(sanitise(job))
 return result
