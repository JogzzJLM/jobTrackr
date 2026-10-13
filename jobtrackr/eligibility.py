"""Finance graduate gates, separate from ranking. Unconfirmed requirements stay in Review."""
import re
from .store import setting
from .verifier import deadline_date
from datetime import date

CATEGORIES = {
 'Accounting': ('accountant','accounting','accounts assistant','accounts payable','accounts receivable','bookkeep','purchase ledger','sales ledger','assistant accountant','credit control','cash allocation'),
 'Audit': ('audit','assurance'), 'Tax': ('tax','taxation'),
 'Finance': ('finance','financial analyst','financial planning','fp&a','treasury','credit analyst','investment analyst','risk analyst','banking','wealth management','portfolio analyst','valuation'),
 'Payroll': ('payroll',)}
UK_WORDS=('united kingdom','england','scotland','wales','northern ireland','london','bristol','birmingham','manchester','leeds','nottingham','edinburgh','glasgow','reading','oxford','aylesbury','belfast','newcastle','cambridge','southampton','liverpool','leicester','milton keynes','sheffield','gatwick','crawley','aberdeen','cardiff','cheltenham','ipswich','guildford','norwich','dundee','exeter','brighton','rickmansworth','st albans','colchester','fakenham','diss')

def evaluate(job, profile=None):
 p=dict(profile if profile is not None else setting('profile'));
 if profile is None:p.update(setting('school_grades',{}))
 title=job.get('title','').lower();description=job.get('description','').lower();text=title+' '+description
 reasons=[];unknown=[];reject=[]
 category=next((k for k,v in CATEGORIES.items() if any(re.search(r'\b'+re.escape(w),title) for w in v)),None)
 if not category and job.get('source')=='Accountancy Careers' and re.search(r'\b(graduate|trainee|aca|acca)\b',title):category='Accounting'
 if not category:reject.append('Role is outside accounting and finance')
 if re.search(r'\b(senior|manager|director|head of|principal|chief|lead)\b',title) or (re.search(r'\bcontroller\b',title) and not re.search(r'\bcredit controller\b',title)):reject.append('Experienced or leadership role')
 if re.search(r'\b(placement|school leaver|insight|penultimate|undergraduate internship|summer intern)\b',title):reject.append('Student or school-leaver programme')
 if re.search(r'\b(recruiter|software|developer|engineer|actuarial)\b',title) or ('sales' in title and 'sales ledger' not in title):reject.append('Outside graduate accounting and finance scope')
 loc=(job.get('location','')+' '+job.get('country','')).lower()
 country=job.get('country','').strip().lower()
 if country and country not in ('gb','gbr','uk','united kingdom','england','scotland','wales','northern ireland'):reject.append('Role is outside the UK')
 elif re.search(r'\b(united states|usa|canada|australia|germany|france|netherlands|singapore|dubai|new york)\b',loc):reject.append('Role is outside the UK')
 if not (re.search(r'\b(uk|gb|gbr)\b',loc) or any(w in loc for w in UK_WORDS)):unknown.append('UK location not confirmed')
 early=bool(re.search(r'\b(graduate|trainee|junior|entry.level|assistant|apprentice|apprenticeship|clerk|administrator|credit controller|bookkeeper)\b',title))
 if not early and not re.search(r'\b(no (?:prior )?experience|entry.level|recent graduate|full training|graduates welcome)\b',description):unknown.append('Entry-level suitability not confirmed')
 # Requirements are detected in sentences, rather than incidental words such as “qualified colleagues”.
 for sentence in re.split(r'[.!?\n;]',description):
  if re.search(r'\b(fully qualified|part.qualified|qualified accountant|acca qualified|aca qualified|cima qualified)\b',sentence):
   if not re.search(r'\b(study|towards|become|working with|our team|mentored|support|not required|preferred|desirable|complete the programme|pass the exams|you will become|on completion)\b',sentence):reject.append('Requires an existing professional accounting qualification')
  if re.search(r'\b(currently studying|already studying|registered (?:acca|aca)|acca student)\b',sentence) and re.search(r'\b(must|required|essential|need|you are|you will be)\b',sentence):unknown.append('Existing ACCA enrolment required or unclear')
  exp=re.search(r'\b(?:minimum(?: of)?|at least|requires?|essential|must have|need)\s*(\d+)\s*\+?\s*years?\b',sentence)
  exp=exp or re.search(r'\b(\d+)\+?\s*years?[^.!?]{0,35}\b(?:experience|required|essential)\b',sentence)
  if exp and not re.search(r'\b(preferred|desirable|not required)\b',sentence):
   required=int(exp.group(1));have=p.get('experience_years')
   if have is None:unknown.append(f'{required} years of relevant experience required; candidate experience unknown')
   elif float(have)<required:reject.append(f'Requires {required} years of relevant experience')
  if re.search(r'\b(2[:.]1|upper second|first.class degree)\b',sentence) and not re.search(r'\b(no minimum|not require|regardless|any degree|2[:.]2)\b',sentence):
   grade=p.get('classification','')
   if not grade:unknown.append('Degree classification requirement needs confirmation')
   elif grade not in ('First','2:1'):reject.append('Degree classification below stated requirement')
  if re.search(r'\b(2[:.]2|lower second)\b',sentence) and not re.search(r'\b(no minimum|not require)\b',sentence):
   grade=p.get('classification','')
   if not grade:unknown.append('Degree classification requirement needs confirmation')
   elif grade not in ('First','2:1','2:2'):reject.append('Degree classification below stated requirement')
  points=re.search(r'\b(\d{2,3})\s*(?:ucas|tariff)\s*points',sentence)
  if points and not re.search(r'\b(no minimum|not require|regardless)\b',sentence):
   have=p.get('a_level_points')
   if have is None:unknown.append('UCAS points requirement needs confirmation')
   elif int(have)<int(points.group(1)):reject.append('UCAS points below stated requirement')
  if not (re.search(r'\b(?:equivalent|btec|vocational)\b',sentence) and p.get('a_level_points') is not None) and re.search(r'\b(?:three|3) a.levels?\b',sentence) and re.search(r'\b(?:a\*.?c|a.?c|grade|equivalent)\b',sentence) and not p.get('a_level_grades_confirmed'):
   unknown.append('A-level grade requirement needs confirmation')
  years=re.search(r'(?:graduated|graduating|graduate)\s+(?:in|between|during)\s+(20\d\d)(?:\s*(?:and|to|[-–])\s*(20\d\d))?',sentence)
  if years:
   year=p.get('graduation_year')
   if not year:unknown.append('Graduation year restriction needs confirmation')
   elif not int(years.group(1))<=int(year)<=int(years.group(2) or years.group(1)):reject.append('Outside stated graduation window')

 from .school_requirements import check
 school_reject,school_unknown=check(description,p);reject.extend(school_reject);unknown.extend(school_unknown)
 # Job boards also advertise paid training packages as vacancies.
 if re.search(r'(training course and fees apply|course fees (?:apply|of|payable)|(?:you|candidates?|applicants?) (?:must |will |have to )?pay.{0,40}(?:course|training|fees)|one.off cost|refund.{0,30}(?:course|training)|job guarantee upon completion)',text):reject.append('Paid training package rather than an employed job')
 if re.search(r'(?:essential.{0,100}previous experience|previous experience.{0,100}(?:essential|required)|minimum.{0,15}\d+\s*months?.{0,50}experience|seeking an experienced)',text) and p.get('experience_years') is None:
  unknown.append('Relevant professional experience requirement needs confirmation')
 closing=deadline_date(job.get('deadline',''))
 if closing and closing<date.today():reject.append('Application deadline has passed')
 study=bool(re.search(r'\b(study support|study leave|funded.{0,30}(?:acca|aca|cima)|(?:acca|aca|cima).{0,40}(?:support|fund|training)|professional qualification|training contract)\b',text))
 if category:reasons.append(category+' role')
 if early:reasons.append('Graduate / trainee / junior entry route')
 if study:reasons.append('Professional study support mentioned')
 if p.get('relocate'):reasons.append('Nationwide relocation accepted')
 return {'state':'filtered' if reject else 'needs_check' if unknown else 'eligible', 'category':category or 'Other',
  'reasons':list(dict.fromkeys(reasons)), 'requirements':list(dict.fromkeys(reject+unknown)), 'study_support':study,'score':70+20*study+10*early, 'school_requirements': 'Unconfirmed school requirements' if school_unknown else 'Below advertised GCSE minimum' if school_reject else 'No blocking GCSE requirement found in this advert'}


def displayable(decision):
 """School-grade checks remain visible and explicit; never invent candidate grades."""
 return decision['state']=='eligible' or (decision['state']=='needs_check' and bool(decision['requirements']) and all(r.startswith(('UCAS points requirement','A-level grade requirement','GCSE maths requirement','GCSE english requirement')) for r in decision['requirements']))
