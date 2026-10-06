# One-time stack setup

The website is for jobs and applications. Private eligibility settings and mailbox credentials stay in stack environment variables. Existing stored candidate data is preserved.

- `SCRAPER_INTERVAL_SECONDS=300`: matches ApplicationTrackr's five-minute default. Scans never overlap.
- `JOBTRACKR_PROFILE_JSON`: optional JSON object for first-time private eligibility configuration (classification, graduation_year, uk_citizen, relocate, acca_status, experience_years, a_level_points, gcse_maths, gcse_english). Omit to keep the existing private settings. Never commit a real candidate's data.
- `JOBTRACKR_IMAP_USER`: application Gmail address.
- `JOBTRACKR_IMAP_PASSWORD`: Google app password; enable two-step verification first. See https://support.google.com/accounts/answer/185833. Messages are read without marking them read.
- `NTFY_TOPIC=applicationtrackr_alerts_har`.

## Optional Google Sheet

Use a separate spreadsheet. Add `google-sheet.gs` through Extensions → Apps Script. Set Script Property `JOBTRACKR_SPREADSHEET_ID` to the spreadsheet ID from its URL and `JOBTRACKR_SYNC_TOKEN` to a long random secret. The web app opens this exact spreadsheet by ID; an active spreadsheet is not available in web app execution. Deploy as a web app that executes as your account, accessible to Anyone (each request still requires the secret).

Set stack variables `GOOGLE_SHEET_EDIT_URL` to the spreadsheet link, `GOOGLE_SHEET_WEBHOOK_URL` to the deployment's `/exec` URL and `GOOGLE_SHEET_SYNC_TOKEN` to the same secret. Recreate the stack once.

An Open Sheet shortcut appears when its URL is configured. Jobs and application updates mirror to the JobTrackr tab within one minute. IDs prevent duplicates; failed syncs retry. Other tabs and columns after J are preserved. This is a **one-way mirror**: change application statuses and notes in JobTrackr, not the mirrored columns. Keep this Sheet private: it includes application notes.
