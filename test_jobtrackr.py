import sys
import time
import os
import requests
import threading

# Import core modules
from core.storage import (
    load_profiles_data, get_all_profiles, get_active_profile,
    set_active_profile_id, save_or_update_profile, delete_profile,
    load_discovered_jobs, save_discovered_jobs, load_seen_jobs
)
from core.normalization import (
    normalize_company, normalize_role, normalize_url, extract_ats_post_id,
    fuzzy_roles_match, deduplicate_job_list, clean_company_display_name
)
from core.scoring import (
    calculate_skill_match_score, evaluate_job_for_all_profiles,
    is_job_relevant_for_profile
)
from sheets import (
    fetch_google_sheet_csv, parse_sheet_stats, get_detailed_applications,
    resolve_smart_stage, generate_sankey_from_google_sheets
)
from email_listener import (
    classify_email_stage, extract_company_name, handle_incoming_email_update
)
from scrapers_engine.verifier import verify_live_page_applyable
from scrapers_engine.ats_scrapers import add_discovered_job
from web.handlers import ThreadedHTTPServer, CleanHandler

def test_profiles():
    print("🧪 [Test] 1. Multi-User & Multi-Industry Profiles...")
    profiles = get_all_profiles()
    assert len(profiles) >= 4, f"Expected at least 4 default profiles, got {len(profiles)}"
    
    initial_active = get_active_profile()
    print(f"   Default active profile: '{initial_active.get('name')}' (ID: {initial_active.get('id')})")
    
    # Test switching
    set_active_profile_id("prof_pm")
    active_now = get_active_profile()
    assert active_now.get("id") == "prof_pm", "Failed to switch active profile to prof_pm"
    print(f"   Switched active profile to: '{active_now.get('name')}'")
    
    # Test creating new profile
    test_prof = {
        "id": "prof_test_marketing",
        "name": "Growth & Marketing",
        "owner": "Marketing Test",
        "industry": "Marketing",
        "role_keywords": ["growth", "marketing manager", "seo", "content"],
        "level_keywords": ["lead", "senior", "manager"],
        "skills": ["analytics", "google ads", "hubspot", "copywriting"],
        "target_locations": ["London", "Remote"],
        "exclude_keywords": ["intern"],
        "color_accent": "#EC4899"
    }
    save_or_update_profile(test_prof)
    fetched = [p for p in get_all_profiles() if p.get("id") == "prof_test_marketing"]
    assert len(fetched) == 1, "Failed to persist new profile"
    
    # Reset back to SWE
    set_active_profile_id("prof_swe")
    print("   ✅ Profiles test passed successfully.")

def test_normalization_and_deduplication():
    print("🧪 [Test] 2. Normalization & Multi-Layer Deduplication...")
    
    # Company Normalization
    assert normalize_company("Monzo Bank Ltd") == "monzo"
    assert normalize_company("Hudson River Trading LLC") == "hrt"
    assert clean_company_display_name("monzo") == "Monzo"
    
    # Role Normalization & Fuzzy Match
    t1 = "Senior Backend Engineer - London / UK"
    t2 = "Senior Backend Developer"
    assert fuzzy_roles_match(t1, t2), f"Expected '{t1}' and '{t2}' to match fuzzy roles"
    
    # ATS Post IDs
    url_gh = "https://job-boards.greenhouse.io/deliveroo/jobs/5162206007?gh_src=test"
    url_lev = "https://jobs.lever.co/spotify/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
    url_ash = "https://jobs.ashbyhq.com/notion/11223344-5566-7788-99aa-bbccddeeff00"
    
    assert extract_ats_post_id(url_gh) == "gh_5162206007"
    assert extract_ats_post_id(url_lev) == "lev_a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
    assert extract_ats_post_id(url_ash) == "ash_11223344-5566-7788-99aa-bbccddeeff00"
    
    # URL Normalization
    norm_u = normalize_url(url_gh)
    assert "gh_src" not in norm_u and not norm_u.startswith("http")
    
    # Deduplication test
    raw_jobs = [
        {"id": "j1", "company": "Deliveroo", "title": "Senior Backend Engineer", "link": url_gh, "source": "Greenhouse API"},
        {"id": "j2", "company": "Deliveroo Ltd", "title": "Senior Backend Engineer - London", "link": "https://deliveroo.com/jobs/5162206007", "source": "LinkedIn Egress"},
        {"id": "j3", "company": "Spotify", "title": "Lead Agile Coach", "link": url_lev, "source": "Lever API"}
    ]
    deduped = deduplicate_job_list(raw_jobs)
    assert len(deduped) == 2, f"Expected 2 deduplicated jobs, got {len(deduped)}"
    assert "LinkedIn Egress" in deduped[0]["sources"], "Expected sources to be merged into master card"
    print("   ✅ Normalization & Deduplication test passed.")

