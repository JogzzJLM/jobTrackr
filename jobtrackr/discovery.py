"""Diversified public employer feeds and verified, paginated graduate boards."""
import hashlib
import os
import concurrent.futures
import re
import threading
import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from . import store, alerts
from .eligibility import evaluate, displayable
from .normalization import normalize_url, canonical_url
from .verifier import verify_listing, plain, deadline_date
SCAN_INTERVAL=max(300,int(os.getenv("SCRAPER_INTERVAL_SECONDS","300")))
SCAN_LOCK=threading.Lock()
HEADERS={'User-Agent':'Mozilla/5.0','Accept':'text/html,application/xhtml+xml'}

def get(url):
 r=requests.get(url,headers=HEADERS,timeout=20);r.raise_for_status();return r

def candidate(company,title,location,link,source,description='',**extra):
 return {'company':company,'title':title,'location':location,'link':canonical_url(link),'source':source,'description':plain(description),**extra}

def board(name,url,pattern,company='',pages=5):
 visited=set();result=[]
 for _ in range(pages):
  if url in visited:break
  visited.add(url);soup=BeautifulSoup(get(url).text,'html.parser')
  for a in soup.select('a[href]'):
   link=urljoin(url,a['href']);heading=a.find(['h2','h3']);title=(heading or a).get_text(' ',strip=True)
   if re.search(pattern,urlparse(link).path) and len(title)>10 and title.lower() not in ('view opportunity','apply now'):
    article=a.find_parent('article');context=article.get_text(' ',strip=True) if article else ''
    if 'School Leaver Scheme' in context or 'Industrial Placement' in context:continue
    result.append(candidate(company,title,'',link,name))
  next_link=next((a for a in soup.select('a[href]') if a.get_text(' ',strip=True).lower() in ('next','next page')),None)
  if not next_link:break
  url=urljoin(url,next_link['href'])
 return result


def _bdo_workday():
 result=[];offset=0
 for _ in range(10):
  r=requests.post('https://bdouk.wd3.myworkdayjobs.com/wday/cxs/bdouk/BDO_Early_in_Career/jobs',headers=HEADERS,json={'appliedFacets':{},'limit':20,'offset':offset,'searchText':'graduate'},timeout=20);r.raise_for_status();page=r.json();items=page.get('jobPostings',[])
  for j in items:
   result.append(candidate('BDO',j['title'],j.get('locationsText',''), 'https://bdouk.wd3.myworkdayjobs.com/BDO_Early_in_Career'+j['externalPath'],'BDO employer feed',country='GB'))
  offset+=len(items)
  if not items or offset>=page.get('total',offset):break
 return result

def bdo_workday():
 try:return _bdo_workday()
 except (requests.RequestException,ValueError):
  # Workday can block the home-server IP while its employer careers pages work.
  return board('BDO graduates','https://careers.bdo.co.uk/en/search-jobs/graduate/',r'/job/','BDO',5)

def rsm():
 data=[];offset=0
 for _ in range(15):
  response=get(f'https://www.rsmuk.com/job-search-index.json?limit=500&offset={offset}').json();items=response.get('data',[]);data.extend(items)
  offset+=len(items)
  if not items or offset>=response.get('total',len(data)):break
 result=[]
 for item in data:
  if str(item.get('showInSearch','true')).lower()=='false':continue
  title=item.get('jobTitle') or item.get('title','');loc=item.get('jobLocation','').replace('offices:','').replace(',',', ');link=urljoin('https://www.rsmuk.com',item.get('path',''))
  if '/careers/jobs/' not in link:continue
  result.append(candidate('RSM UK',title,loc,link,'RSM employer feed',item.get('jobDescription',''),country='GB'))
 return result

def greenhouse(company):
 data=get(f'https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true').json()['jobs']
 return [candidate(company,j['title'],j.get('location',{}).get('name',''),j['absolute_url'],'Greenhouse employer feed',j.get('content','')) for j in data]

def lever(company):
 data=get(f'https://api.lever.co/v0/postings/{company}?mode=json').json()
 return [candidate(company,j['text'],j.get('categories',{}).get('location',''),j['hostedUrl'],'Lever employer feed',j.get('descriptionPlain','')+' '+plain(j.get('additional',''))) for j in data]

