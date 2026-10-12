import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('DATA_DIR',tempfile.mkdtemp(prefix='jobtrackr-system-fixes-'))
from jobtrackr import store,mail,sheets,alerts,discovery
from jobtrackr.health import health

def record(id,**extra):
 job={'id':id,'company':'Audit Firm','title':'Graduate Accountant','location':'London','link':'https://example.org/jobs/'+id,**extra}
 store.upsert(job);return job

class SystemFixTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory(prefix='jobtrackr-regression-')
  self.previous_db=store.DB;store.DB=Path(self.directory.name)/'jobs.sqlite3';store.init()
 def tearDown(self):
  store.DB=self.previous_db;self.directory.cleanup()
 def test_existing_id_can_change_destination_without_losing_history(self):
  j=record('id-refresh');store.update_job(j['id'],{'status':'Applied'})
  store.upsert({**j,'link':'https://example.org/jobs/updated','title':'Graduate Audit Trainee'})
  saved=next(j for j in store.jobs() if j['id']=='id-refresh')
  assert saved['status']=='Applied' and saved['link'].endswith('/updated')
  assert len(store.history(j['id']))==2
 
 def test_deleted_sheet_row_does_not_reappear(self):
  j=record('sheet-delete');store.update_job(j['id'],{'status':'Applied'})
  row=next(r for r in sheets.snapshot() if r['id']==j['id'])
  sheets.import_applications([row]);sheets.import_applications([])
  assert not any(r['id']==j['id'] for r in sheets.snapshot())
  assert next(x for x in store.jobs() if x['id']==j['id'])['status']=='New'
  assert store.history(j['id'])
 
 def test_sheet_deletion_cannot_drop_a_concurrent_new_interview_round(self):
  j=record('sheet-race');store.update_job(j['id'],{'status':'Interview'})
  row=next(r for r in sheets.snapshot() if r['id']==j['id']);sheets.import_applications([row])
  cursors=store.history_cursors();store.update_job(j['id'],{'status':'Interview'},stage_label='Interview 2')
  sheets.import_applications([], {j['id']:'Interview'},cursors)
  assert next(r for r in sheets.snapshot() if r['id']==j['id'])['stages'][-1]=='Interview 2'
 
 def test_health_reports_failed_scan_while_preserving_liveness(self):
  store.set_setting('scan',{'running':False,'error':'IntegrityError'});result=health()
  assert not result['ok'] and result['alive'] and result['status']=='degraded'
  assert any('Discovery' in x for x in result['issues'])
 
 def test_programme_alerts_combine_locations_and_retry_without_duplicates(self):
  jobs=[record('alert-london',route_type='Direct employer',title='Audit Graduate - London September 2027'),record('alert-bristol',route_type='Direct employer',title='Audit Graduate - Bristol September 2027',location='Bristol')]
  alerts.new_listings(jobs);alerts.new_listings(jobs)
  with store.connect() as c:
   rows=c.execute("SELECT payload FROM outbox WHERE id LIKE 'programme:%' AND delivered IS NULL").fetchall()
  matches=[json.loads(r[0]) for r in rows if '2 locations' in json.loads(r[0])['title']]
  assert len(matches)==1 and 'London' in matches[0]['message'] and 'Bristol' in matches[0]['message']
 
 def test_one_broken_job_does_not_abort_following_jobs(self):
  jobs=[{'id':'broken','company':'Audit Firm','title':'Graduate Accountant','location':'London','link':'https://example.org/jobs/broken'},{'id':'good','company':'Other Firm','title':'Graduate Accountant','location':'London','link':'https://example.org/jobs/good'}]
  original=store.upsert
  def save(job):
   if job['link'].endswith('/broken'):raise ValueError('Invalid record')
   return original(job)
  with patch.object(discovery,'sources',return_value=[('Test',lambda:jobs)]),patch.object(discovery,'enrich',side_effect=lambda j:(j,{'state':'verified'})),patch.object(store,'upsert',side_effect=save),patch.object(alerts,'flush'):
   assert discovery.scan()
  assert any(j['link'].endswith('/good') for j in store.jobs())
  assert any(e['error']=='ValueError' for e in store.setting('scan')['errors'])
 
 
 def test_outcome_contract_matches_applicationtrackr_rules(self):
  cases=[('Thank you for your application. We are unable to progress your application further.','Rejected'),('Regarding your application: we will not be moving forward with your application.','Rejected'),('Regarding your application: we are unable to offer technical support today.',''),('Your application has not been unsuccessful; we invite you to your interview.','Interview'),('Your interview is scheduled. Previous email: your application was unsuccessful.','Interview'),('If your application is unsuccessful, contact recruitment.',''),('Thank you for your application.','Applied')]
  for text,status in cases:assert mail.classify(text)==status
 
