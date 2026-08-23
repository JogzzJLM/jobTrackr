import re
import time
import requests
import concurrent.futures
from core.normalization import (
    normalize_company, normalize_role, normalize_url,
    extract_ats_post_id, fuzzy_roles_match, clean_company_display_name
)
from core.storage import (
    load_reported_closed_jobs, load_settings, save_settings,
    load_closed_urls_cache, mark_url_as_closed, get_active_profile
)
from core.scoring import calculate_skill_match_score, evaluate_job_for_all_profiles, is_job_relevant_for_profile
from scrapers_engine.verifier import verify_live_page_applyable
from config import update_source_status

_JOB_LOCK = concurrent.futures.ThreadPoolExecutor.__module__ and __import__('threading').Lock()

def validate_job_legitimacy(company, title, link):
    if not company or not title or not isinstance(company, str) or not isinstance(title, str):
        return False
    if not link or not isinstance(link, str) or not link.startswith("http"):
        return False
    t_lower = title.lower()
    c_lower = company.lower()
    noise_words = ["test", "demo", "sample", "undefined", "null", "placeholder", "test job", "do not apply", "dummy"]
    if any(nw in t_lower for nw in noise_words) or any(nw in c_lower for nw in noise_words):
        return False
    return True

def is_any_profile_relevant(title, location="", company=""):
    """
    Checks if a job is relevant for at least one profile or general search.
    """
    from core.storage import get_all_profiles
    profiles = get_all_profiles()
    for p in profiles:
        if is_job_relevant_for_profile(title, company, location, profile=p):
            return True
    return False

def add_discovered_job(discovered_list, job_id, company, title, location, link, source, source_url=None, department=""):
    if not validate_job_legitimacy(company, title, link):
        return False

    closed_urls = load_closed_urls_cache()
    if link in closed_urls:
        return False

    norm_c = normalize_company(company)
    norm_t = normalize_role(title)
    norm_u = normalize_url(link)
    ats_id = extract_ats_post_id(link)

    closed_map = load_reported_closed_jobs()
    if (job_id in closed_map) or (norm_u in set(c.get("link") for c in closed_map.values() if c.get("link"))):
        mark_url_as_closed(link)
        return False

    for c_job in closed_map.values():
        if normalize_company(c_job.get("company")) == norm_c and (normalize_role(c_job.get("title")) == norm_t or fuzzy_roles_match(title, c_job.get("title"))):
            mark_url_as_closed(link)
            return False

    if not verify_live_page_applyable(link):
        return False

    if not source_url:
        source_url = link

    active_profile = get_active_profile()
    active_score = calculate_skill_match_score(title, company, location, profile=active_profile)
    profile_scores = evaluate_job_for_all_profiles(title, company, location)

    clean_comp = clean_company_display_name(company)

    with _JOB_LOCK:
        for item in discovered_list:
            item_url = normalize_url(item.get("link", ""))
            item_ats = extract_ats_post_id(item.get("link", ""))
            item_c = normalize_company(item.get("company"))
            item_t = normalize_role(item.get("title"))

            is_match = False
            if ats_id and item_ats and ats_id == item_ats:
                is_match = True
            elif norm_u and item_url and norm_u == item_url:
                is_match = True
            elif norm_c and item_c == norm_c and (norm_t == item_t or fuzzy_roles_match(title, item.get("title"))):
                is_match = True

            if is_match:
                if "sources" not in item:
                    item["sources"] = [item.get("source", "Discovered API")]
                if source not in item["sources"]:
                    item["sources"].append(source)
                if any(ats in link.lower() for ats in ["greenhouse", "lever", "ashby", "smartrecruiters"]):
                    item["link"] = link
                    item["source_url"] = source_url
                item["match_score"] = active_score
                item["profile_scores"] = profile_scores
                if department and not item.get("department"):
                    item["department"] = department
                return False

        entry = {
            "id": job_id,
            "company": clean_comp,
            "title": title,
            "location": location if location else "UK / Remote",
            "department": department if department else "",
            "link": link,
            "source": source,
            "sources": [source],
            "source_url": source_url,
            "match_score": active_score,
            "profile_scores": profile_scores,
            "date_found": time.strftime("%Y-%m-%d %H:%M")
        }
        discovered_list.insert(0, entry)
        return True

def extract_and_register_ats_company(url):
    if not url or not isinstance(url, str):
        return
    settings = load_settings()
    gh_match = re.search(r'greenhouse\.io/([^/]+)', url, re.IGNORECASE)
    if gh_match:
        comp = gh_match.group(1).lower()
        if comp not in settings.get("greenhouse_companies", []):
            settings.setdefault("greenhouse_companies", []).append(comp)
            save_settings(settings)
            print(f"  [ATS Auto-Register] ➕ Added '{comp}' to Greenhouse target list")
        return

    lev_match = re.search(r'jobs\.lever\.co/([^/]+)', url, re.IGNORECASE)
    if lev_match:
        comp = lev_match.group(1).lower()
        if comp not in settings.get("lever_companies", []):
            settings.setdefault("lever_companies", []).append(comp)
            save_settings(settings)
            print(f"  [ATS Auto-Register] ➕ Added '{comp}' to Lever target list")
        return

    ash_match = re.search(r'jobs\.ashbyhq\.com/([^/]+)', url, re.IGNORECASE)
    if ash_match:
        comp = ash_match.group(1).lower()
        if comp not in settings.get("ashby_companies", []):
            settings.setdefault("ashby_companies", []).append(comp)
            save_settings(settings)
            print(f"  [ATS Auto-Register] ➕ Added '{comp}' to Ashby target list")
        return