def smart(company):
 data=[];offset=0
 for _ in range(10):
  page=get(f'https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset={offset}').json();items=page.get('content',[]);data.extend(items);offset+=len(items)
  if not items or offset>=page.get('totalFound',offset):break
 results=[]
 for item in data:
  loc=item.get('location',{});j=candidate(company,item['name'],', '.join(str(loc.get(k,'')) for k in ('city','country')),item.get('ref',''),'SmartRecruiters employer feed',country=loc.get('country',''))
  if evaluate(j)['state']=='filtered':continue
  detail=get(item['ref']).json();sections=detail.get('jobAd',{}).get('sections',{})
  j['description']=plain(' '.join(x.get('text','') for x in sections.values() if isinstance(x,dict)))
  j['link']=detail.get('postingUrl') or f"https://jobs.smartrecruiters.com/{company}/{item['id']}"
  results.append(j)
 return results

def sources():
 return [('BDO employer feed',bdo_workday),
 ('Accountancy Careers',lambda:board('Accountancy Careers','https://www.accountancycareers.co.uk/search/jobs/',r'/jobs/[^/]+/',pages=5)),
 ('Graduate-jobs.com accounting',lambda:board('Graduate-jobs.com accounting','https://www.graduate-jobs.com/jobs/accounting',r'/job/',pages=5)),
 *[(f'Graduate-jobs.com {area}',lambda area=area:board(f'Graduate-jobs.com {area}',f'https://www.graduate-jobs.com/jobs/{area}',r'/job/',pages=5)) for area in ('finance','banking')],
 *[(f'Reed {area}',lambda area=area:board(f'Reed {area}',f'https://www.reed.co.uk/jobs/{area}-jobs',r'/jobs/[^/]+/\d+',pages=3)) for area in ('graduate-accountant','trainee-accountant','graduate-finance')],
 ('RSM employer feed',rsm),('Sanctuary graduates',lambda:board('Sanctuary graduates','https://jobs.sanctuarygraduates.co.uk/',r'/job/',pages=5)),
 ('ACCA Careers',lambda:board('ACCA Careers','https://jobs.accaglobal.com/jobs/united-kingdom/graduate/',r'/job/',pages=3)),
 ('DWP Find a job',lambda:board('DWP Find a job','https://findajob.dwp.gov.uk/search?q=trainee+accountant&w=UK',r'/details/',pages=3)),
 *[(f'Greenhouse: {c}',lambda c=c:greenhouse(c)) for c in ('monzo','wise','deliveroo')],
 *[(f'SmartRecruiters: {c}',lambda c=c:smart(c)) for c in ('EvelynPartners','ForvisMazars','Visa')]]

