import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('DATA_DIR',tempfile.mkdtemp(prefix='jobtrackr-school-test-'))
from jobtrackr import store,alerts,discovery,network
from jobtrackr.eligibility import evaluate
from jobtrackr.source_policy import excluded,blocked_url,visible_jobs

class SchoolSourceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.previous=store.DB;store.DB=Path(self.temp.name)/'jobs.sqlite3';store.init()
  self.profile={**store.DEFAULT_PROFILE,'classification':'First','gcse_english':'3','gcse_maths':'4','a_level_points':144,'post16_qualification':'BTEC DD'}
 def tearDown(self):store.DB=self.previous;self.temp.cleanup()
 def job(self,description='',**values):return {'id':'test','company':'Firm','title':'Trainee Accountant','location':'London, UK','country':'GB','link':'https://employer.example/jobs/1','description':description,'status':'New','verification':{'state':'verified'},**values}
 def test_english_and_maths_grades(self):
  for description in ['GCSEs at grade 4 in Maths and English.','GCSEs at grade C in English and Mathematics.','GCSE Maths and English at grades 9–4.','GCSEs at A*-C including English and Maths.','GCSE English Language grade C/4 and Maths grade C/4.']:
   with self.subTest(description=description):
    result=evaluate(self.job(description),self.profile);self.assertEqual(result['state'],'filtered');self.assertTrue(any('english' in x for x in result['requirements']));self.assertFalse(any('maths requires' in x for x in result['requirements']))
 def test_different_subject_minima(self):
  result=evaluate(self.job('GCSE English at grade 3 and Mathematics at grade 5.'),self.profile)
  self.assertTrue(any('maths requires grade 5' in x for x in result['requirements']));self.assertFalse(any('english requires' in x for x in result['requirements']))
 def test_numeric_or_letter_equivalence(self):
  self.assertEqual(evaluate(self.job('GCSE Maths grade 5 or B and GCSE English Language grade 5 or B.'),self.profile)['state'],'filtered')
 def test_optional_or_absent_minimum(self):
  for text in ['No minimum GCSE grades are required.','GCSE English at grade 4 is preferred.','A degree in accounting and funded ACCA training.']:
   self.assertEqual(evaluate(self.job(text),self.profile)['state'],'eligible')
 def test_unstated_grade_is_unconfirmed(self):
  result=evaluate(self.job('GCSE Maths and English required.'),self.profile);self.assertEqual(result['state'],'needs_check')
 def test_degree_does_not_waive_gcse(self):
  self.assertEqual(evaluate(self.job('First-class degree and GCSE English grade 4 required.'),self.profile)['state'],'filtered')
 def test_btec_points_are_used_without_inventing_a_levels(self):
  result=evaluate(self.job('120 UCAS points required. Three A-levels at grades A-C or equivalent qualifications.'),self.profile);self.assertEqual(result['state'],'eligible')
 def test_private_saved_grades_override_old_environment_profile(self):
  store.set_setting('school_grades',{'gcse_english':'3','gcse_maths':'4','a_level_points':144})
  self.assertEqual(evaluate(self.job('GCSE English at grade 4 required.'))['state'],'filtered')
 def test_host_matching_is_precise(self):
  for url in ['https://reed.co.uk/jobs/1','https://www.reed.co.uk/jobs/1','https://apply.reed.co.uk/1']:self.assertTrue(blocked_url(url))
  self.assertFalse(blocked_url('https://employer.example/jobs/reed'))
 def test_old_records_cannot_reappear_in_discovery(self):
  self.assertEqual(visible_jobs([self.job(link='https://www.reed.co.uk/jobs/1')]),[])
 def test_old_ineligible_verified_record_is_hidden_immediately(self):
  store.set_setting('school_grades',{'gcse_english':'3','gcse_maths':'4'})
  self.assertEqual(visible_jobs([self.job('GCSE English grade 4 required.')]),[])
 def test_application_history_is_preserved_without_reed_routes(self):
  rows=visible_jobs([self.job(status='Applied',link='https://www.reed.co.uk/jobs/1',apply_url='https://apply.reed.co.uk/1',alternate_links=['https://www.reed.co.uk/jobs/1'])]);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'Applied');self.assertNotIn('reed.co.uk',str(rows))
 def test_network_does_not_request_reed(self):
  with patch('jobtrackr.network.requests.get') as get:
   with self.assertRaises(Exception):network.get('https://www.reed.co.uk/jobs/1')
   get.assert_not_called()
 def test_reed_cannot_publish_new_alert(self):
  alerts.new_listings([self.job(link='https://reed.co.uk/jobs/1')])
  with store.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
 def test_sources_do_not_include_reed(self):self.assertFalse(any('reed' in name.lower() for name,_ in discovery.sources()))

 def test_employer_funded_course_fees_are_not_paid_training_adverts(self):
  self.assertEqual(evaluate(self.job('A fully-funded professional qualification, paid study leave and all course fees covered.'),self.profile)['state'],'eligible')
  self.assertEqual(evaluate(self.job('You must pay course fees of £1,000 before placement.'),self.profile)['state'],'filtered')
