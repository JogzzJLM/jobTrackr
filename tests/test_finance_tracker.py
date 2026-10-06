import importlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='jobtrackr-test-')
from jobtrackr import store, alerts
from jobtrackr.eligibility import evaluate
from jobtrackr.verifier import _check
from jobtrackr.discovery import enrich

class FinanceTests(unittest.TestCase):
 def job(self,**kwargs):return {'id':'test','title':'Graduate Accountant','company':'Firm','location':'London, UK','link':'https://example.org/jobs/graduate-accountant','description':'Full training and funded ACCA study support.',**kwargs}
 def test_canonical_link_is_navigable_and_preserves_case(self):
  from jobtrackr.discovery import candidate
  j=candidate('Firm','Graduate Accountant','UK','https://www.Example.org/Jobs/ABC?utm_source=test','Employer')
  self.assertEqual(j['link'],'https://www.Example.org/Jobs/ABC')
 def test_graduate_eligible_and_study_prioritised(self):
  result=evaluate(self.job());self.assertEqual(result['state'],'eligible');self.assertTrue(result['study_support'])
 def test_first_class_confirmed(self):self.assertEqual(evaluate(self.job(description='A minimum 2:1 degree.'),{**store.DEFAULT_PROFILE,'classification':'First'})['state'],'eligible')
 def test_senior_filtered(self):self.assertEqual(evaluate(self.job(title='Senior Accountant'))['state'],'filtered')
 def test_qualified_required_filtered(self):self.assertEqual(evaluate(self.job(description='You must be a fully qualified accountant.'))['state'],'filtered')
 def test_studying_towards_is_not_qualification_requirement(self):self.assertEqual(evaluate(self.job(description='Study towards becoming a qualified accountant.'))['state'],'eligible')
 def test_unknown_experience_quarantined(self):self.assertEqual(evaluate(self.job(description='A minimum of 2 years accounting experience is essential.'))['state'],'needs_check')
 def test_unknown_school_requirements_quarantined(self):self.assertEqual(evaluate(self.job(description='A minimum of 112 UCAS points. GCSEs at grade 4 in Maths and English.'))['state'],'needs_check')
 def test_school_low_grade_rejected(self):
  profile={**store.DEFAULT_PROFILE,'gcse_maths':'3','gcse_english':'5'};self.assertEqual(evaluate(self.job(description='GCSEs at grade 4 in Maths and English.'),profile)['state'],'filtered')
 def test_unrelated_role_filtered(self):self.assertEqual(evaluate(self.job(title='Graduate Software Engineer'))['state'],'filtered')
 def test_student_placement_filtered(self):self.assertEqual(evaluate(self.job(title='Finance Industrial Placement'))['state'],'filtered')
 def test_country_not_assumed(self):self.assertEqual(evaluate(self.job(location='New York, US'))['state'],'needs_check')
 def test_passed_deadline_filtered(self):self.assertEqual(evaluate(self.job(deadline='2020-01-01'))['state'],'filtered')
 def test_unknown_acca_not_claimed(self):self.assertEqual(evaluate(self.job(description='You must be currently studying ACCA.'))['state'],'needs_check')
 def test_rescrape_keeps_notes_stage_and_history(self):
  j=self.job(id='persist',link='https://example.org/jobs/persist');self.assertTrue(store.upsert(j));store.update_job('persist',{'status':'Interview','notes':'Interview Thursday','reminder':'2027-01-01'});self.assertFalse(store.upsert({**j,'description':'Updated'}));saved=next(j for j in store.jobs() if j['id']=='persist');self.assertEqual(saved['status'],'Interview');self.assertEqual(saved['notes'],'Interview Thursday');self.assertEqual(saved['reminder'],'2027-01-01');self.assertEqual(len(store.history('persist')),2)
 def test_notification_dedup_retry(self):
  alerts.enqueue('retry-test','Test','Message');alerts.enqueue('retry-test','Test','Message')
  with patch('jobtrackr.alerts.requests.post',side_effect=__import__('requests').ConnectionError):alerts.flush()
  with store.connect() as c:
   row=c.execute('SELECT * FROM outbox WHERE id=?',('retry-test',)).fetchone();self.assertIsNone(row['delivered']);self.assertEqual(row['attempts'],1);c.execute('UPDATE outbox SET next_retry=0 WHERE id=?',('retry-test',))
  with patch('jobtrackr.alerts.requests.post') as publish:
   publish.return_value.json.return_value={'id':'receipt','event':'message'};alerts.flush();alerts.flush();self.assertEqual(publish.call_count,1)
 def test_blocked_response_unknown_not_closed(self):
  with patch('jobtrackr.verifier.requests.get') as get:
   get.return_value.status_code=403;self.assertEqual(_check('https://example.org/jobs/test')['state'],'unknown')
 def test_missing_specific_evidence_not_verified(self):
  with patch('jobtrackr.verifier.requests.get') as get:
   get.return_value.status_code=200;get.return_value.url='https://example.org/jobs/test';get.return_value.text='<h1>Careers</h1><p>Explore careers</p>';self.assertEqual(_check('https://example.org/jobs/test','Graduate Accountant')['state'],'unknown')

if __name__=='__main__':unittest.main()

class EmailMatchingTests(unittest.TestCase):
 def job(self,id='a',title='Graduate Accountant',company='Example Finance'):
  return {'id':id,'title':title,'company':company,'link':'https://example.org/jobs/'+id,'status':'Applied','location':'London'}
 def test_exact_listing_match(self):
  from jobtrackr.mail import match_message
  result=match_message('Interview invitation','hr@example.org','We invite you to interview for https://example.org/jobs/a',[self.job()]);self.assertTrue(result.certain);self.assertEqual(result.job_id,'a');self.assertEqual(result.status,'Interview')
 def test_ambiguous_company_roles_review(self):
  from jobtrackr.mail import match_message
  result=match_message('Interview invitation','Example Finance recruitment','We invite you to interview for our accountant role.',[self.job(),self.job('b')]);self.assertFalse(result.certain);self.assertEqual(len(result.candidates),2)
 def test_wrong_employer_does_not_match(self):
  from jobtrackr.mail import match_message
  result=match_message('Application received','Other employer','Thank you for applying for Graduate Accountant',[self.job()]);self.assertFalse(result.certain);self.assertFalse(result.job_id)
 def test_offer_not_marketing(self):
  from jobtrackr.mail import classify
  self.assertEqual(classify('Special offer! Get 10% off today'),'');self.assertEqual(classify('We are pleased to offer you the position.'),'Offer')
 def test_unknown_school_visible_with_explicit_check(self):
  from jobtrackr.eligibility import displayable
  self.assertTrue(displayable({'state':'needs_check','requirements':['UCAS points requirement needs confirmation']}));self.assertFalse(displayable({'state':'needs_check','requirements':['Existing ACCA enrolment required or unclear']}))
