import os
import json
import threading
import time

_FILE_LOCK = threading.Lock()

PORT = 5001

PROFILES_FILE = "profiles.json"
SEEN_JOBS_FILE = "seen_jobs.json"
SEEN_EMAILS_FILE = "seen_emails.json"
DISCOVERED_JOBS_FILE = "discovered_jobs.json"
SETTINGS_FILE = "settings.json"
CLOSED_KB_FILE = "closed_keywords_kb.json"
REPORTED_CLOSED_FILE = "reported_closed_jobs.json"
CLOSED_URLS_CACHE_FILE = "closed_urls_cache.json"
HIDDEN_JOBS_FILE = "hidden_jobs.json"
SCRAPER_STATUS_FILE = "scraper_status.json"
PENDING_EMAILS_FILE = "pending_email_updates.json"

DEFAULT_PROFILES = {
    "active_profile_id": "prof_swe",
    "profiles": [
        {
            "id": "prof_swe",
            "name": "Software Engineering",
            "owner": "Default Profile",
            "industry": "Software Engineering",
            "role_keywords": [
                "software", "developer", "engineer", "backend", "frontend", "fullstack",
                "devops", "cloud", "platform", "systems", "sre", "machine learning",
                "ai", "data engineer", "infrastructure", "distributed", "security"
            ],
            "level_keywords": [
                "junior", "mid", "senior", "lead", "principal", "staff", "associate",
                "engineer", "entry", "developer"
            ],
            "exclude_keywords": [
                "intern", "unpaid", "volunteer", "marketing", "recruiter", "sales", "unpaid"
            ],
            "exclude_locations": [
                "us government", "defense tech - us", "security clearance required"
            ],
            "skills": [
                "python", "javascript", "typescript", "react", "node", "sql", "docker",
                "aws", "golang", "java", "c++", "kubernetes", "git", "linux", "rest"
            ],
            "target_locations": [
                "london", "remote", "uk", "hybrid", "united kingdom", "manchester",
                "bristol", "cambridge", "oxford", "edinburgh", "birmingham"
            ],
            "sheet_webhook_url": "",
            "sheet_csv_url": "",
            "color_accent": "#FF8000"
        },
        {
            "id": "prof_pm",
            "name": "Project & Product Management",
            "owner": "Uncle's Profile",
            "industry": "Project Management",
            "role_keywords": [
                "project manager", "program manager", "product manager", "scrum master",
                "delivery manager", "operations manager", "agile coach", "product owner",
                "technical project manager", "project coordinator", "business transformation"
            ],
            "level_keywords": [
                "junior", "mid", "senior", "lead", "principal", "head of", "director",
                "manager", "coordinator"
            ],
            "exclude_keywords": [
                "intern", "unpaid", "software engineer", "developer", "coding"
            ],
            "exclude_locations": [
                "us government", "defense tech - us"
            ],
            "skills": [
                "agile", "scrum", "jira", "prince2", "pmp", "stakeholder management",
                "kanban", "roadmapping", "confluence", "budgeting", "risk management",
                "sdlc", "governance", "waterfall"
            ],
            "target_locations": [
                "london", "remote", "uk", "hybrid", "united kingdom", "manchester",
                "birmingham", "leeds", "bristol"
            ],
            "sheet_webhook_url": "",
            "sheet_csv_url": "",
            "color_accent": "#3B82F6"
        },
        {
            "id": "prof_data",
            "name": "Data Science & Analytics",
            "owner": "Brother's Profile",
            "industry": "Data & Analytics",
            "role_keywords": [
                "data analyst", "data scientist", "data engineer", "analytics engineer",
                "bi analyst", "business intelligence", "machine learning engineer",
                "quantitative analyst", "reporting analyst", "data specialist"
            ],
            "level_keywords": [
                "junior", "mid", "senior", "lead", "principal", "analyst", "scientist",
                "engineer", "specialist"
            ],
            "exclude_keywords": [
                "intern", "unpaid"
            ],
            "exclude_locations": [
                "us government", "defense tech - us"
            ],
            "skills": [
                "python", "sql", "tableau", "power bi", "snowflake", "r", "pandas",
                "dbt", "bigquery", "spark", "looker", "excel", "etl", "machine learning"
            ],
            "target_locations": [
                "london", "remote", "uk", "hybrid", "united kingdom", "manchester",
                "edinburgh", "cambridge"
            ],
            "sheet_webhook_url": "",
            "sheet_csv_url": "",
            "color_accent": "#10B981"
        },
        {
            "id": "prof_finance",
            "name": "Finance & Business Operations",
            "owner": "Finance Profile",
            "industry": "Finance & Operations",
            "role_keywords": [
                "financial analyst", "investment analyst", "finance manager", "risk analyst",
                "accountant", "operations analyst", "commercial finance", "strategy analyst",
                "fp&a", "portfolio analyst", "credit analyst", "audit"
            ],
            "level_keywords": [
                "associate", "analyst", "senior", "manager", "lead", "director", "officer"
            ],
            "exclude_keywords": [
                "intern", "unpaid"
            ],
            "exclude_locations": [
                "us government", "defense tech - us"
            ],
            "skills": [
                "excel", "financial modeling", "accounting", "valuation", "cfa", "acca",
                "powerbi", "forecasting", "sap", "bloomberg", "variance analysis", "budgeting"
            ],
            "target_locations": [
                "london", "remote", "uk", "hybrid", "united kingdom", "london city"
            ],
            "sheet_webhook_url": "",
            "sheet_csv_url": "",
            "color_accent": "#8B5CF6"
        }
    ]
}

