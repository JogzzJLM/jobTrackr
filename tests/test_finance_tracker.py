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
 def test_country_not_assumed(self):self.assertEqual(evaluate(self.job(location='New York, US'))['state'],'filtered')
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
 def test_two_specific_urls_require_review(self):
  from jobtrackr.mail import match_message
  result=match_message('Application received','hr@example.org','Application received: https://example.org/jobs/a and https://example.org/jobs/b',[self.job(),self.job('b')]);self.assertFalse(result.certain)
 def test_tracking_parameters_do_not_break_url_match(self):
  from jobtrackr.mail import match_message
  result=match_message('Application received','hr@example.org','Application received: https://www.example.org/jobs/a/?utm_source=email',[self.job()]);self.assertEqual(result.job_id,'a');self.assertTrue(result.certain)
 def test_employer_only_updates_single_recorded_application(self):
  from jobtrackr.mail import match_message
  result=match_message('Interview invitation','Example Finance Recruitment','We invite you to interview.',[self.job()]);self.assertTrue(result.certain)
  new={**self.job(),'status':'New'};self.assertFalse(match_message('Interview invitation','Example Finance Recruitment','We invite you to interview.',[new]).certain)
 def test_ats_sender_uses_employer_signature(self):
  from jobtrackr.mail import match_message, employer_from_email
  body='Thank you for applying for Graduate Accountant.\nRSM Recruitment Team'
  self.assertEqual(employer_from_email('Application received','noreply@myworkdayjobs.com',body),'RSM')
  result=match_message('Application received','noreply@myworkdayjobs.com',body,[self.job(company='RSM UK LLP')]);self.assertTrue(result.certain)
 def test_role_ambiguity_not_resolved_by_company_alone(self):
  from jobtrackr.mail import match_message
  result=match_message('Interview invitation','Example Finance Recruitment','We invite you to interview.',[self.job(),self.job('b','Graduate Tax Trainee')]);self.assertFalse(result.certain)
 def test_offer_not_marketing(self):
  from jobtrackr.mail import classify
  self.assertEqual(classify('Special offer! Get 10% off today'),'');self.assertEqual(classify('We are pleased to offer you the position.'),'Offer')
 def test_unknown_school_visible_with_explicit_check(self):
  from jobtrackr.eligibility import displayable
  self.assertTrue(displayable({'state':'needs_check','requirements':['UCAS points requirement needs confirmation']}));self.assertFalse(displayable({'state':'needs_check','requirements':['Existing ACCA enrolment required or unclear']}))

class MailboxTests(unittest.TestCase):
 def test_mock_mailbox_read_only_and_updates_specific_job_once(self):
  from jobtrackr import mail
  job={'id':'mail-persist','company':'Example Finance','title':'Graduate Accountant','link':'https://example.org/jobs/mail-persist','location':'London'}
  store.upsert(job);store.update_job(job['id'],{'status':'Applied','notes':'Keep my notes'})
  raw=b'From: Recruitment <hr@example.org>\r\nSubject: Interview invitation\r\nContent-Type: text/plain\r\n\r\nWe invite you to interview for https://example.org/jobs/mail-persist'
  with patch.dict(os.environ,{'JOBTRACKR_IMAP_USER':'example@example.org','JOBTRACKR_IMAP_PASSWORD':'test-only'}),patch('jobtrackr.mail.imaplib.IMAP4_SSL') as connection:
   client=connection.return_value;client.response.return_value=('UIDVALIDITY',[b'991']);client.uid.side_effect=[('OK',[b'77']),('OK',[(b'header',raw)]),('OK',[b'77'])];mail.poll();mail.poll();client.select.assert_called_with('INBOX',readonly=True);self.assertEqual(client.uid.call_args_list[1].args[-1],'(BODY.PEEK[])')
  saved=next(j for j in store.jobs() if j['id']==job['id']);self.assertEqual(saved['status'],'Interview');self.assertIn('Keep my notes',saved['notes']);self.assertEqual(len(store.history(job['id'])),3)
  client.store.assert_not_called();client.expunge.assert_not_called()
  self.assertTrue(all(call.args[0] in ('search','fetch') for call in client.uid.call_args_list))
  from jobtrackr import sheets
  mirrored=next(j for j in sheets.snapshot() if j['id']==job['id']);self.assertEqual(mirrored['status'],'Interview');self.assertEqual(mirrored['stages'],['Applied','Interview'])
 def test_missing_mailbox_does_not_connect(self):
  from jobtrackr import mail
  with patch.dict(os.environ,{'JOBTRACKR_IMAP_USER':'','JOBTRACKR_IMAP_PASSWORD':''}),patch('jobtrackr.mail.imaplib.IMAP4_SSL') as connection:mail.poll();connection.assert_not_called()
  self.assertFalse(store.setting('mail_health')['connected'])

