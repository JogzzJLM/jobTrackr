import csv
import time
import io
import os
import requests
import plotly.graph_objects as go
from config import GOOGLE_SHEET_WEBHOOK_URL, normalize_company, normalize_role, get_active_profile

_SHEET_CSV_CACHE = {}  # {profile_id: {"timestamp": float, "content": str}}

SAMPLE_APPLICATIONS_BY_PROFILE = {
    "prof_swe": """Company,Stage,Role,Date,Link
Monzo,Offer,Senior Backend Engineer,2026-08-18,https://monzo.com/careers
Deliveroo,Interview 2,Staff Fullstack Engineer,2026-08-15,https://deliveroo.com
Cloudflare,Interview 1,Systems Engineer - Distributed,2026-08-12,https://cloudflare.com
Starling Bank,Assessment 1,Backend Go Developer,2026-08-10,https://starlingbank.com
Snyk,Applied,Security Software Engineer,2026-08-08,https://snyk.io
Canonical,Rejected,Ubuntu Platform Engineer,2026-08-02,https://canonical.com""",
    "prof_pm": """Company,Stage,Role,Date,Link
Revolut,Interview 2,Lead Technical Project Manager,2026-08-16,https://revolut.com
Spotify,Interview 1,Senior Agile Delivery Lead,2026-08-14,https://spotify.com
Wise,Assessment 1,Product Operations Manager,2026-08-11,https://wise.com
Checkout.com,Applied,Scrum Master & Program Lead,2026-08-09,https://checkout.com
Palantir,Rejected,Deployment Project Manager,2026-08-04,https://palantir.com""",
    "prof_data": """Company,Stage,Role,Date,Link
Mistral AI,Interview 2,Senior Data & Analytics Engineer,2026-08-17,https://mistral.ai
Hugging Face,Interview 1,Machine Learning Data Scientist,2026-08-13,https://huggingface.co
Synthesia,Assessment 1,BI & Data Platform Specialist,2026-08-10,https://synthesia.io
Scale AI,Applied,Data Pipeline Engineer,2026-08-07,https://scaleai.com""",
    "prof_finance": """Company,Stage,Role,Date,Link
Jane Street,Interview 2,Quantitative Operations Analyst,2026-08-18,https://janestreet.com
Citadel,Interview 1,Strategic Financial Analyst,2026-08-14,https://citadel.com
Two Sigma,Assessment 1,FP&A Operations Specialist,2026-08-11,https://twosigma.com
Marshall Wace,Applied,Investment Risk Analyst,2026-08-09,https://marshallwace.com"""
}

def get_profile_target(profile=None):
    if profile is None:
        profile = get_active_profile()
    return profile

def fetch_google_sheet_csv(profile=None, force_refresh=False):
    """Fetches CSV from Google Sheets with 5-second in-memory caching & profile fallback handling."""
    prof = get_profile_target(profile)
    prof_id = prof.get("id", "prof_swe")
    csv_url = prof.get("sheet_csv_url", "").strip()

    now = time.time()
    cache_entry = _SHEET_CSV_CACHE.get(prof_id, {"timestamp": 0, "content": ""})

    if not force_refresh and (now - cache_entry["timestamp"]) < 5 and cache_entry["content"]:
        return cache_entry["content"]

    if csv_url:
        cache_buster_url = f"{csv_url}&_cb={int(now * 1000)}" if "?" in csv_url else f"{csv_url}?_cb={int(now * 1000)}"
        for attempt in range(2):
            try:
                resp = requests.get(cache_buster_url, timeout=6)
                if resp.status_code == 200 and resp.text.strip():
                    _SHEET_CSV_CACHE[prof_id] = {"timestamp": now, "content": resp.text}
                    return resp.text
            except Exception:
                if attempt == 0:
                    time.sleep(0.5)

    # Return profile template fallback
    fallback_content = SAMPLE_APPLICATIONS_BY_PROFILE.get(prof_id, SAMPLE_APPLICATIONS_BY_PROFILE["prof_swe"])
    _SHEET_CSV_CACHE[prof_id] = {"timestamp": now, "content": fallback_content}
    return fallback_content

