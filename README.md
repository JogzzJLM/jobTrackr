# JobTrackr — Accounting & Finance

Independent UK finance-graduate discovery and application tracker based on ApplicationTrackr's evidence-based verifier, URL normalization and responsive design principles.

## Candidate and scope

Candidate education, graduation year, grades, citizenship, awards and work history are configured in private runtime data, not committed in the repository. Never assume professional qualifications, exemptions or school grades. The generic default targets graduate accounting and finance routes.


## Features

Discover, shortlist, dismiss/restore, application stages (Applied, Assessment, Interview, Offer, Rejected, Withdrawn), notes, activity history, dated follow-ups, custom job links, and CSV export. Persistent SQLite database in `/data/jobtrackr.sqlite3`; no Sheets required. Original profiles/listing files are retained. Legacy listings are only candidates for new verification, never blindly treated as eligible.

Desktop and mobile automatically adapt; no compact-mode switch. Twelve jobs per page, search/category/study-support filters, deadline or fit sorting, full expandable descriptions.

## Discovery and notifications

Scans every 30 minutes and at startup: BDO employer Workday feed (pagination), RSM published job index, Sanctuary graduate jobs (pagination), ACCA Careers and DWP Find a Job, Accountancy Careers, graduate-jobs.com, and public Greenhouse/Lever/SmartRecruiters employer feeds. Blocked or missing sources are reported as unavailable, not successful. Employer pages require specific job evidence. Network errors and access challenges are unconfirmed, not closures.

Accounting/audit/tax/finance/payroll entry routes accepted; senior/qualified/student-only/unrelated roles filtered. Required grades, prior experience, enrolment and graduation windows are checked; unanswered school grades appear explicitly on live graduate listings; other unanswered requirements go to Check requirements. Study support is ranked higher, not invented. Suitability is evidence-based and cannot guarantee employer acceptance.

ntfy topic: `applicationtrackr_alerts_har`. First crawl sends one summary to avoid a backlog flood. Subsequent newly verified roles get individual alerts containing employer, title, location, salary/deadline when published, study support and listing link. Durable outbox, failed-publish retries and event deduplication. Follow-ups, 1/3-day deadline warnings, and an 18:00 Europe/London summary when new jobs exist. Delivery acceptance is checked by ntfy receipt; subscribers must enable notifications on their devices.

## Run

`pip install -r requirements.txt` then `python app.py`, or deploy docker-compose.yml in Portainer using the existing `jobtrackr_data` volume. Port 5001. Set `DATA_DIR`, `APP_BASE_URL`, `NTFY_TOPIC`, optional `NTFY_BASE_URL`/`NTFY_TOKEN`. Local QA only: `DISABLE_SCHEDULER=1`, `NOTIFICATIONS_DISABLED=1`.

Tests: `python -m unittest discover -s tests -p test_finance_tracker.py -v`.

Applications are opened on the employer website and submitted by the applicant. This version does not auto-submit. Gmail email tracking is opt-in and requires the brother's own account setup; Google Sheets can be added later if wanted.

## Research checked 6 October 2026

- [ACCA trainee accountant routes and study support](https://www.accaglobal.com/gb/en/study-with-acca/your-career/sectors-industries-roles/trainee-accountant.html)
- [BDO graduate recruitment](https://careers.bdo.co.uk/en/search-jobs/graduate/)
- [RSM Bristol audit graduate, September 2027](https://www.rsmuk.com/careers/jobs/ec178): employer explicitly requires UCAS points and an honours degree; those are separate from degree classification.
- [ACCA graduate study/exemptions information](https://www.accaglobal.com/gb/en/study-with-acca/getting-started/plan-your-study-and-exam-journey/accounting-or-finance-graduate.html). Do not infer the individual's exemptions from university accreditation alone.

## Gmail setup

Email matching is implemented but disabled until `JOBTRACKR_IMAP_USER` and `JOBTRACKR_IMAP_PASSWORD` are configured separately in Portainer. `JOBTRACKR_IMAP_HOST` defaults to `imap.gmail.com`. The brother must create his own Google app password; do not paste it into chat. Google requires two-step verification: [Google official app-password guide](https://support.google.com/accounts/answer/185833).

The listener checks the last 14 days (up to 100 latest messages) every five minutes using read-only IMAP and BODY.PEEK, without marking messages read. Exact job URLs or distinct company/title matches update stages; ambiguous messages go to Email updates for manual job assignment. It avoids backwards stage changes, ignores marketing, never submits applications and does not publish email text to ntfy. Credentials are environment-only and omitted from API responses. Live mailbox connectivity cannot be verified until credentials are supplied.