class ApplicationEmailWorkflowTests(unittest.TestCase):
 def test_missing_application_recorded_without_claiming_live_listing(self):
  from jobtrackr import mail, sheets
  event='missing-application-test';payload={'subject':'Application received','sender':'hr@example.org','snippet':'Thank you for applying','status':'Applied'}
  with store.connect() as c:c.execute('INSERT OR REPLACE INTO email_updates VALUES(?,?,?,?)',(event,json.dumps(payload),'',store.now()))
  first=store.application_from_email(event,'EY','Graduate Audit Trainee');second=store.application_from_email(event,'EY','Graduate Audit Trainee');self.assertEqual(first,second)
  mail.apply_update(event,first,'Applied');mail.apply_update(event,first,'Applied')
  job=next(j for j in store.jobs() if j['id']==first);self.assertEqual(job['status'],'Applied');self.assertEqual(job['link'],'');self.assertEqual(job['verification']['state'],'application_record');self.assertEqual(len(store.history(first)),2)
  self.assertEqual(next(j for j in sheets.snapshot() if j['id']==first)['status'],'Applied')
  other=store.application_from_email('another-email','BDO','Graduate Accountant');self.assertNotEqual(first,other)
 def test_unmatched_email_reconciled_after_job_is_discovered(self):
  from jobtrackr import mail
  event='late-discovery';payload={'subject':'Application received','sender':'recruitment@latefirm.example','snippet':'Thank you for applying for Graduate Accountant at Latefirm.','status':'Applied'}
  with store.connect() as c:c.execute('INSERT OR REPLACE INTO email_updates VALUES(?,?,?,?)',(event,json.dumps(payload),'',store.now()))
  store.upsert({'id':'late-job','company':'Latefirm','title':'Graduate Accountant','link':'https://latefirm.example/jobs/late'})
  mail.reconcile_updates();self.assertEqual(next(j for j in store.jobs() if j['id']=='late-job')['status'],'Applied')
 def test_closed_application_never_reopened_by_old_email(self):
  from jobtrackr import mail
  job_id=store.application_from_email('terminal-test','Example','Graduate Accountant');store.update_job(job_id,{'status':'Rejected'})
  with store.connect() as c:c.execute('INSERT OR REPLACE INTO email_updates VALUES(?,?,?,?)',('old-confirmation',json.dumps({'subject':'Application received'}),'',store.now()))
  job=next(j for j in store.jobs() if j['id']==job_id);mail.advance_update('old-confirmation',job,'Interview');self.assertEqual(next(j for j in store.jobs() if j['id']==job_id)['status'],'Rejected')
 def test_ignored_messages_do_not_hide_application_reviews(self):
  from jobtrackr import mail
  with store.connect() as c:
   c.execute('INSERT OR REPLACE INTO email_updates VALUES(?,?,?,?)',('review-visible',json.dumps({'subject':'Application update','status':'Applied'}),'','2026-01-01'))
   for i in range(110):c.execute('INSERT OR REPLACE INTO email_updates VALUES(?,?,?,?)',('ignored-'+str(i),'{}','ignored','2027-01-01'))
  self.assertIn('review-visible',[item['id'] for item in mail.updates()])