# ================= ATS SCRAPERS =================

def scrape_greenhouse(company_slug, discovered_list):
    """Fetches jobs from Greenhouse public JSON API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"
    new_jobs = 0
    try:
        resp = requests.get(url, timeout=6)
        if resp.status_code != 200:
            return 0
        data = resp.json()
        jobs = data.get("jobs", [])
        for j in jobs:
            title = j.get("title", "")
            job_id = f"gh_{company_slug}_{j.get('id')}"
            link = j.get("absolute_url", "")
            loc = (j.get("location", {}) or {}).get("name", "Remote / Flexible")
            dept = ""
            departments = j.get("departments", [])
            if departments and isinstance(departments, list):
                dept = departments[0].get("name", "")

            if not is_any_profile_relevant(title, loc, company_slug):
                continue

            if add_discovered_job(discovered_list, job_id, company_slug.capitalize(), title, loc, link, "Greenhouse API", department=dept):
                new_jobs += 1
    except Exception:
        pass
    return new_jobs

def scrape_lever(company_slug, discovered_list):
    """Fetches jobs from Lever public JSON API."""
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    new_jobs = 0
    try:
        resp = requests.get(url, timeout=6)
        if resp.status_code != 200:
            return 0
        postings = resp.json()
        if not isinstance(postings, list):
            return 0
        for p in postings:
            title = p.get("text", "")
            p_id = p.get("id", "")
            job_id = f"lev_{company_slug}_{p_id}"
            link = p.get("hostedUrl", "")
            cats = p.get("categories", {}) or {}
            loc = cats.get("location", "Remote / Flexible")
            dept = cats.get("department", "")

            if not is_any_profile_relevant(title, loc, company_slug):
                continue

            if add_discovered_job(discovered_list, job_id, company_slug.capitalize(), title, loc, link, "Lever API", department=dept):
                new_jobs += 1
    except Exception:
        pass
    return new_jobs

def scrape_ashby(company_slug, discovered_list):
    """Fetches jobs from Ashby public JSON API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
    new_jobs = 0
    try:
        resp = requests.get(url, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            jobs = data.get("jobs", [])
            for j in jobs:
                title = j.get("title", "")
                j_id = j.get("id", "")
                job_id = f"ash_{company_slug}_{j_id}"
                link = j.get("jobUrl", f"https://jobs.ashbyhq.com/{company_slug}/{j_id}")
                loc = j.get("locationName", "Remote / Flexible")
                dept = j.get("department", "")

                if not is_any_profile_relevant(title, loc, company_slug):
                    continue

                if add_discovered_job(discovered_list, job_id, company_slug.capitalize(), title, loc, link, "Ashby API", department=dept):
                    new_jobs += 1
    except Exception:
        pass
    return new_jobs

def scrape_smartrecruiters(company_slug, discovered_list):
    """Fetches jobs from SmartRecruiters public JSON API."""
    url = f"https://api.smartrecruiters.com/v1/companies/{company_slug}/postings?limit=100"
    new_jobs = 0
    try:
        resp = requests.get(url, timeout=6)
        if resp.status_code != 200:
            return 0
        data = resp.json()
        postings = data.get("content", [])
        for p in postings:
            title = p.get("name", "")
            p_id = p.get("id", "")
            job_id = f"sr_{company_slug}_{p_id}"
            link = f"https://jobs.smartrecruiters.com/{company_slug}/{p_id}"
            loc_data = p.get("location", {}) or {}
            city = loc_data.get("city", "")
            country = loc_data.get("country", "")
            loc = f"{city}, {country}".strip(", ") or "Remote / Flexible"
            dept = (p.get("department") or {}).get("label", "")

            if not is_any_profile_relevant(title, loc, company_slug):
                continue

            if add_discovered_job(discovered_list, job_id, company_slug.capitalize(), title, loc, link, "SmartRecruiters API", department=dept):
                new_jobs += 1
    except Exception:
        pass
    return new_jobs

def run_all_ats_scrapers(discovered_list):
    """Runs all registered ATS scrapers concurrently."""
    settings = load_settings()
    gh_comps = settings.get("greenhouse_companies", [])
    lev_comps = settings.get("lever_companies", [])
    ash_comps = settings.get("ashby_companies", [])
    sr_comps = settings.get("smartrecruiters_companies", [])

    total_new = 0

    print(f"🚀 [ATS Scraper Engine] Starting multi-sector crawl across {len(gh_comps)} GH, {len(lev_comps)} Lever, {len(ash_comps)} Ashby, {len(sr_comps)} SmartRecruiters companies...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = []
        for c in gh_comps:
            futures.append(executor.submit(scrape_greenhouse, c, discovered_list))
        for c in lev_comps:
            futures.append(executor.submit(scrape_lever, c, discovered_list))
        for c in ash_comps:
            futures.append(executor.submit(scrape_ashby, c, discovered_list))
        for c in sr_comps:
            futures.append(executor.submit(scrape_smartrecruiters, c, discovered_list))

        for f in concurrent.futures.as_completed(futures):
            try:
                res = f.result()
                total_new += res
            except Exception:
                pass

    update_source_status("Greenhouse API", f"🟢 Active • {len(gh_comps)} Target Companies Online")
    update_source_status("Lever API", f"🟢 Active • {len(lev_comps)} Target Companies Online")
    update_source_status("Ashby API", f"🟢 Active • {len(ash_comps)} Target Companies Online")
    update_source_status("SmartRecruiters API", f"🟢 Active • {len(sr_comps)} Target Companies Online")

    print(f"✅ [ATS Scraper Engine] Ingestion complete. Discovered {total_new} new jobs.")
    return total_new
