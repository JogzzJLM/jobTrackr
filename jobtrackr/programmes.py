"""Conservative employer programme grouping for notification delivery."""
import re
from urllib.parse import urlparse,parse_qs
from .normalization import normalize_company

def key(job):
 if job.get('route_type')!='Direct employer' or not job.get('location'):return job['id']
 parsed=urlparse(job.get('apply_url') or job.get('link',''));query=parse_qs(parsed.query)
 fields=('programme','business_area','intake_year','start_date')
 if parsed.hostname=='student.kpmgcareers.co.uk' and all(query.get(k) for k in fields):return normalize_company(job.get('company',''))+'|'+ '|'.join(query[k][0].lower() for k in fields)
 title=job.get('title','')
 names=sorted(set([job['location']]+[x.strip() for x in re.split(r'[,;|]',job['location']) if x.strip()]),key=len,reverse=True)
 for location in names:title=re.sub(r'\b'+re.escape(location)+r'\b(?=\s*(?:$|[,()\-–—]|(?:January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|20\d{2})\b))',' ',title,flags=re.I)
 title=re.sub(r'\s*[-–—|]\s*(?:East Midlands|West Midlands|Midlands|East Anglia|South East|South West|North East|North West|Scotland|Wales|Northern Ireland|England|United Kingdom|UK)\s*(?=$|[-–—|]|20\d{2}\b)',' ',title,flags=re.I)
 title=' '.join(re.findall(r'[a-z0-9]+',title.lower()))
 return normalize_company(job.get('company',''))+'|'+title if title else job['id']