def _enrich(job,force=False):
 if evaluate(job)['state']=='filtered':return job,{'state':'filtered','reason':'Role or seniority outside profile'}
 check=verify_listing(job.get('verification_url') or job['link'],job['title'],force=force)
 # RSM public index/detail is employer evidence, even though its static page labels
 # the apply link by URL rather than the word “Apply”.
 if check['state']=='unknown' and urlparse(job['link']).hostname=='www.rsmuk.com':
  try:
   soup=BeautifulSoup(get(job['link']).text,'html.parser');main=soup.find('main');apply=next((a['href'] for a in soup.select('a[href]') if urlparse(a['href']).hostname=='rsm-careers.tal.net'),None)
   if main and apply and main.select_one('.job-details') and soup.title and job['title'].lower() in soup.title.get_text().lower() and len(main.get_text())>500:
    check={'state':'verified','reason':'Employer job description and specific application link','checked_at':store.now(),'title':soup.title.get_text(' ',strip=True),'description':main.get_text(' ',strip=True),'final_url':job['link']}
    job['apply_url']=apply
  except requests.RequestException:pass
 if check['state']=='unknown' and job['source']=='Accountancy Careers':
  try:
   soup=BeautifulSoup(get(job['link']).text,'html.parser');description=soup.select_one('#job-description .article-content');employer=soup.select_one('.job-detailheader a.logo-link[title]')
   title=soup.title.get_text(' ',strip=True).lower() if soup.title else ''
   applies=[a for a in soup.select('a[href]') if re.search(r'apply',a.get_text(' ',strip=True),re.I)]
   content=description.get_text(' ',strip=True) if description else ''
   if description and employer and applies and job['title'].lower() in title and len(content)>300 and not re.search(r'(vacancy (?:has )?closed|no longer accepting|applications (?:have )?closed)',content,re.I):
    check={'state':'verified','reason':'Specific accountancy vacancy, employer, full description and apply control','checked_at':store.now(),'description':content,'final_url':job['link']}
  except requests.RequestException:pass
 if check['state']!='verified':return job,check
 if job['source']=='Sanctuary graduates':
  try:
   soup=BeautifulSoup(get(job['link']).text,'html.parser');facts={x.find('dt').get_text(' ',strip=True).lower():x.find('dd').get_text(' ',strip=True) for x in soup.select('.detail-hero__facts > div') if x.find('dt') and x.find('dd')}
   if facts.get('location'):job['location']=facts['location']
   if facts.get('salary'):job['salary']=facts['salary']
   if facts.get('deadline'):check['closing_date']=re.sub(r'^Closes\s+','',facts['deadline'],flags=re.I)
   description=soup.select_one('.job-detail')
   if description:job['description']=description.get_text(' ',strip=True)
   employer=re.search(r'About The Company\s+([A-Z][A-Za-z &]+?)\s+is\s',job.get('description',''))
   if employer:job['company']=employer.group(1)
   elif ' with ' in job['title']:job['company']=job['title'].split(' with ',1)[1]
  except requests.RequestException:pass
 for key in ('title','company','location','country','description','published_at'):
  if check.get(key):job[key]=check[key]
 if job['source']=='Accountancy Careers':
  try:
   soup=BeautifulSoup(get(job['link']).text,'html.parser');facts={}
   for li in soup.select('.meta-infolist li'):
    field=li.select_one('.fieldname')
    if field:facts[field.get_text(' ',strip=True).strip(': ').lower()]=li.get_text(' ',strip=True).replace(field.get_text(' ',strip=True),'',1).strip()
   if facts.get('location'):job['location']=facts['location']
   if facts.get('salary'):job['salary']=facts['salary']
   if facts.get('deadline'):check['closing_date']=facts['deadline']
   employer=soup.select_one('.job-detailheader a.logo-link[title]')
   if employer:job['company']=employer['title']
   description=soup.select_one('#job-description .article-content')
   if description:job['description']=description.get_text(' ',strip=True)
   if 'school leaver' in facts.get('job type','').lower():job['title']='School Leaver '+job['title']
  except requests.RequestException:pass
 job['deadline']=(deadline_date(check.get('closing_date') or job.get('deadline')) or '')
 if job['deadline']:job['deadline']=job['deadline'].isoformat()
 job['verification']={k:check.get(k) for k in ('state','reason','checked_at')}
 # Pull only the job's description, not recommendations, navigation or footer.
 if job['source']=='BDO graduates':
  try:
   soup=BeautifulSoup(get(job.get('verification_url') or job['link']).text,'html.parser');node=soup.select_one('.job-description, .ats-description, #job-description')
   apply=next((a['href'] for a in soup.select('a[href]') if urlparse(a['href']).hostname=='bdouk.wd3.myworkdayjobs.com' and '/job/' in a['href']),None)
   if apply:
    job['verification_url']=job.get('verification_url') or job['link'];job['apply_url']=apply;job['link']=canonical_url(apply).removesuffix('/apply')
   if node:job['description']=node.get_text(' ',strip=True)
  except requests.RequestException:pass
 return job,check

_ENRICH_CACHE_LOCK=threading.RLock()
def enrich(job,force=False):
 cache_path=store.DATA_DIR/'enriched_listings.json';key=job['link']
 with _ENRICH_CACHE_LOCK:cached=store.load_json_safe(cache_path,{}).get(key)
 if cached and not force:
  ttl=1800 if cached['check']['state'] in ('verified','closed') else 300
  if time.time()-cached['saved_at']<ttl:return {**job,**cached['job']},dict(cached['check'])
 result,check=_enrich(job,force=force)
 with _ENRICH_CACHE_LOCK:
  cache=store.load_json_safe(cache_path,{})
  cache[key]={'saved_at':time.time(),'job':{k:v for k,v in result.items() if k not in ('status','notes','reminder','created','updated')},'check':check}
  cache=dict(sorted(cache.items(),key=lambda item:item[1]['saved_at'],reverse=True)[:2000])
  store.atomic_write_json(cache_path,cache)
 return result,check