def test_scoring():
    print("🧪 [Test] 3. Profile-Aware Scoring Engine...")
    swe_score = calculate_skill_match_score("Senior Python Backend Engineer", "Monzo", "London", profile=get_active_profile())
    assert swe_score >= 80, f"Expected SWE score >= 80, got {swe_score}"
    
    pm_prof = next((p for p in get_all_profiles() if p.get("id") == "prof_pm"), None)
    pm_score = calculate_skill_match_score("Technical Project Manager - Agile Delivery", "Wise", "Remote", profile=pm_prof)
    assert pm_score >= 80, f"Expected PM score >= 80, got {pm_score}"
    
    all_scores = evaluate_job_for_all_profiles("Senior Project Manager Scrum Master", "Wise", "London")
    assert all_scores["prof_pm"] > all_scores["prof_swe"], "Expected PM profile to score higher for Scrum Master"
    print(f"   Scores: SWE={all_scores['prof_swe']}%, PM={all_scores['prof_pm']}%")
    print("   ✅ Scoring test passed.")

def test_sheets_and_sankey():
    print("🧪 [Test] 4. Google Sheets & Sankey Diagram Engine...")
    apps = get_detailed_applications()
    assert len(apps) > 0, "Expected default sample applications to load"
    
    stats = parse_sheet_stats()
    assert stats["total"] > 0, "Stats total should be > 0"
    
    s_stage = resolve_smart_stage("Monzo", "Interview")
    assert s_stage is not None
    
    sankey_file = generate_sankey_from_google_sheets(force_refresh=True)
    assert os.path.exists(sankey_file), f"Expected Sankey file {sankey_file} to exist"
    print("   ✅ Sheets & Sankey test passed.")

def test_email_classification():
    print("🧪 [Test] 5. Email Classification & Auto-matching...")
    assert classify_email_stage("We are pleased to offer you the position of Senior Engineer") == "Offer"
    assert classify_email_stage("Invitation to technical interview round 2 with hiring manager") == "Interview"
    assert classify_email_stage("Please complete the HackerRank coding assessment within 5 days") == "Online Assessment"
    assert classify_email_stage("Unfortunately, we have decided not to proceed with your application") == "Rejected"
    
    c_name = extract_company_name("Your application with Deliveroo", "no-reply@deliveroo.com")
    assert "Deliveroo" in c_name
    print("   ✅ Email classification test passed.")

def test_web_server():
    print("🧪 [Test] 6. Live Test Server on Port 5092...")
    test_port = 5092
    server = ThreadedHTTPServer(("127.0.0.1", test_port), CleanHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(1)
    
    base_url = f"http://127.0.0.1:{test_port}"
    
    # GET /
    r_flow = requests.get(f"{base_url}/")
    assert r_flow.status_code == 200 and "jobTrackr" in r_flow.text
    
    # GET /jobs
    r_jobs = requests.get(f"{base_url}/jobs")
    assert r_jobs.status_code == 200 and "Discovered" in r_jobs.text
    
    # GET /settings
    r_set = requests.get(f"{base_url}/settings")
    assert r_set.status_code == 200 and "Profile Configuration" in r_set.text
    
    # GET /sankey-embed
    r_sankey = requests.get(f"{base_url}/sankey-embed")
    assert r_sankey.status_code == 200 and "plotly" in r_sankey.text.lower()
    
    # GET /api/profiles
    r_api_prof = requests.get(f"{base_url}/api/profiles")
    assert r_api_prof.status_code == 200 and "profiles" in r_api_prof.json()
    
    # POST /api/profile/switch
    r_switch = requests.post(f"{base_url}/api/profile/switch", json={"profile_id": "prof_data"})
    assert r_switch.status_code == 200 and r_switch.json().get("success") is True
    
    # POST /api/log-application
    r_log = requests.post(f"{base_url}/api/log-application", json={
        "company": "Scale AI",
        "role": "Data Engineer",
        "stage": "Applied",
        "link": "https://scaleai.com/jobs/123",
        "profile_id": "prof_data"
    })
    assert r_log.status_code == 200
    
    server.shutdown()
    print("   ✅ Live web server test passed.")

if __name__ == "__main__":
    print("\n=======================================================")
    print("🚀 Starting jobTrackr System Verification Test Suite")
    print("=======================================================\n")
    
    test_profiles()
    test_normalization_and_deduplication()
    test_scoring()
    test_sheets_and_sankey()
    test_email_classification()
    test_web_server()
    
    print("\n=======================================================")
    print("🎉 ALL TESTS PASSED SUCCESSFULLY! (6/6 Suites Green)")
    print("=======================================================\n")