def get_detailed_applications(csv_text=None, profile=None, force_refresh=False):
    """
    Parses Google Sheet CSV and returns grouped application dictionaries:
    [{'company': 'Monzo', 'role': '...', 'stages': ['Applied', 'Interview 1'], 'current_stage': 'Interview 1', 'date': '...', 'link': '...'}]
    """
    if csv_text is None:
        csv_text = fetch_google_sheet_csv(profile=profile, force_refresh=force_refresh)

    if not csv_text:
        return []

    apps_map = {}
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            comp = (row.get("Company") or row.get("company") or "").strip()
            role = (row.get("Role") or row.get("role") or "General Role").strip()
            stage = (row.get("Stage") or row.get("stage") or "Applied").strip()
            date_val = (row.get("Date") or row.get("date") or "").strip()
            link = (row.get("Link") or row.get("link") or "").strip()

            if not comp:
                continue

            key = (normalize_company(comp), normalize_role(role))
            if key not in apps_map:
                apps_map[key] = {
                    "company": comp,
                    "role": role,
                    "stages": [],
                    "current_stage": stage,
                    "date": date_val,
                    "link": link
                }

            if stage and stage not in apps_map[key]["stages"]:
                apps_map[key]["stages"].append(stage)

            apps_map[key]["current_stage"] = stage
            if date_val:
                apps_map[key]["date"] = date_val
            if link:
                apps_map[key]["link"] = link

    except Exception as e:
        print(f"⚠️ Error parsing sheet rows: {e}")

    return list(apps_map.values())

def parse_sheet_stats(csv_text=None, profile=None):
    apps = get_detailed_applications(csv_text=csv_text, profile=profile)
    total = len(apps)
    offers = 0
    rejections = 0
    active = 0

    for app in apps:
        stage = app.get("current_stage", "").lower()
        if "offer" in stage:
            offers += 1
        elif "reject" in stage or "fail" in stage or "unsuccessful" in stage:
            rejections += 1
        else:
            active += 1

    return {
        "total": total,
        "active": active,
        "offers": offers,
        "rejections": rejections
    }

def get_applied_jobs_set(csv_text=None, profile=None):
    """Returns a set of (norm_comp, norm_role) tuples and set of norm_comp names."""
    apps = get_detailed_applications(csv_text=csv_text, profile=profile)
    applied_jobs = set()
    applied_companies = set()
    for app in apps:
        nc = normalize_company(app["company"])
        nr = normalize_role(app["role"])
        if nc:
            applied_companies.add(nc)
            applied_jobs.add((nc, nr))
    return applied_jobs, applied_companies

def resolve_smart_stage(company, stage, profile=None):
    """
    Inspects existing stages for `company` in the profile's pipeline and generates
    sequential stage naming (e.g. 'Interview 1' -> 'Interview 2').
    """
    apps = get_detailed_applications(profile=profile)
    norm_c = normalize_company(company)

    existing_stages = []
    for app in apps:
        if normalize_company(app["company"]) == norm_c:
            existing_stages = app.get("stages", [])
            break

    if not existing_stages:
        if stage == "Interview":
            return "Interview 1"
        elif stage == "Online Assessment" or stage == "Assessment":
            return "Assessment 1"
        return stage

    stage_lower = stage.lower()

    if "interview" in stage_lower:
        count = sum(1 for s in existing_stages if "interview" in s.lower())
        new_num = count + 1
        return f"Interview {new_num}"

    elif "assessment" in stage_lower or "oa" in stage_lower or "test" in stage_lower:
        count = sum(1 for s in existing_stages if any(k in s.lower() for k in ["assessment", "oa", "test", "hackerrank", "codility"]))
        new_num = count + 1
        return f"Assessment {new_num}"

    elif "applied" in stage_lower:
        if any("applied" in s.lower() for s in existing_stages):
            return None

    elif "reject" in stage_lower or "fail" in stage_lower:
        if any("reject" in s.lower() for s in existing_stages):
            return None

    elif "offer" in stage_lower:
        if any("offer" in s.lower() for s in existing_stages):
            return None

    return stage

def update_google_sheet_via_webhook(company, stage, role="Target Role", link="", resolve_sequential=True, profile=None):
    prof = get_profile_target(profile)
    webhook_url = prof.get("sheet_webhook_url", "").strip() or GOOGLE_SHEET_WEBHOOK_URL

    if not webhook_url:
        print(f"📝 Local Notice: No Webhook URL configured for profile '{prof.get('name')}'. Stage update recorded locally: {company} -> {stage}")
        # Invalidate cache so local changes can re-read
        prof_id = prof.get("id", "prof_swe")
        _SHEET_CSV_CACHE.pop(prof_id, None)
        return True

    if resolve_sequential:
        final_stage = resolve_smart_stage(company, stage, profile=prof)
        if final_stage is None:
            print(f"📊 Sheet Notice: Stage '{stage}' for {company} already recorded. Skipping duplicate.")
            return True
    else:
        final_stage = stage

    payload = {
        "company": company,
        "stage": final_stage,
        "role": role,
        "link": link,
        "date": time.strftime("%Y-%m-%d")
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=6)
        if resp.status_code in [200, 201]:
            print(f"✅ Logged to Google Sheet ({prof.get('name')}): {company} -> {final_stage}")
            fetch_google_sheet_csv(profile=prof, force_refresh=True)
            return True
        else:
            print(f"⚠️ Google Sheet Webhook returned HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️ Webhook dispatch error ({e})")
    return False

