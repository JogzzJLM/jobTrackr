import time
import requests
import concurrent.futures
from config import (
    update_scraper_status, HEALTHCHECKS_PING_URL,
    load_discovered_jobs, save_discovered_jobs,
    load_seen_jobs, save_seen_jobs,
    load_reported_closed_jobs,
    load_closed_urls_cache, mark_url_as_closed,
    get_active_profile
)
from core.normalization import deduplicate_job_list, normalize_url, normalize_company, normalize_role
from core.scoring import calculate_skill_match_score, evaluate_job_for_all_profiles
from scrapers_engine.ats_scrapers import run_all_ats_scrapers
from scrapers_engine.verifier import verify_live_page_applyable

def recheck_existing_open_jobs_for_closure(discovered_list=None):
    """
    Sweeps through discovered jobs and tests URLs.
    Purges expired or closed jobs to ensure 0 dead links.
    """
    if discovered_list is None:
        discovered_list = load_discovered_jobs()

    if not discovered_list:
        return 0

    print(f"🧹 [Closure Audit] Verifying {len(discovered_list)} discovered opportunities for live applyability...")
    closed_map = load_reported_closed_jobs()
    closed_urls = load_closed_urls_cache()

    still_open = []
    closed_count = 0

    def check_single_job(item):
        link = item.get("link", "")
        norm_u = normalize_url(link)
        j_id = item.get("id", "")
        comp = item.get("company", "")
        title = item.get("title", "")

        if link in closed_urls or (j_id in closed_map) or (norm_u in set(c.get("link") for c in closed_map.values() if c.get("link"))):
            mark_url_as_closed(link)
            return None

        if not verify_live_page_applyable(link):
            mark_url_as_closed(link)
            return None

        # Re-score for freshness
        active_prof = get_active_profile()
        item["match_score"] = calculate_skill_match_score(title, comp, item.get("location", ""), profile=active_prof)
        item["profile_scores"] = evaluate_job_for_all_profiles(title, comp, item.get("location", ""))
        return item

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        results = executor.map(check_single_job, discovered_list)
        for res in results:
            if res:
                still_open.append(res)
            else:
                closed_count += 1

    deduped = deduplicate_job_list(still_open)
    save_discovered_jobs(deduped)
    update_scraper_status("total_discovered_jobs", len(deduped))

    print(f"✅ [Closure Audit] Sweep finished. Purged {closed_count} closed roles. Active open roles: {len(deduped)}")
    return closed_count

def run_all_scrapers():
    """
    Main ingestion loop orchestrating scrapers, deduplication, scoring, and status updates.
    """
    print(f"\n=======================================================")
    print(f"🚀 [Scraper Pipeline] Launching full multi-sector scrape at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"=======================================================")

    discovered = load_discovered_jobs()
    seen = load_seen_jobs()

    new_found = run_all_ats_scrapers(discovered)

    # Multi-layer deduplication
    deduped = deduplicate_job_list(discovered)

    # Ensure profile scores are up-to-date
    active_prof = get_active_profile()
    for item in deduped:
        item["match_score"] = calculate_skill_match_score(item.get("title", ""), item.get("company", ""), item.get("location", ""), profile=active_prof)
        item["profile_scores"] = evaluate_job_for_all_profiles(item.get("title", ""), item.get("company", ""), item.get("location", ""))
        seen.add(item.get("id"))
        seen.add(normalize_url(item.get("link", "")))

    save_discovered_jobs(deduped)
    save_seen_jobs(seen)

    now_str = time.strftime("%Y-%m-%d %H:%M")
    update_scraper_status("last_run", now_str)
    update_scraper_status("total_discovered_jobs", len(deduped))
    update_scraper_status("total_seen_jobs", len(seen))
    update_scraper_status("last_new_jobs_found", new_found)

    print(f"📊 [Scraper Pipeline] Status updated: {len(deduped)} active discovered roles ({new_found} new).")

    # Optional healthcheck ping
    if HEALTHCHECKS_PING_URL:
        try:
            requests.get(HEALTHCHECKS_PING_URL, timeout=5)
            print("📡 Healthchecks ping dispatched successfully.")
        except Exception:
            pass

    return new_found
