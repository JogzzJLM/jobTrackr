import os,tempfile,unittest
from unittest.mock import patch,Mock
os.environ.setdefault('DATA_DIR',tempfile.mkdtemp(prefix='jobtrackr-employer-tests-'))
from jobtrackr import employer_feeds,verifier,store
from jobtrackr.eligibility import evaluate

class EmployerFeedTests(unittest.TestCase):
 def response(self,data=None,text=''):
  r=Mock();r.json.return_value=data;r.text=text;r.status_code=200;return r
 def test_pinpoint_includes_requirements_and_employer_destination(self):
  data={'data':[{'title':'Trainee Accountant','url':'https://firm.pinpointhq.com/en/postings/abc','description':'Full training','skills_knowledge_expertise':'GCSE English grade 4 required','location':{'city':'London','province':'UK'}}]}
  with patch('jobtrackr.discovery.get',return_value=self.response(data)):
   row=employer_feeds.pinpoint('Firm','https://firm.pinpointhq.com')[0]
  self.assertIn('grade 4',row['description']);self.assertEqual(row['country'],'GB');self.assertEqual(row['company'],'Firm')
 def test_teamtailor_uses_actual_country_instead_of_assuming_uk(self):
  text='<rss xmlns:tt="https://teamtailor.com/locations"><channel><item><title>Junior Accountant</title><link>https://firm.example/jobs/1</link><description>Full training</description><tt:locations><tt:location><tt:city>Paris</tt:city><tt:country>France</tt:country></tt:location></tt:locations></item></channel></rss>'
  with patch('jobtrackr.discovery.get',return_value=self.response(text=text)):
   row=employer_feeds.teamtailor('Firm','https://firm.example')[0]
  self.assertEqual(row['country'],'France');self.assertEqual(evaluate(row,store.DEFAULT_PROFILE)['state'],'filtered')
 def test_oracle_search_excludes_overseas_and_deduplicates_keywords(self):
  data={'items':[{'TotalJobsCount':2,'requisitionList':[{'Id':'1','Title':'Finance Assistant','PrimaryLocationCountry':'GB','PrimaryLocation':'London'},{'Id':'2','Title':'Finance Assistant','PrimaryLocationCountry':'US','PrimaryLocation':'Boston'}]}]}
  with patch('jobtrackr.discovery.get',return_value=self.response(data)):
   rows=employer_feeds.oracle('Firm','example.oraclecloud.com','CX',queries=('finance','accounts'))
  self.assertEqual(len(rows),1);self.assertIn('/job/1',rows[0]['link'])
 def test_oracle_verification_uses_complete_qualifications(self):
  data={'Id':'123','Title':'Finance Assistant','ExternalDescriptionStr':'<p>Finance team</p>','ExternalQualificationsStr':'<p>GCSE English grade 4 required</p>','PrimaryLocation':'London','PrimaryLocationCountry':'GB'}
  with patch('jobtrackr.verifier.network.get',return_value=self.response(data)):
   result=verifier._oracle('https://example.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/123')
  self.assertEqual(result['state'],'verified');self.assertIn('GCSE English',result['description'])
 def test_oracle_does_not_verify_the_wrong_requisition(self):
  with patch('jobtrackr.verifier.network.get',return_value=self.response({'Id':'456','Title':'Finance Assistant','ExternalDescriptionStr':'Full training'})):
   self.assertIsNone(verifier._oracle('https://example.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/123'))
 def test_nhs_extracts_the_actual_trust_location_and_deadline(self):
  text='<li data-test="search-result"><h2><a data-test="search-result-job-title" href="/candidate/jobadvert/ABC?keyword=finance">Finance Assistant</a></h2><div data-test="search-result-location"><h3>Trust Name<div class="location-font-size">London</div></h3></div><div data-test="search-result-closingDate"><strong>30 October 2026</strong></div></li>'
  with patch('jobtrackr.discovery.get',return_value=self.response(text=text)):
   row=employer_feeds.nhs('finance assistant')[0]
  self.assertEqual(row['company'],'Trust Name');self.assertEqual(row['location'],'London');self.assertEqual(row['deadline'],'2026-10-30')
 def test_junior_accounting_titles_are_not_filtered_as_sales_or_senior_management(self):
  for title in ['Sales Ledger Assistant','Credit Controller','Payroll Administrator','Accounts Payable Clerk']:
   with self.subTest(title=title):self.assertEqual(evaluate({'title':title,'location':'London','description':'Full training provided.'},store.DEFAULT_PROFILE)['state'],'eligible')
 def test_new_routes_still_reject_required_finance_experience(self):
  result=evaluate({'title':'Credit Controller','location':'London','description':'Minimum 2 years experience required.'},store.DEFAULT_PROFILE)
  self.assertEqual(result['state'],'needs_check');self.assertIn('experience',str(result['requirements']))
 def test_financial_controller_is_still_an_experienced_role(self):
  self.assertEqual(evaluate({'title':'Financial Controller','location':'London'},store.DEFAULT_PROFILE)['state'],'filtered')