DEFAULT_GLOBAL_SETTINGS = {
    "greenhouse_companies": [
        "deliveroo", "cloudflare", "snyk", "monzo", "starlingbank",
        "janestreet", "optiver", "canonical", "citadel", "hudsonrivertrading",
        "palantir", "millennium", "quadrature", "samsara", "imc", "bloomberg",
        "twosigma", "jumptrading", "barclays", "wise", "checkout", "kraken",
        "stripe", "datadog", "figma", "airbnb", "uber", "hashicorp", "elastic",
        "github", "coinbase", "okta"
    ],
    "lever_companies": [
        "spotify", "revolut", "checkout", "beamng", "wayve", "palantir",
        "fiveai", "plex", "clearscore", "marsh", "figma", "kraken", "soundcloud"
    ],
    "ashby_companies": [
        "mistral", "synthesia", "multiverse", "ramp", "huggingface", "cohere",
        "notion", "scaleai", "elevenlabs", "perplexity", "replicate", "linear",
        "cursor", "resend", "causal", "veed", "retool", "postman"
    ],
    "smartrecruiters_companies": [
        "Ubisoft2", "CERN", "SquarepointCapital", "Visa", "IKEA", "Bosch", "Alstom"
    ],
    "auto_hide_applied_company_jobs": False
}

DEFAULT_SCRAPER_STATUS = {
    "last_run": "Never",
    "total_seen_jobs": 0,
    "total_discovered_jobs": 0,
    "last_new_jobs_found": 0,
    "source_status": {
        "Greenhouse API": "🟢 Active • 32 Target Companies Registered",
        "Lever API": "🟢 Active • 13 Target Companies Registered",
        "Ashby API": "🟢 Active • 18 Target Companies Registered",
        "SmartRecruiters API": "🟢 Active • 10 Target Companies Registered",
        "Gmail Inbox Listener": "🟢 Active • Universal Email Auto-Tracker"
    }
}

