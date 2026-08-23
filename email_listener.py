import os
import json
import re
import imaplib
import email
from email.header import decode_header
import time
from datetime import datetime, timedelta
from config import (
    GMAIL_USER, GMAIL_APP_PASS, SEEN_EMAILS_FILE,
    HP_STREAM_TAILSCALE_IP, PORT, update_source_status,
    add_pending_email_update, load_pending_email_updates,
    load_json_safe, atomic_write_json, get_all_profiles,
    get_active_profile
)
from notifications import send_notification
from sheets import update_google_sheet_via_webhook, get_detailed_applications, normalize_company

GENERIC_DOMAINS = {
    "gmail", "yahoo", "hotmail", "outlook", "icloud", "proton", "mail",
    "googlemail", "live", "msn", "me", "comcast", "aol"
}

def load_seen_emails():
    if os.path.exists(SEEN_EMAILS_FILE):
        try:
            with open(SEEN_EMAILS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_seen_emails(seen):
    try:
        with open(SEEN_EMAILS_FILE, "w") as f:
            json.dump(list(seen), f)
    except Exception:
        pass

def extract_company_name(subject, from_sender, body_text=""):
    """Intelligently extracts the company name from email subject, sender domain, or body."""
    sub_match = (
        re.search(r"\b(?:at|with|for|to)\s+([A-Z][a-zA-Z0-9\s\&]+?)(?=\s+[\-\–\|]|[\.\,\!\?]|$)", subject, re.IGNORECASE) or
        re.search(r"([A-Z][a-zA-Z0-9\s\&]+?)\s+Application\b", subject)
    )
    if sub_match:
        c_name = sub_match.group(1).strip()
        if len(c_name) > 2 and c_name.lower() not in ["your", "the", "a", "an", "our", "us"]:
            return c_name.title()

    domain_match = re.search(r"@([a-zA-Z0-9\-]+)\.", from_sender)
    if domain_match:
        dom = domain_match.group(1).lower()
        if dom not in GENERIC_DOMAINS and len(dom) > 2:
            return dom.capitalize()

    return "Application Company"

def classify_email_stage(text):
    """Determines application status from email content."""
    text_lower = text.lower()

    offer_keywords = [
        "offer of employment", "pleased to offer", "congratulations on your offer",
        "job offer", "formal offer", "offer letter", "we would like to offer"
    ]
    if any(k in text_lower for k in offer_keywords):
        return "Offer"

    interview_keywords = [
        "interview", "schedule a call", "invitation to interview", "next step", "speaking with",
        "first round", "final round", "assessment centre", "assessment center", "video call"
    ]
    if any(k in text_lower for k in interview_keywords):
        return "Interview"

    oa_keywords = [
        "online test", "coding assessment", "hackerrank", "codility", "hirevue",
        "online assessment", "numerical reasoning", "logic test", "take-home"
    ]
    if any(k in text_lower for k in oa_keywords):
        return "Online Assessment"

    rejection_keywords = [
        "regret to inform", "unable to offer", "not moving forward", "other candidates",
        "unsuccessful", "high volume of applications", "after careful consideration",
        "decided not to proceed", "will not be proceeding"
    ]
    if any(k in text_lower for k in rejection_keywords):
        return "Rejected"

    applied_keywords = [
        "thank you for applying", "application received", "received your application",
        "confirming your application", "application submitted", "successfully submitted"
    ]
    if any(k in text_lower for k in applied_keywords):
        return "Applied"

    update_keywords = [
        "application status", "update regarding your", "regarding your application"
    ]
    if any(k in text_lower for k in update_keywords):
        return "Application Update"

    return None

def handle_incoming_email_update(company_name, detected_stage, subject="", from_sender="", body_text=""):
    """
    Intelligently maps incoming email status updates (Rejected, Interview, OA, Offer) across user profiles:
    - If 1 exact application exists for company_name: updates that application directly on Google Sheets.
    - If >1 application exists for company_name: saves a pending update for user resolution on dashboard.
    - If 0 applications exist: creates a pending update offering 1-click assignment to a new role.
    """
    profiles = get_all_profiles()
    norm_c = normalize_company(company_name)

    all_matching_apps = []
    for prof in profiles:
        apps = get_detailed_applications(profile=prof, force_refresh=True)
        for a in apps:
            if normalize_company(a.get("company", "")) == norm_c:
                all_matching_apps.append({
                    "profile_id": prof.get("id"),
                    "profile_name": prof.get("name"),
                    "company": a.get("company", company_name),
                    "role": a.get("role", "Target Role"),
                    "current_stage": a.get("current_stage", "Applied")
                })

    if len(all_matching_apps) == 1:
        match = all_matching_apps[0]
        exact_role = match["role"]
        exact_company = match["company"]
        target_prof = next((p for p in profiles if p.get("id") == match["profile_id"]), None)

        update_google_sheet_via_webhook(exact_company, detected_stage, role=exact_role, resolve_sequential=True, profile=target_prof)
        send_notification(
            title=f"Update Logged: {exact_company} ({detected_stage})",
            message=f"Auto-updated status to {detected_stage} for '{exact_role}' ({target_prof.get('name') if target_prof else ''}).",
            tags="check-mark",
            priority=3,
            sound="chime"
        )
        print(f"  ├── ✅ MATCHED 1-EXACT APPLICATION: {exact_company} -> {exact_role} ({detected_stage})")
        return True

    else:
        # Multiple matches or unlogged application -> Ambiguous Resolution Banner
        update_id = f"pending_{int(time.time()*1000)}"
        pending_obj = {
            "id": update_id,
            "company": company_name,
            "stage": detected_stage,
            "subject": subject[:90] if subject else f"{company_name} Email Update",
            "date_received": time.strftime("%Y-%m-%d %H:%M"),
            "options": all_matching_apps
        }
        add_pending_email_update(pending_obj)

        send_notification(
            title=f"⚠️ Action Required: {company_name} ({detected_stage})",
            message=f"Received status update for '{company_name}'. Please select the target role on jobTrackr dashboard.",
            tags="warning",
            priority=4,
            sound="default",
            click_url=f"http://{HP_STREAM_TAILSCALE_IP}:{PORT}/"
        )
        print(f"  ├── ⚠️ AMBIGUOUS EMAIL SAVED: {company_name} ({len(all_matching_apps)} candidates)")
        return False

def check_gmail_inbox():
    if not GMAIL_USER or not GMAIL_APP_PASS:
        update_source_status("Gmail Inbox Listener", "⚪ Idle • Gmail credentials not configured in environment")
        return 0

    seen_emails = load_seen_emails()
    new_events = 0

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASS)
        mail.select("INBOX")

        # Search emails from past 7 days
        since_date = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{since_date}")')

        if status != "OK" or not messages[0]:
            mail.logout()
            update_source_status("Gmail Inbox Listener", "🟢 Active • Universal Email Auto-Tracker (0 unread updates)")
            return 0

        email_ids = messages[0].split()
        for e_id in email_ids[-30:]:  # Check last 30 messages
            e_id_str = e_id.decode("utf-8")
            if e_id_str in seen_emails:
                continue

            status, msg_data = mail.fetch(e_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = ""
            raw_sub = msg.get("Subject", "")
            if raw_sub:
                decoded_chunks = decode_header(raw_sub)
                for chunk, encoding in decoded_chunks:
                    if isinstance(chunk, bytes):
                        subject += chunk.decode(encoding or "utf-8", errors="ignore")
                    else:
                        subject += str(chunk)

            from_sender = msg.get("From", "")
            body_text = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body_text = part.get_payload(decode=True).decode(errors="ignore")
                        break
            else:
                body_text = msg.get_payload(decode=True).decode(errors="ignore")

            full_text = f"{subject} {body_text}"
            detected_stage = classify_email_stage(full_text)

            if detected_stage:
                company = extract_company_name(subject, from_sender, body_text)
                print(f"\n📧 [Gmail Event] Detected '{detected_stage}' from {from_sender} | Subject: {subject[:60]}")
                handle_incoming_email_update(company, detected_stage, subject=subject, from_sender=from_sender, body_text=body_text)
                new_events += 1

            seen_emails.add(e_id_str)

        save_seen_emails(seen_emails)
        mail.logout()
        update_source_status("Gmail Inbox Listener", f"🟢 Active • Checked {len(email_ids)} recent messages")
        return new_events

    except Exception as e:
        print(f"⚠️ Gmail Listener Notice: {e}")
        update_source_status("Gmail Inbox Listener", f"⚠️ Notice • {str(e)[:40]}")
        return 0

def email_listener_loop(interval_seconds=300):
    """Periodic background runner for Gmail IMAP listener."""
    while True:
        try:
            check_gmail_inbox()
        except Exception:
            pass
        time.sleep(interval_seconds)
