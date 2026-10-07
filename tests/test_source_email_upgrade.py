import json
import os
import tempfile
import unittest
from unittest.mock import patch,Mock
os.environ.setdefault('DATA_DIR',tempfile.mkdtemp(prefix='jt-upgrade-test-'))
from jobtrackr import store,mail,events,sheets,normalization,discovery,verifier,network

class ReliableMailboxTests(unittest.TestCase):
 def client(self):
  client=Mock();client.list.return_value=('OK',[b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"']);client.select.return_value=('OK',[b'200']);client.response.return_value=('UIDVALIDITY',[b'upgrade-1']);return client
 def test_all_mail_includes_archived_messages_and_stays_readonly(self):
  client=self.client();client.uid.return_value=('OK',[b''])
  with patch.dict(os.environ,{'JOBTRACKR_IMAP_USER':'archive-test@example.org','JOBTRACKR_IMAP_PASSWORD':'test'}),patch('jobtrackr.mail.imaplib.IMAP4_SSL',return_value=client):mail.poll()
  client.select.assert_called_once_with('"[Gmail]/All Mail"',readonly=True);client.store.assert_not_called();client.expunge.assert_not_called()
 def test_batch_checkpoint_does_not_skip_messages_after_one_hundred(self):
  client=self.client();uids=b' '.join(str(i).encode() for i in range(1,206));calls=[]
  def uid(command,*args):
   calls.append((command,args))
   if command=='search':return 'OK',[uids]
   n=args[0].decode();return 'OK',[(b'h',f'Message-ID: <batch-{n}>\r\nFrom: other@example.org\r\nSubject: Hello\r\n\r\nUnrelated message'.encode())]
  client.uid.side_effect=uid
  with patch.dict(os.environ,{'JOBTRACKR_IMAP_USER':'batch-test@example.org','JOBTRACKR_IMAP_PASSWORD':'test','JOBTRACKR_MAIL_BATCH_SIZE':'200'}),patch('jobtrackr.mail.imaplib.IMAP4_SSL',return_value=client):mail.poll();mail.poll()
  self.assertEqual(sum(cmd=='fetch' for cmd,_ in calls),205);self.assertEqual(calls[201],('search',(None,'UID','201:*')));self.assertEqual(store.setting('mail_health')['remaining'],0)
  self.assertTrue(all(args[-1]=='(BODY.PEEK[])' for cmd,args in calls if cmd=='fetch'))
 def test_failed_fetch_retains_checkpoint_and_retries_missing_message(self):
  client=self.client();fetches=[];failed=[False]
  def uid(command,*args):
   if command=='search':return 'OK',[b'1 2 3']
   n=args[0];fetches.append(n)
   if n==b'2' and not failed[0]:failed[0]=True;return 'NO',[]
   return 'OK',[(b'h',b'From: other@example.org\r\nSubject: Hello\r\n\r\nHi')]
  client.uid.side_effect=uid
  with patch.dict(os.environ,{'JOBTRACKR_IMAP_USER':'retry-test@example.org','JOBTRACKR_IMAP_PASSWORD':'test'}),patch('jobtrackr.mail.imaplib.IMAP4_SSL',return_value=client):mail.poll();self.assertFalse(store.setting('mail_health')['connected']);mail.poll()
  self.assertEqual(fetches,[b'1',b'2',b'2',b'3']);self.assertTrue(store.setting('mail_health')['connected'])
 def test_message_id_deduplicates_across_folder_uid_reset(self):
  client=self.client();client.uid.side_effect=lambda cmd,*args:('OK',[b'10']) if cmd=='search' else ('OK',[(b'h',b'Message-ID: <same-across-folders>\r\nFrom: other@example.org\r\nSubject: Hello\r\n\r\nHi')])
  with patch.dict(os.environ,{'JOBTRACKR_IMAP_USER':'duplicate-test@example.org','JOBTRACKR_IMAP_PASSWORD':'test'}),patch('jobtrackr.mail.imaplib.IMAP4_SSL',return_value=client):
   mail.poll();client.response.return_value=('UIDVALIDITY',[b'upgrade-2']);mail.poll()
  import hashlib
  account=hashlib.sha256(b'imap.gmail.com|duplicate-test@example.org').hexdigest()[:16]
  with store.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM email_updates WHERE id LIKE ?',(account+':%',)).fetchone()[0],1)
 def test_configured_folder_is_respected(self):
  with patch.dict(os.environ,{'JOBTRACKR_IMAP_FOLDER':'Applications'}):self.assertEqual(mail.mailbox_folder(self.client()),'Applications')

class ActualEventTests(unittest.TestCase):
 def record(self,name,status='Interview',subject='Second interview invitation'):
  jid=store.application_from_email(name,'Round Test '+name,'Graduate Accountant');store.update_job(jid,{'status':status})
  with store.connect() as c:c.execute('INSERT INTO email_updates VALUES(?,?,?,?)',(name,json.dumps({'subject':subject,'snippet':'We invite you to your second interview. Interview on 2026-10-15.','status':status}),'',store.now()))
  return jid
 def test_explicit_second_interview_retained_and_exported_without_status_change(self):
  jid=self.record('round-two');job=next(j for j in store.jobs() if j['id']==jid);mail.advance_update('round-two',job,'Interview')
  self.assertEqual(store.application_events(jid)[0]['label'],'Interview 2');self.assertEqual(next(j for j in store.jobs() if j['id']==jid)['status'],'Interview')
  self.assertEqual(next(row for row in sheets.snapshot() if row['id']==jid)['stages'],['Applied','Interview','Interview 2'])
  self.assertFalse(store.application_events(jid)[0]['date_suggestions'][0]['confirmed'])
 def test_repeated_poll_of_message_does_not_duplicate_event(self):
  jid=self.record('round-once');job=next(j for j in store.jobs() if j['id']==jid);mail.advance_update('round-once',job,'Interview');mail.advance_update('round-once',job,'Interview');self.assertEqual(len(store.application_events(jid)),1)
 def test_old_email_records_evidence_without_reopening_rejected_job(self):
  jid=self.record('closed-round',status='Rejected');job=next(j for j in store.jobs() if j['id']==jid);mail.advance_update('closed-round',job,'Interview');self.assertEqual(next(j for j in store.jobs() if j['id']==jid)['status'],'Rejected');self.assertEqual(len(store.application_events(jid)),1)
 def test_final_assessment_and_no_invented_round(self):
  self.assertEqual(events.details({'subject':'Final assessment invitation'},'Assessment')['label'],'Assessment (final)');self.assertEqual(events.details({'subject':'Interview invitation'},'Interview')['label'],'Interview')
 def test_sheet_ack_does_not_hide_future_same_stage_round(self):
  jid=self.record('ack-round',subject='Interview invitation');sheets.import_applications([{'id':jid,'company':'Round Test ack-round','title':'Graduate Accountant','stages':['Applied','Interview']}]);job=next(j for j in store.jobs() if j['id']==jid);mail.advance_update('ack-round',job,'Interview');self.assertEqual(next(row for row in sheets.snapshot() if row['id']==jid)['stages'],['Applied','Interview','Interview 2'])

class DuplicateAndSourceTests(unittest.TestCase):
 def test_native_application_id_merges_board_and_employer(self):
  a={'link':'https://board.example/jobs/123','apply_url':'https://rsm-careers.tal.net/vx/appcentre/opp/178?instant=apply'};b={'link':'https://www.rsmuk.com/careers/jobs/ec178','apply_url':'https://rsm-careers.tal.net/vx/mobile/appcentre/opp/178/apply/en-GB'};self.assertTrue(normalization.finance_same_listing(a,b))
 def test_distinct_employer_tenant_or_intake_is_not_merged(self):
  a={'link':'https://one.tal.net/vx/opp/178'};b={'link':'https://two.tal.net/vx/opp/178'};self.assertFalse(normalization.finance_same_listing(a,b))
  a={'company':'Firm','title':'Graduate Accountant 2026','location':'London','description':'Identical '*100};b={**a,'title':'Graduate Accountant 2027'};self.assertFalse(normalization.finance_same_listing(a,b))
 def test_identical_advert_merges_but_different_location_stays_separate(self):
  a={'company':'Firm','title':'Graduate Accountant','location':'London','description':'Identical description '*30,'link':'https://board.example/jobs/a'};b={**a,'link':'https://firm.example/jobs/b'};self.assertTrue(normalization.finance_same_listing(a,b));self.assertFalse(normalization.finance_same_listing(a,{**b,'location':'Leeds'}))
 def test_upsert_preserves_record_id_status_and_employer_link(self):
  a={'id':'merge-employer','company':'Merge Firm','title':'Graduate Accountant','location':'London','description':'Identical job description '*30,'link':'https://firm.example/jobs/merge','route_type':'Direct employer'};store.upsert(a);store.update_job(a['id'],{'status':'Applied'})
  self.assertFalse(store.upsert({**a,'id':'merge-board','link':'https://board.example/jobs/merge','route_type':'Job board advert'}));saved=next(j for j in store.jobs() if j['id']==a['id']);self.assertEqual(saved['link'],a['link']);self.assertEqual(saved['status'],'Applied');self.assertIn('https://board.example/jobs/merge',saved['alternate_links'])
 def test_kpmg_extracts_actual_title_location_and_specific_url(self):
  response=Mock();response.text='<div class="col"><h3>Graduate Audit - ACA Watford Autumn 2027</h3><p class="vacancy-location"><b>Watford</b></p><a class="view-job-description" href="/Vacancies/GraduateAudit/123">View role</a></div>'
  with patch('jobtrackr.discovery.get',return_value=response):rows=discovery.kpmg()
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['company'],'KPMG');self.assertEqual(rows[0]['location'],'Watford');self.assertTrue(rows[0]['link'].startswith('https://www.kpmgcareers.co.uk/Vacancies/'))
 def test_salary_extracted_from_structured_listing(self):
  self.assertEqual(verifier.salary_text({'currency':'GBP','value':{'minValue':25000,'maxValue':30000,'unitText':'YEAR'}}),'£25,000 – £30,000 / year')
 def test_application_link_does_not_follow_recommended_jobs(self):
  from bs4 import BeautifulSoup
  soup=BeautifulSoup('<main><div class="similar-jobs"><a href="https://jobs.smartrecruiters.com/Other/1/apply">Apply</a></div><a href="https://rsm-careers.tal.net/vx/opp/178?instant=apply">Apply</a></main>','html.parser')
  self.assertIn('/opp/178',verifier.application_link(soup,'https://rsmuk.com/jobs/178'))
 def test_rate_limit_stops_further_requests_during_cooldown(self):
  response=Mock();response.status_code=429;response.headers={'Retry-After':'60'}
  with patch('jobtrackr.network.requests.get',return_value=response) as get:
   network.get('https://ratelimit.unit.test/job/1')
   with self.assertRaises(__import__('requests').RequestException):network.get('https://ratelimit.unit.test/job/2')
   self.assertEqual(get.call_count,1)

class ApplicationRouteMatchingTests(unittest.TestCase):
 def test_email_matches_employer_native_id_even_when_public_listing_is_on_another_site(self):
  job={'id':'route-email','title':'Graduate Audit','company':'RSM','status':'Applied','link':'https://www.rsmuk.com/careers/jobs/ec178','apply_url':'https://rsm-careers.tal.net/vx/appcentre/opp/178?instant=apply'}
  match=mail.match_message('Interview invitation','hr@rsmuk.com','We invite you to interview. https://rsm-careers.tal.net/vx/mobile/opp/178/apply/en-GB',[job])
  self.assertTrue(match.certain);self.assertEqual(match.job_id,job['id'])
 def test_failure_between_evidence_insert_and_stage_update_can_resume(self):
  jobid=store.application_from_email('resume-evidence','Resume Firm','Graduate Accountant')
  with store.connect() as c:c.execute('INSERT INTO email_updates VALUES(?,?,?,?)',('resume-evidence',json.dumps({'subject':'Interview invitation'}),'',store.now()))
  with patch('jobtrackr.mail.store.update_job',side_effect=RuntimeError('interrupted')):
   with self.assertRaises(RuntimeError):mail.apply_update('resume-evidence',jobid,'Interview')
  mail.apply_update('resume-evidence',jobid,'Interview');self.assertEqual(next(j for j in store.jobs() if j['id']==jobid)['status'],'Interview');self.assertEqual(len(store.application_events(jobid)),1)

class AsdaEmployerFeedTests(unittest.TestCase):
 def test_known_reed_crosspost_is_merged_into_exact_employer_requisition(self):
  page={'total':1,'jobPostings':[{'title':'Finance Graduate Programme','locationsText':'Asda House','externalPath':'/job/Asda-House/Finance-Graduate-Programme_R-106204'}]}
  with patch('jobtrackr.discovery.requests.post') as post:
   post.return_value.json.return_value=page;row=discovery.asda()[0]
  self.assertEqual(row['company'],'Asda');self.assertIn('asda.wd103.myworkdayjobs.com',row['link']);self.assertEqual(normalization.vacancy_identity(row),'wd:asda:r-106204')
  self.assertTrue(normalization.finance_same_listing(row,{'link':'https://www.reed.co.uk/jobs/finance-graduate-programme/57377624'}))

class KpmgDistinctRouteTests(unittest.TestCase):
 def test_information_link_is_not_application_destination(self):
  from bs4 import BeautifulSoup
  soup=BeautifulSoup('<a href="/graduate/applying-to-kpmg/">Applying to KPMG</a><a href="https://student.kpmgcareers.co.uk/graduates2027/Login.aspx?intake_year=2027&amp;programme=Graduate&amp;business_area=Audit&amp;location=Watford&amp;start_date=Autumn">Apply for role</a>','html.parser')
  self.assertIn('student.kpmgcareers.co.uk',verifier.application_link(soup,'https://www.kpmgcareers.co.uk/Vacancies/test/123'))
 def test_different_kpmg_locations_with_login_query_remain_distinct(self):
  base={'company':'KPMG','description':'Role details '*40,'title':'Graduate Audit','route_type':'Direct employer'}
  for city in ('Watford','Leeds'):
   row={**base,'id':'kpmg-route-'+city,'location':city,'link':'https://www.kpmgcareers.co.uk/Vacancies/test/'+city,'apply_url':'https://student.kpmgcareers.co.uk/graduates2027/Login.aspx?intake_year=2027&programme=Graduate&business_area=Audit&location='+city+'&start_date=Autumn'}
   self.assertTrue(store.upsert(row))
  self.assertEqual(len([j for j in store.jobs() if j['id'].startswith('kpmg-route-')]),2)
 def test_polluted_aliases_and_generic_guide_do_not_merge_roles(self):
  a={'link':'https://www.kpmgcareers.co.uk/Vacancies/Audit/one','apply_url':'https://www.kpmgcareers.co.uk/graduate/applying-to-kpmg/','alternate_links':['https://www.kpmgcareers.co.uk/Vacancies/Tax/two']}
  b={'link':'https://www.kpmgcareers.co.uk/Vacancies/Tax/two','apply_url':a['apply_url']}
  self.assertFalse(normalization.finance_same_listing(a,b))
