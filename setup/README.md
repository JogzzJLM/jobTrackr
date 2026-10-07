# One-time stack setup

The website is for jobs and applications. Private eligibility settings and mailbox credentials stay in stack environment variables. Existing stored candidate data is preserved.

- `SCRAPER_INTERVAL_SECONDS=300`: matches ApplicationTrackr's five-minute default. Scans never overlap.
- `JOBTRACKR_PROFILE_JSON`: optional JSON object for first-time private eligibility configuration (classification, graduation_year, uk_citizen, relocate, acca_status, experience_years, a_level_points, a_level_grades_confirmed, gcse_maths, gcse_english). Omit to keep the existing private settings. Never commit a real candidate's data.
- `JOBTRACKR_IMAP_USER`: application Gmail address.
- `JOBTRACKR_IMAP_PASSWORD`: Google app password; enable two-step verification first. See https://support.google.com/accounts/answer/185833. Messages are read without marking them read.
- `JOBTRACKR_IMAP_FOLDER`: optional explicit folder; otherwise Gmail All Mail is detected so archived mail is covered. Spam and Trash are excluded.
- `JOBTRACKR_MAIL_LOOKBACK_DAYS=90`: one-time initial history window (14–365 days). Saved UID checkpoints then capture all new received messages.
- `JOBTRACKR_MAIL_BATCH_SIZE=200`: bounded batches; backlog continues every ten seconds, normal checks every five minutes. Fetch failures retain the checkpoint and retry. Message IDs prevent repeats across folders and UID resets.
- `NTFY_TOPIC=applicationtrackr_alerts_har`.

## Optional Google Sheet

Use a separate spreadsheet. Add `google-sheet.gs` through Extensions → Apps Script. Set Script Property `JOBTRACKR_SPREADSHEET_ID` to the spreadsheet ID from its URL and `JOBTRACKR_SYNC_TOKEN` to a long random secret. The web app opens this exact spreadsheet by ID; an active spreadsheet is not available in web app execution. Deploy as a web app that executes as your account, accessible to Anyone (each request still requires the secret).

Set stack variables `GOOGLE_SHEET_EDIT_URL` to the spreadsheet link, `GOOGLE_SHEET_WEBHOOK_URL` to the deployment's `/exec` URL and `GOOGLE_SHEET_SYNC_TOKEN` to the same secret. Recreate the stack once.

An Open Sheet shortcut opens the exact synced JobTrackr tab. Only recorded applications are synced; discovered and dismissed vacancies are excluded. Columns A–L contain Company, Role and Stage 1–10; hidden column M holds the record ID. Other tabs and columns after M are preserved.

Sync runs every minute in both directions. Edit stages in JobTrackr or the Sheet; manual Sheet rows are imported as application records. Concurrent local stage updates are retained for the next sync. Keep the Sheet private. Notes and personal reminders are not part of the website or Sheet sync.

Application email evidence is retained in Activity, including explicit numbered/final interview and assessment rounds. Such labels sync to the stage columns and diagram. Suggested dates are shown as unconfirmed text from the email; no ambiguous date is silently scheduled. Old backfill events do not send new-stage alerts.

Job cards distinguish direct employers from recruiters and job-board adverts. Direct employer routes rank first by default. A live agency advert is not proof of an unnamed client vacancy. Access challenges and rate limits remain unconfirmed and retry; they are never treated as successful verification or proof of closure.