def atomic_write_json(filepath, data, indent=2):
    """Atomic write to JSON file using a temp file and os.replace to prevent corruption."""
    with _FILE_LOCK:
        tmp_filepath = f"{filepath}.tmp"
        try:
            with open(tmp_filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            os.replace(tmp_filepath, filepath)
        except Exception as e:
            if os.path.exists(tmp_filepath):
                try:
                    os.remove(tmp_filepath)
                except Exception:
                    pass
            print(f"⚠️ Error performing atomic JSON write to {filepath}: {e}")

def load_json_safe(filepath, default_val):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_val

# ================= PROFILES PERSISTENCE =================

def load_profiles_data():
    loaded = load_json_safe(PROFILES_FILE, None)
    if loaded and isinstance(loaded, dict) and "profiles" in loaded:
        return loaded
    # Initialize default
    atomic_write_json(PROFILES_FILE, DEFAULT_PROFILES)
    return dict(DEFAULT_PROFILES)

def save_profiles_data(data):
    atomic_write_json(PROFILES_FILE, data)

def get_all_profiles():
    data = load_profiles_data()
    return data.get("profiles", [])

def get_active_profile_id():
    data = load_profiles_data()
    return data.get("active_profile_id", "prof_swe")

def set_active_profile_id(profile_id):
    data = load_profiles_data()
    profiles = data.get("profiles", [])
    if any(p.get("id") == profile_id for p in profiles):
        data["active_profile_id"] = profile_id
        save_profiles_data(data)
        return True
    return False

def get_active_profile():
    data = load_profiles_data()
    active_id = data.get("active_profile_id", "prof_swe")
    profiles = data.get("profiles", [])
    for p in profiles:
        if p.get("id") == active_id:
            return p
    if profiles:
        return profiles[0]
    return DEFAULT_PROFILES["profiles"][0]

def get_profile_by_id(profile_id):
    profiles = get_all_profiles()
    for p in profiles:
        if p.get("id") == profile_id:
            return p
    return None

def save_or_update_profile(profile_obj):
    data = load_profiles_data()
    profiles = data.get("profiles", [])
    p_id = profile_obj.get("id")
    if not p_id:
        p_id = f"prof_{int(time.time()*1000)}"
        profile_obj["id"] = p_id

    updated = False
    for i, p in enumerate(profiles):
        if p.get("id") == p_id:
            profiles[i] = profile_obj
            updated = True
            break
    if not updated:
        profiles.append(profile_obj)

    data["profiles"] = profiles
    save_profiles_data(data)
    return profile_obj

def delete_profile(profile_id):
    data = load_profiles_data()
    profiles = data.get("profiles", [])
    if len(profiles) <= 1:
        return False  # Do not delete the only profile
    filtered = [p for p in profiles if p.get("id") != profile_id]
    if len(filtered) < len(profiles):
        data["profiles"] = filtered
        if data.get("active_profile_id") == profile_id:
            data["active_profile_id"] = filtered[0]["id"]
        save_profiles_data(data)
        return True
    return False

# ================= GLOBAL SETTINGS & DISCOVERY =================

def load_settings():
    loaded = load_json_safe(SETTINGS_FILE, None)
    if loaded and isinstance(loaded, dict):
        merged = dict(DEFAULT_GLOBAL_SETTINGS)
        merged.update(loaded)
        return merged
    return dict(DEFAULT_GLOBAL_SETTINGS)

def save_settings(data):
    atomic_write_json(SETTINGS_FILE, data)

def load_seen_jobs():
    data = load_json_safe(SEEN_JOBS_FILE, [])
    return set(data) if isinstance(data, list) else set()

def save_seen_jobs(seen_set):
    atomic_write_json(SEEN_JOBS_FILE, list(seen_set))

def mark_job_as_seen(job_id_or_url):
    seen = load_seen_jobs()
    if job_id_or_url not in seen:
        seen.add(job_id_or_url)
        save_seen_jobs(seen)

def load_discovered_jobs():
    return load_json_safe(DISCOVERED_JOBS_FILE, [])

def save_discovered_jobs(jobs_list):
    atomic_write_json(DISCOVERED_JOBS_FILE, jobs_list)

# ================= REPORTED CLOSED & URL CACHE =================

def load_reported_closed_jobs():
    return load_json_safe(REPORTED_CLOSED_FILE, {})

def save_reported_closed_jobs(closed_map):
    atomic_write_json(REPORTED_CLOSED_FILE, closed_map)

def load_closed_urls_cache():
    data = load_json_safe(CLOSED_URLS_CACHE_FILE, [])
    return set(data) if isinstance(data, list) else set()

def save_closed_urls_cache(closed_set):
    atomic_write_json(CLOSED_URLS_CACHE_FILE, list(closed_set))

def mark_url_as_closed(url):
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return
    closed = load_closed_urls_cache()
    if url not in closed:
        closed.add(url)
        save_closed_urls_cache(closed)

# ================= HIDDEN JOBS =================

def load_hidden_jobs():
    data = load_json_safe(HIDDEN_JOBS_FILE, [])
    return set(data) if isinstance(data, list) else set()

def save_hidden_jobs(hidden_set):
    atomic_write_json(HIDDEN_JOBS_FILE, list(hidden_set))

def hide_job(job_id):
    hidden = load_hidden_jobs()
    hidden.add(job_id)
    save_hidden_jobs(hidden)

# ================= PENDING EMAIL UPDATES =================

def load_pending_email_updates():
    return load_json_safe(PENDING_EMAILS_FILE, [])

def save_pending_email_updates(updates):
    atomic_write_json(PENDING_EMAILS_FILE, updates)

def add_pending_email_update(update_obj):
    updates = load_pending_email_updates()
    updates.append(update_obj)
    save_pending_email_updates(updates)

def remove_pending_email_update(update_id):
    updates = load_pending_email_updates()
    filtered = [u for u in updates if u.get("id") != update_id]
    save_pending_email_updates(filtered)
    return len(updates) - len(filtered)

# ================= SCRAPER STATUS =================

def load_scraper_status():
    loaded = load_json_safe(SCRAPER_STATUS_FILE, None)
    if loaded and isinstance(loaded, dict):
        merged = dict(DEFAULT_SCRAPER_STATUS)
        merged.update(loaded)
        return merged
    return dict(DEFAULT_SCRAPER_STATUS)

def save_scraper_status(status_dict):
    atomic_write_json(SCRAPER_STATUS_FILE, status_dict)