def scan():
 if not SCAN_LOCK.acquire(blocking=False):return False
 started=time.time();health={};new=0;checked=0
 try:
  store.set_setting('scan',{'running':True,'started':store.now()})
  candidates=[]
  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
   futures={pool.submit(fn):name for name,fn in sources()}
   for future in concurrent.futures.as_completed(futures):
    name=futures[future]
    try:
     rows=future.result();candidates.extend(rows);health[name]={'ok':True,'candidates':len(rows),'checked_at':store.now()}
    except Exception as exc:health[name]={'ok':False,'error':f'Feed unavailable ({type(exc).__name__}); will retry','checked_at':store.now()}
  # Imported legacy jobs are candidates only: never shown as verified blindly.
  if not store.setting('legacy_reviewed',False):
   for root in (store.DATA_DIR, __import__('pathlib').Path(__file__).resolve().parent.parent):
    for old in store.load_json_safe(root/'discovered_jobs.json',[]):
     candidates.append(candidate(old.get('company',''),old.get('title',''),old.get('location',''),old.get('link',''), 'Legacy import',old.get('description') or old.get('metadata',{}).get('description','')))
   store.set_setting('legacy_reviewed',True)
  for existing in store.jobs():
   decision=evaluate(existing)
   if not displayable(decision):
    existing['verification']={'state':decision['state'],'reason':'; '.join(decision['requirements']),'checked_at':store.now()};store.upsert(existing)
  candidates.extend({k:v for k,v in j.items() if k not in ('status','notes','reminder','created','updated')} for j in store.jobs())
  unique={normalize_url(j['link']):j for j in candidates if j.get('link') and evaluate(j)['state']!='filtered'}
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
   futures={pool.submit(enrich,j):j for j in unique.values()}
   for future in concurrent.futures.as_completed(futures):
    original=futures[future];checked+=1
    try:job,verification=future.result()
    except Exception:store.review(original,'Could not retrieve listing; will retry','unknown');continue
    decision=evaluate(job)
    if verification['state']!='verified' or not displayable(decision):
     reason='; '.join(decision['requirements']) if decision['requirements'] else verification.get('reason','Cannot confirm')
     store.review(job,reason,decision['state'] if decision['state']!='eligible' else verification['state'])
     # Existing application history remains, but the listing ceases to be actionable.
     existing=next((x for x in store.jobs() if x['link']==job['link']),None)
     if existing:
      job['id']=existing['id'];job['verification']={'state':verification['state'] if verification['state']!='verified' else decision['state'],'reason':reason,'checked_at':store.now()};store.upsert(job)
     continue
    job.update(decision);job['id']=hashlib.sha256(job['link'].encode()).hexdigest()[:24]
    is_new=store.upsert(job);store.clear_review(job['link'])
    if is_new:
     new+=1
     if store.setting('alerts_initialized',False):alerts.new_listing(job)
  store.set_setting('sources',health)
  store.set_setting('scan',{'running':False,'finished':store.now(),'seconds':round(time.time()-started),'new':new,'checked':checked})
  if not store.setting('alerts_initialized',False):
   if new:alerts.enqueue('initial-discovery','JobTrackr is ready',f'{new} verified finance graduate roles found. Open JobTrackr to explore them. Future new roles get individual alerts.')
   store.set_setting('alerts_initialized',True)
  alerts.flush();return True
 except Exception as exc:
  store.set_setting('scan',{'running':False,'error':type(exc).__name__,'finished':store.now()});return False
 finally:SCAN_LOCK.release()

def loop(stop):
 scan()
 last=time.time()
 while not stop.wait(60):
  alerts.scheduled()
  if time.time()-last>=SCAN_INTERVAL:scan();last=time.time()