class SourceFallbackTests(unittest.TestCase):
 def test_workday_failure_uses_real_employer_pages(self):
  from jobtrackr.discovery import bdo_workday
  with patch('jobtrackr.discovery._bdo_workday',side_effect=__import__('requests').HTTPError),patch('jobtrackr.discovery.board',return_value=[{'title':'Graduate Accountant'}]) as fallback:
   self.assertEqual(len(bdo_workday()),1);self.assertIn('careers.bdo.co.uk',fallback.call_args.args[1])

class CanonicalEmployerTests(unittest.TestCase):
 def test_bdo_marketing_and_feed_share_employer_identity(self):
  from jobtrackr.discovery import enrich
  job={'company':'BDO','title':'Graduate Accountant','location':'London','link':'https://careers.bdo.co.uk/en/job/london/accountant/1469/1','source':'BDO graduates'}
  employer='https://bdouk.wd3.myworkdayjobs.com/BDO_Early_in_Career/job/London/Graduate_123'
  with patch('jobtrackr.discovery.verify_listing',return_value={'state':'verified','reason':'Employer description','checked_at':'now'}),patch('jobtrackr.discovery.get') as get:
   get.return_value.text='<a href="'+employer+'/apply">Apply</a><div id="job-description">Study support</div>';saved,_=enrich(job)
  self.assertEqual(saved['link'],employer);self.assertEqual(saved['verification_url'],job['verification_url'])

class DiscoveryFirstTests(unittest.TestCase):
 def test_sheet_retry_and_no_duplicate_sync_after_ack(self):
  from jobtrackr import sheets
  from requests import ConnectionError
  with patch.dict(os.environ,{'GOOGLE_SHEET_WEBHOOK_URL':'https://example.org/exec','GOOGLE_SHEET_SYNC_TOKEN':'test-only'}),patch('jobtrackr.sheets.snapshot',return_value=[{'id':'sheet-test','status':'Applied'}]):
   store.set_setting('sheet_fingerprint','')
   with patch('jobtrackr.sheets.requests.post',side_effect=ConnectionError):self.assertFalse(sheets.sync())
   self.assertEqual(store.setting('sheet_fingerprint'),'')
   with patch('jobtrackr.sheets.requests.post') as post:
    post.return_value.json.return_value={'ok':True,'count':1,'layout':'applications-v2'}
    self.assertTrue(sheets.sync());self.assertTrue(sheets.sync());self.assertEqual(post.call_count,1)
 def test_sheet_does_not_ack_partial_write(self):
  from jobtrackr import sheets
  with patch.dict(os.environ,{'GOOGLE_SHEET_WEBHOOK_URL':'https://example.org/exec','GOOGLE_SHEET_SYNC_TOKEN':'test-only'}),patch('jobtrackr.sheets.snapshot',return_value=[{'id':'partial'}]),patch('jobtrackr.sheets.requests.post') as post:
   store.set_setting('sheet_fingerprint','');post.return_value.json.return_value={'ok':True,'count':0,'layout':'applications-v2'}
   self.assertFalse(sheets.sync());self.assertEqual(store.setting('sheet_fingerprint'),'')
 def test_flow_uses_recorded_transitions_without_inventing_assessment(self):
  from jobtrackr import flow
  job={'id':'flow-test','title':'Graduate Accountant','link':'https://example.org/jobs/flow-test'}
  store.upsert(job);store.update_job(job['id'],{'status':'Applied'});store.update_job(job['id'],{'status':'Interview'})
  result=flow.counts([{'id':job['id'],'status':'Interview'}])
  self.assertEqual(result[('Applications','Applied')],1);self.assertEqual(result[('Applied','Interview')],1);self.assertNotIn(('Applied','Assessment'),result)
 def test_accountancy_custom_page_needs_apply_control(self):
  from jobtrackr.discovery import enrich
  job={'title':'Graduate Trainee','company':'Firm','location':'London, UK','link':'https://www.accountancycareers.co.uk/jobs/firm-graduate/','source':'Accountancy Careers','description':''}
  markup='<title>Graduate Trainee | Firm</title><header class="job-detailheader"><a class="logo-link" title="Firm"></a></header><section id="job-description"><div class="article-content">'+'Training in accounting. '*30+'</div></section>'
  with patch('jobtrackr.discovery.verify_listing',return_value={'state':'unknown'}),patch('jobtrackr.discovery.get') as get:
   get.return_value.text=markup;self.assertEqual(enrich(job.copy(),force=True)[1]['state'],'unknown')
   get.return_value.text=markup+'<a href="https://example.org/apply">Apply now</a>';self.assertEqual(enrich(job.copy(),force=True)[1]['state'],'verified')

 def test_enrichment_cache_reuses_page_but_not_application_notes(self):
  from jobtrackr import discovery
  job={'title':'Graduate Accountant','link':'https://example.org/jobs/cache-test','source':'Employer'}
  with patch('jobtrackr.discovery._enrich',return_value=({**job,'description':'Employer detail'}, {'state':'verified'})) as fetch:
   discovery.enrich(job,force=True)
   second,check=discovery.enrich({**job,'notes':'Current private notes'})
   self.assertEqual(fetch.call_count,1);self.assertEqual(second['notes'],'Current private notes');self.assertEqual(check['state'],'verified')

 def test_paid_training_ad_is_not_a_job(self):
  result=evaluate({'title':'Trainee Accountant','company':'Training provider','location':'London, UK','description':'Job guarantee upon completion. This is a training course and fees apply.'})
  self.assertEqual(result['state'],'filtered')
 def test_unquantified_essential_experience_is_not_assumed(self):
  result=evaluate({'title':'Finance Assistant','location':'London, UK','description':'Skills and experience essential: Previous experience in a finance assistant role.'})
  self.assertEqual(result['state'],'needs_check')

