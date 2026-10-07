import json
import os
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('DATA_DIR',tempfile.mkdtemp(prefix='jobtrackr-audit-'))
from jobtrackr import store, mail, alerts, sheets, verifier

class AuditFixTests(unittest.TestCase):
 def test_pending_review_survives_more_than_one_hundred_resolved_messages(self):
  with store.connect() as c:
   c.execute('INSERT OR REPLACE INTO email_updates VALUES(?,?,?,?)',('old-pending','{}','','2000-01-01'))
   for i in range(110):c.execute('INSERT OR REPLACE INTO email_updates VALUES(?,?,?,?)',(f'new-matched-{i}','{}','matched:job','2026-10-07'))
  self.assertIn('old-pending',[row['id'] for row in mail.updates() if not row['resolved']])
 def test_redirect_to_different_specific_job_is_not_verified(self):
  post={'@type':'JobPosting','title':'Graduate Tax Programme','description':'Training and study support.'}
  with patch('jobtrackr.verifier.requests.get') as get:
   get.return_value.status_code=200;get.return_value.url='https://example.org/jobs/tax'
   get.return_value.text='<script type="application/ld+json">'+json.dumps(post)+'</script>'
   self.assertEqual(verifier._check('https://example.org/jobs/audit','Graduate Audit Programme')['state'],'unknown')
   self.assertEqual(verifier._check('https://example.org/jobs/tax','2027 Tax Graduate Programme')['state'],'verified')
 def test_workday_wrong_title_is_not_verified(self):
  with patch('jobtrackr.verifier._workday',return_value={'state':'verified','title':'Marketing Coordinator'}):
   self.assertEqual(verifier._check('https://example.org/jobs/audit','Graduate Accountant')['state'],'unknown')
 def test_personal_reminders_are_never_sent_including_previously_queued(self):
  alerts.enqueue('reminder:audit-test','Old reminder','Old message')
  with store.connect() as c:c.execute("UPDATE outbox SET delivered='test-isolation' WHERE id NOT LIKE 'reminder:%'")
  with patch('jobtrackr.alerts.requests.post') as publish:alerts.scheduled();self.assertEqual(publish.call_count,0)
 def test_sheet_receipt_does_not_revert_concurrent_email_update(self):
  job={'id':'audit-race','title':'Graduate Accountant','company':'Audit Test','link':'https://example.org/jobs/audit-race'}
  store.upsert(job);store.update_job(job['id'],{'status':'Applied'})
  sent=next(row for row in sheets.snapshot() if row['id']==job['id'])
  def receipt(*args,**kwargs):
   store.update_job(job['id'],{'status':'Interview'})
   from unittest.mock import Mock
   response=Mock();response.json.return_value={'ok':True,'count':len(kwargs['json']['jobs']),'layout':'applications-v3','applications':kwargs['json']['jobs']}
   return response
  with patch.dict(os.environ,{'GOOGLE_SHEET_WEBHOOK_URL':'https://example.org/sync','GOOGLE_SHEET_SYNC_TOKEN':'test-token'}),patch('jobtrackr.sheets.requests.post',side_effect=receipt):
   self.assertTrue(sheets.sync())
  self.assertEqual(next(j for j in store.jobs() if j['id']==job['id'])['status'],'Interview')
  self.assertEqual(next(r for r in store.setting('sheet_sent_rows',[]) if r['id']==job['id'])['stages'],['Applied'])
  self.assertEqual(next(r for r in sheets.snapshot() if r['id']==job['id'])['stages'],['Applied','Interview'])
