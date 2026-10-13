"""Direct employer and public-service finance feeds; every role is verified later."""
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin,quote
from bs4 import BeautifulSoup
from .verifier import plain,deadline_date


def pinpoint(company,base):
 from .discovery import candidate,get
 data=get(base.rstrip('/')+'/en/postings.json').json()
 if not isinstance(data.get('data'),list):raise ValueError('Vacancy feed structure changed')
 result=[]
 for row in data['data']:
  loc=row.get('location') or {};location=', '.join(str(loc.get(k,'')) for k in ('city','province') if loc.get(k))
  content=' '.join(str(row.get(k) or '') for k in ('description','key_responsibilities','skills_knowledge_expertise','benefits'))
  if row.get('url') and row.get('title'):result.append(candidate(company,row['title'],location,row['url'],company+' employer feed',content,country='GB',deadline=row.get('deadline_at') or ''))
 return result


def teamtailor(company,base):
 from .discovery import candidate,get
 root=ET.fromstring(get(base.rstrip('/')+'/jobs.rss').text)
 if root.tag!='rss':raise ValueError('Vacancy feed structure changed')
 result=[];ns={'tt':'https://teamtailor.com/locations'}
 for row in root.findall('channel/item'):
  locations=row.findall('tt:locations/tt:location',ns)
  cities=[x.findtext('tt:city',default='',namespaces=ns) or x.findtext('tt:name',default='',namespaces=ns) for x in locations]
  countries=list(dict.fromkeys(x.findtext('tt:country',default='',namespaces=ns) for x in locations))
  title=row.findtext('title');link=row.findtext('link')
  if title and link:result.append(candidate(company,title,', '.join(filter(None,cities)),link,company+' employer feed',row.findtext('description') or '',country=', '.join(filter(None,countries))))
 return result


def nhs(query,pages=10):
 from .discovery import candidate,get
 url='https://www.jobs.nhs.uk/candidate/search/results?keyword='+quote(query)+'&language=en';seen=set();result=[]
 for _ in range(pages):
  if url in seen:break
  seen.add(url);soup=BeautifulSoup(get(url).text,'html.parser')
  for card in soup.select('[data-test="search-result"]'):
   title=card.select_one('[data-test="search-result-job-title"]');loc=card.select_one('[data-test="search-result-location"]')
   if not title or not title.get('href'):continue
   location=loc.select_one('.location-font-size') if loc else None
   company=loc.find('h3') if loc else None
   company_text=company.get_text(' ',strip=True).replace(location.get_text(' ',strip=True),'').strip() if company and location else company.get_text(' ',strip=True) if company else ''
   closing=card.select_one('[data-test="search-result-closingDate"] strong');salary=card.select_one('[data-test="search-result-salary"] strong')
   deadline=deadline_date(closing.get_text(' ',strip=True)) if closing else None
   result.append(candidate(company_text,title.get_text(' ',strip=True),location.get_text(' ',strip=True) if location else '',urljoin(url,title['href'].split('?')[0]),'NHS Jobs: '+query,country='GB',deadline=deadline.isoformat() if deadline else '',salary=salary.get_text(' ',strip=True) if salary else ''))
  next_link=soup.select_one('[data-test="search-next-page"]') or next((a for a in soup.select('a[href]') if re.search(r'^next(?: page)?$',a.get_text(' ',strip=True),re.I)),None)
  if not next_link:break
  url=urljoin(url,next_link['href'])
 return result


def oracle(company,host,site,queries=('finance','accounts','payroll')):
 from .discovery import candidate,get
 result={}
 for query in queries:
  offset=0
  for _ in range(5):
   url=f'https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber={site},keyword={quote(query)},limit=50,offset={offset}'
   data=get(url,accept='application/json').json();items=data.get('items',[])
   if not items:break
   rows=items[0].get('requisitionList')
   if not isinstance(rows,list):raise ValueError('Vacancy feed structure changed')
   for row in rows:
    if str(row.get('PrimaryLocationCountry','')).upper() not in ('GB','GBR','UK'):continue
    link=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{row['Id']}"
    result[link]=candidate(company,row['Title'],row.get('PrimaryLocation',''),link,company+' employer feed',row.get('ShortDescriptionStr') or '',country=row.get('PrimaryLocationCountry',''),deadline=row.get('PostingEndDate') or '',requisition_id=row['Id'])
   offset+=len(rows)
   if not rows or offset>=items[0].get('TotalJobsCount',offset):break
 return list(result.values())


def haysmac():
 from .discovery import board
 rows=board('HaysMac employer feed','https://haysmac.com/vacancies/',r'^/vacancies/[^/]+/','HaysMac',pages=3)
 for job in rows:job['title']=re.split(r'\s+View position',job['title'],flags=re.I)[0].strip();job['country']='GB'
 return rows


def sources():
 from .discovery import greenhouse,workday_employer
 return [('Menzies employer feed',lambda:pinpoint('Menzies','https://menzies.pinpointhq.com')),
 ('BKL employer feed',lambda:teamtailor('BKL','https://careers.bkl.co.uk')),
 ('HaysMac employer feed',haysmac),
 ('NEXT employer feed',lambda:oracle('NEXT','ekeq.fa.em2.oraclecloud.com','CX_3001')),
 ('Sainsbury’s employer feed',lambda:oracle('Sainsbury’s','hdhe.fa.em3.oraclecloud.com','CX_1')),
 ('Fidelity International employer feed',lambda:workday_employer('Fidelity International','fil.wd3.myworkdayjobs.com','fil','001',search='finance',country='')),
 ('Forvis Mazars UK employer feed',lambda:workday_employer('Forvis Mazars','forvismazarsuk.wd107.myworkdayjobs.com','forvismazarsuk','FM_1',country='')),
 ('GoCardless employer feed',lambda:greenhouse('gocardless')),
 ('Tide employer feed',lambda:greenhouse('tide')),
 *[('NHS Jobs: '+q,lambda q=q:nhs(q)) for q in ('finance','accounts','payroll')]]