class ApplicationsOnlySheetTests(unittest.TestCase):
 def test_discovery_and_saved_roles_are_excluded(self):
  from jobtrackr import sheets
  jobs=[{'id':'new','status':'New'},{'id':'saved','status':'Saved'},{'id':'dismissed','status':'Dismissed'}]
  with patch('jobtrackr.store.jobs',return_value=jobs),patch('jobtrackr.store.history',return_value=[]):self.assertEqual(sheets.snapshot(),[])
 def test_stages_follow_actual_history_and_preserve_closed_applications(self):
  from jobtrackr import sheets
  job={'id':'a','company':'RSM','title':'Audit Graduate','status':'Rejected'}
  history=[{'event':'Status: Rejected'},{'event':'Notes or reminder updated'},{'event':'Status: Interview'},{'event':'Status: Applied'}]
  with patch('jobtrackr.store.jobs',return_value=[job]),patch('jobtrackr.store.history',return_value=history):
   row=sheets.snapshot()[0];self.assertEqual(row['stages'],['Applied','Interview','Rejected']);self.assertNotIn('notes',row)
 def test_old_sheet_endpoint_cannot_ack_new_layout(self):
  from jobtrackr import sheets
  store.set_setting('sheet_fingerprint','')
  with patch.dict(os.environ,{'GOOGLE_SHEET_WEBHOOK_URL':'https://example.org/exec','GOOGLE_SHEET_SYNC_TOKEN':'test-only'}),patch('jobtrackr.sheets.snapshot',return_value=[]),patch('jobtrackr.sheets.requests.post') as post:
   post.return_value.json.return_value={'ok':True,'count':0};self.assertFalse(sheets.sync())
