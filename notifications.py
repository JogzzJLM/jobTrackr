import requests
from config import NTFY_TOPIC, HP_STREAM_TAILSCALE_IP, PORT

def send_notification(title, message, tags="briefcase", priority=3, sound="default", click_url=None):
    """
    Sends a push notification via ntfy.sh.
    """
    if not NTFY_TOPIC:
        return False

    if not click_url:
        click_url = f"http://{HP_STREAM_TAILSCALE_IP}:{PORT}/"

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {
        "Title": title,
        "Priority": str(priority),
        "Tags": tags,
        "Click": click_url
    }
    if sound:
        headers["Sound"] = sound

    try:
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=5)
        return resp.status_code == 200
    except Exception as e:
        print(f"⚠️ Notification notice: {e}")
        return False

def generate_apple_calendar_ics(company, role, stage_name, event_date_str=""):
    """
    Generates standard .ics calendar format string for interview scheduling.
    """
    import time
    dtstamp = time.strftime("%Y%m%dT%H%M%SZ")
    summary = f"{stage_name}: {company} - {role}"
    description = f"jobTrackr scheduled event for {company} ({role}) stage: {stage_name}."

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//jobTrackr//Job Tracking Engine//EN
BEGIN:VEVENT
UID:{int(time.time()*1000)}@jobtrackr.local
DTSTAMP:{dtstamp}
DTSTART:{dtstamp}
SUMMARY:{summary}
DESCRIPTION:{description}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""
    return ics_content
