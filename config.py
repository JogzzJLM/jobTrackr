"""
Config facade and logging tee for jobTrackr (Port 5001).
"""
import os
import sys
import time
import threading

from core.storage import (
    PORT, HP_STREAM_TAILSCALE_IP, PROFILES_FILE, SEEN_JOBS_FILE,
    SEEN_EMAILS_FILE, DISCOVERED_JOBS_FILE, SETTINGS_FILE,
    CLOSED_KB_FILE, REPORTED_CLOSED_FILE, CLOSED_URLS_CACHE_FILE,
    HIDDEN_JOBS_FILE, SCRAPER_STATUS_FILE, PENDING_EMAILS_FILE,
    load_json_safe, atomic_write_json,
    load_profiles_data, save_profiles_data, get_all_profiles,
    get_active_profile_id, set_active_profile_id, get_active_profile,
    get_profile_by_id, save_or_update_profile, delete_profile,
    load_settings, save_settings,
    load_reported_closed_jobs, save_reported_closed_jobs,
    load_closed_urls_cache, save_closed_urls_cache, mark_url_as_closed,
    load_hidden_jobs, save_hidden_jobs, hide_job,
    load_pending_email_updates, save_pending_email_updates,
    add_pending_email_update, remove_pending_email_update,
    load_scraper_status, save_scraper_status,
    load_seen_jobs, save_seen_jobs, mark_job_as_seen,
    load_discovered_jobs, save_discovered_jobs
)

from core.kb import (
    DEFAULT_CLOSED_PHRASES, load_closed_keywords_kb, save_closed_keywords_kb,
    extract_generic_closure_phrases
)

from core.normalization import (
    COMPANY_ALIASES, COMPANY_DISPLAY_NAMES, clean_company_display_name,
    normalize_company, normalize_role, stem_word, fuzzy_roles_match,
    normalize_url, extract_ats_post_id, deduplicate_job_list
)

from core.scoring import (
    calculate_skill_match_score, evaluate_job_for_all_profiles,
    is_job_relevant_for_profile
)

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "jog_jobtrackr_alerts")
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")
GOOGLE_SHEET_WEBHOOK_URL = os.getenv("GOOGLE_SHEET_WEBHOOK_URL", "")
HEALTHCHECKS_PING_URL = os.getenv("HEALTHCHECKS_PING_URL", "")

SCRAPER_STATUS = load_scraper_status()

_LOG_LOCK = threading.Lock()
SCRAPER_LOGS = []
_in_tee = threading.local()

class TerminalStreamTee:
    """Tee stream capturing sys.stdout & sys.stderr for rolling web terminal console."""
    def __init__(self, original_stream):
        self.original_stream = original_stream
        self.line_buffer = ""

    def write(self, buf):
        if getattr(_in_tee, 'active', False):
            self.original_stream.write(buf)
            return

        try:
            _in_tee.active = True
            self.original_stream.write(buf)
            self.original_stream.flush()

            self.line_buffer += str(buf)
            while "\n" in self.line_buffer:
                line, self.line_buffer = self.line_buffer.split("\n", 1)
                clean_line = line.strip()
                if clean_line:
                    with _LOG_LOCK:
                        timestamp = time.strftime("%H:%M:%S")
                        if not clean_line.startswith("[") and not clean_line.startswith("┌") and not clean_line.startswith("├") and not clean_line.startswith("└") and not clean_line.startswith("│") and not clean_line.startswith("  "):
                            formatted = f"[{timestamp}] {clean_line}"
                        else:
                            formatted = clean_line
                        SCRAPER_LOGS.append(formatted)
                        if len(SCRAPER_LOGS) > 800:
                            SCRAPER_LOGS.pop(0)
        except Exception:
            pass
        finally:
            _in_tee.active = False

    def flush(self):
        try:
            self.original_stream.flush()
        except Exception:
            pass

if not getattr(sys, '_terminal_tee_installed', False):
    sys.stdout = TerminalStreamTee(sys.stdout)
    sys.stderr = TerminalStreamTee(sys.stderr)
    sys._terminal_tee_installed = True

def add_scraper_log(msg):
    print(msg)

def get_scraper_logs():
    with _LOG_LOCK:
        return list(SCRAPER_LOGS)

def clear_scraper_logs():
    global SCRAPER_LOGS
    with _LOG_LOCK:
        SCRAPER_LOGS = []

def update_scraper_status(key, value):
    with _LOG_LOCK:
        SCRAPER_STATUS[key] = value
        save_scraper_status(SCRAPER_STATUS)

def update_source_status(source_name, status_str):
    with _LOG_LOCK:
        if "source_status" not in SCRAPER_STATUS:
            SCRAPER_STATUS["source_status"] = {}
        SCRAPER_STATUS["source_status"][source_name] = status_str
        save_scraper_status(SCRAPER_STATUS)