# ================= SANKEY DIAGRAM GENERATOR =================

def generate_sankey_from_google_sheets(profile=None, force_refresh=False):
    """
    Generates a high-resolution Apple Glass Sankey flow diagram using Plotly.
    """
    prof = get_profile_target(profile)
    prof_id = prof.get("id", "prof_swe")
    accent_color = prof.get("color_accent", "#FF8000")

    apps = get_detailed_applications(profile=prof, force_refresh=force_refresh)

    nodes = ["Applied", "Assessment / OA", "Interview 1", "Interview 2", "Final Round", "Offers", "Rejected", "Active Waiting"]
    node_indices = {name: idx for idx, name in enumerate(nodes)}

    flow_counts = {}

    for app in apps:
        stages = app.get("stages", [])
        current = app.get("current_stage", "Applied")

        has_applied = True
        has_oa = any("assessment" in s.lower() or "oa" in s.lower() for s in stages)
        has_int1 = any("interview 1" in s.lower() or ("interview" in s.lower() and "2" not in s.lower()) for s in stages)
        has_int2 = any("interview 2" in s.lower() for s in stages)
        has_final = any("final" in s.lower() or "interview 3" in s.lower() for s in stages)
        has_offer = any("offer" in s.lower() for s in stages)
        has_reject = any("reject" in s.lower() or "fail" in s.lower() for s in stages)

        # Build path
        last_step = "Applied"
        if has_oa:
            flow_counts[(last_step, "Assessment / OA")] = flow_counts.get((last_step, "Assessment / OA"), 0) + 1
            last_step = "Assessment / OA"

        if has_int1:
            flow_counts[(last_step, "Interview 1")] = flow_counts.get((last_step, "Interview 1"), 0) + 1
            last_step = "Interview 1"

        if has_int2:
            flow_counts[(last_step, "Interview 2")] = flow_counts.get((last_step, "Interview 2"), 0) + 1
            last_step = "Interview 2"

        if has_final:
            flow_counts[(last_step, "Final Round")] = flow_counts.get((last_step, "Final Round"), 0) + 1
            last_step = "Final Round"

        if has_offer:
            flow_counts[(last_step, "Offers")] = flow_counts.get((last_step, "Offers"), 0) + 1
        elif has_reject:
            flow_counts[(last_step, "Rejected")] = flow_counts.get((last_step, "Rejected"), 0) + 1
        else:
            flow_counts[(last_step, "Active Waiting")] = flow_counts.get((last_step, "Active Waiting"), 0) + 1

    # Guarantee at least some base links if empty
    if not flow_counts:
        flow_counts[("Applied", "Active Waiting")] = 1

    sources = []
    targets = []
    values = []
    link_colors = []

    for (src, tgt), count in flow_counts.items():
        if src in node_indices and tgt in node_indices:
            sources.append(node_indices[src])
            targets.append(node_indices[tgt])
            values.append(count)
            if tgt == "Offers":
                link_colors.append("rgba(16, 185, 129, 0.45)")
            elif tgt == "Rejected":
                link_colors.append("rgba(239, 68, 68, 0.35)")
            elif "Interview" in tgt or "Assessment" in tgt:
                link_colors.append("rgba(255, 128, 0, 0.45)")
            else:
                link_colors.append("rgba(59, 130, 246, 0.35)")

    node_colors = [
        accent_color,              # Applied
        "#F59E0B",                 # Assessment
        "#3B82F6",                 # Interview 1
        "#8B5CF6",                 # Interview 2
        "#EC4899",                 # Final Round
        "#10B981",                 # Offers
        "#EF4444",                 # Rejected
        "#6B7280"                  # Active Waiting
    ]

    fig = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=18,
            thickness=22,
            line=dict(color="#1E293B", width=1.5),
            label=nodes,
            color=node_colors
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors
        )
    )])

    fig.update_layout(
        title_text=f"<b>{prof.get('name', 'Job')} Application Flow</b>",
        title_font=dict(size=17, color="#FFFFFF", family="Inter, system-ui, sans-serif"),
        font=dict(size=12, color="#E2E8F0", family="Inter, system-ui, sans-serif"),
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        margin=dict(l=25, r=25, t=45, b=25),
        height=380
    )

    out_filename = f"sankey_diagram_{prof_id}.html"
    fig.write_html(out_filename, include_plotlyjs="cdn", full_html=True)
    return out_filename
