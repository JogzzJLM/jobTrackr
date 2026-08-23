import html
import json
import urllib.parse
from config import (
    SCRAPER_STATUS, HP_STREAM_TAILSCALE_IP, PORT,
    get_active_profile, get_all_profiles, get_active_profile_id,
    load_hidden_jobs, load_reported_closed_jobs, load_pending_email_updates,
    load_settings, load_discovered_jobs
)
from core.kb import load_closed_keywords_kb
from core.normalization import (
    normalize_company, normalize_role, clean_company_display_name, deduplicate_job_list
)
from sheets import (
    fetch_google_sheet_csv, parse_sheet_stats, get_detailed_applications,
    get_applied_jobs_set, generate_sankey_from_google_sheets
)
from web.components import render_kpi_card, render_job_card, render_application_row

def render_unified_dashboard_html(active_tab="flow", selected_profile_id=None):
    all_profiles = get_all_profiles()
    active_profile = get_active_profile()
    if selected_profile_id:
        for p in all_profiles:
            if p.get("id") == selected_profile_id:
                active_profile = p
                break

    profile_id = active_profile.get("id", "prof_swe")
    accent_color = active_profile.get("color_accent", "#FF8000")

    csv_text = fetch_google_sheet_csv(profile=active_profile)
    stats = parse_sheet_stats(csv_text=csv_text, profile=active_profile)
    apps = get_detailed_applications(csv_text=csv_text, profile=active_profile)
    all_discovered = load_discovered_jobs()
    applied_jobs, applied_companies = get_applied_jobs_set(csv_text=csv_text, profile=active_profile)
    hidden_jobs = load_hidden_jobs()
    pending_updates = load_pending_email_updates()
    closed_map = load_reported_closed_jobs()
    kb_phrases = load_closed_keywords_kb()
    settings = load_settings()

    total_tracked = stats.get("total", 0)
    active_pipe = stats.get("active", 0)
    offers_count = stats.get("offers", 0)
    rejections_count = stats.get("rejections", 0)
    conv_rate = round((offers_count / total_tracked * 100), 1) if total_tracked > 0 else 0.0

    # Filter out hidden or closed jobs for discovery tab
    visible_jobs = [j for j in all_discovered if j.get("id") not in hidden_jobs and j.get("id") not in closed_map]
    
    # Sort visible jobs by match score descending
    visible_jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)

    # Ambiguous Email Resolution Banner HTML
    pending_banner_html = ""
    if pending_updates:
        items_html = ""
        for u in pending_updates:
            u_id = u.get("id", "")
            comp = u.get("company", "Company")
            stage = u.get("stage", "Update")
            subj = u.get("subject", "")
            date_rec = u.get("date_received", "")
            options = u.get("options", [])

            opt_btns = ""
            if options:
                for opt in options:
                    opt_role = opt.get("role", "Target Role")
                    opt_comp = opt.get("company", comp)
                    opt_prof_id = opt.get("profile_id", profile_id)
                    opt_prof_name = opt.get("profile_name", "Profile")
                    opt_role_js = opt_role.replace("'", "\\'").replace('"', '&quot;')
                    opt_comp_js = opt_comp.replace("'", "\\'").replace('"', '&quot;')
                    opt_btns += f"""
                    <button onclick="resolvePendingUpdate('{u_id}', '{opt_comp_js}', '{opt_role_js}', '{stage}', '{opt_prof_id}')" class="btn btn-apply btn-sm" style="margin-right:6px; margin-top:6px;">
                        Assign to: <strong>{html.escape(opt_comp)} ({html.escape(opt_role)})</strong> <small>[{html.escape(opt_prof_name)}]</small>
                    </button>
                    """
            else:
                opt_btns += f"""
                <button onclick="openLogModalForPending('{u_id}', '{comp.replace("'", "\\'")}', '{stage}')" class="btn btn-apply btn-sm" style="margin-right:6px; margin-top:6px;">
                    + Assign to New Role in Sheet
                </button>
                """

            opt_btns += f"""
            <button onclick="dismissPendingUpdate('{u_id}')" class="btn btn-ghost btn-sm" style="margin-top:6px;">
                Dismiss
            </button>
            """

            items_html += f"""
            <div class="pending-card">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
                    <div>
                        <span class="badge-alert">ACTION REQUIRED</span>
                        <strong style="font-size:16px; margin-left:8px; color:var(--text-white);">{html.escape(comp)}</strong>
                        <span class="stage-tag-alert">[{html.escape(stage)}]</span>
                    </div>
                    <span style="font-size:12px; color:var(--text-muted);">{html.escape(date_rec)}</span>
                </div>
                <div style="font-size:13.5px; color:var(--text-dim); margin-top:8px;">Email Subject: <em>"{html.escape(subj)}"</em></div>
                <div style="font-size:13px; font-weight:600; color:var(--text-white); margin-top:10px;">Select which logged role this status update belongs to:</div>
                <div style="margin-top:8px; display:flex; flex-wrap:wrap; gap:6px;">{opt_btns}</div>
            </div>
            """

        pending_banner_html = f"""
        <div class="pending-banner-container">
            <div class="banner-header">
                <span>⚠️ Action Required: Received Status Updates ({len(pending_updates)})</span>
            </div>
            <p style="font-size:13.5px; color:var(--text-dim); margin-top:4px;">
                Incoming status emails were detected for companies with multiple roles or unlogged positions. Pick the target role to update Google Sheets:
            </p>
            {items_html}
        </div>
        """

    # Build Profile Switcher Options
    profile_options_html = ""
    for p in all_profiles:
        p_id = p.get("id")
        p_name = p.get("name", "Profile")
        p_owner = p.get("owner", "")
        p_accent = p.get("color_accent", "#FF8000")
        is_sel = "selected" if p_id == profile_id else ""
        label = f"{p_name} ({p_owner})" if p_owner else p_name
        profile_options_html += f'<option value="{p_id}" {is_sel} data-color="{p_accent}">👤 {html.escape(label)}</option>'

    # Active Tab Rendering
    tab_content_html = ""

    if active_tab == "flow":
        # Generate Sankey Diagram for active profile
        generate_sankey_from_google_sheets(profile=active_profile)

        apps_rows = "".join([render_application_row(a, active_profile) for a in apps]) if apps else """
        <div class="empty-state">
            <div class="empty-icon">📭</div>
            <div class="empty-title">No applications logged yet in this profile</div>
            <div class="empty-sub">Click "+ Log Application" or 1-click apply from the Discovered Jobs feed.</div>
        </div>
        """

        tab_content_html = f"""
        <div class="flow-grid">
            <div class="sankey-wrapper glass-panel">
                <div class="panel-header">
                    <div>
                        <h2 class="panel-title">Interactive Pipeline Flow Visualizer</h2>
                        <div class="panel-sub">Real-time stage transitions synchronized with Google Sheets</div>
                    </div>
                    <button onclick="refreshSankey()" class="btn btn-ghost btn-sm">🔄 Refresh Flow</button>
                </div>
                <iframe src="/sankey-embed" id="sankey_iframe" class="sankey-iframe"></iframe>
            </div>

            <div class="pipeline-list-wrapper glass-panel">
                <div class="panel-header">
                    <div>
                        <h2 class="panel-title">Active Applications ({len(apps)})</h2>
                        <div class="panel-sub">Tracked progression for profile: <strong>{html.escape(active_profile.get('name'))}</strong></div>
                    </div>
                    <button onclick="openLogModal()" class="btn btn-apply btn-sm">+ Log Application</button>
                </div>
                <div class="apps-scroll-list">
                    {apps_rows}
                </div>
            </div>
        </div>
        """

    elif active_tab == "jobs":
        cards_html = "".join([render_job_card(j, applied_companies, applied_jobs, active_profile) for j in visible_jobs]) if visible_jobs else """
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <div class="empty-title">No discovered jobs in feed</div>
            <div class="empty-sub">Click "⚡ Run Live Scraper" below to ingest opportunities across Greenhouse, Lever, Ashby, and SmartRecruiters.</div>
            <button onclick="triggerScrapers()" class="btn btn-apply" style="margin-top:16px;">⚡ Run Live Scrapers</button>
        </div>
        """

        tab_content_html = f"""
        <div class="jobs-view-container">
            <div class="jobs-controls-bar glass-panel">
                <div class="search-input-box">
                    <span class="search-icon">🔍</span>
                    <input type="text" id="jobSearchInput" onkeyup="filterJobsList()" placeholder="Search by role title, company, location, or department..." class="search-input">
                </div>
                <div class="filter-btn-group">
                    <button onclick="setFilter('all')" class="filter-pill active" id="btn_filter_all">All ({len(visible_jobs)})</button>
                    <button onclick="setFilter('match90')" class="filter-pill" id="btn_filter_match90">🔥 80%+ Match</button>
                    <button onclick="setFilter('remote')" class="filter-pill" id="btn_filter_remote">🌐 Remote / Flexible</button>
                    <button onclick="setFilter('unapplied')" class="filter-pill" id="btn_filter_unapplied">⭐ Unapplied</button>
                    <button onclick="triggerScrapers()" class="btn btn-apply btn-sm" id="btn_trigger_scrape">⚡ Run Live Scraper</button>
                </div>
            </div>

            <div class="jobs-feed-grid" id="jobsFeedGrid">
                {cards_html}
            </div>
        </div>
        """

    elif active_tab == "settings":
        gh_list = ", ".join(settings.get("greenhouse_companies", []))
        lev_list = ", ".join(settings.get("lever_companies", []))
        ash_list = ", ".join(settings.get("ashby_companies", []))
        sr_list = ", ".join(settings.get("smartrecruiters_companies", []))

        tab_content_html = f"""
        <div class="settings-grid">
            <div class="settings-col glass-panel">
                <div class="panel-header">
                    <div>
                        <h2 class="panel-title">👤 Active Profile Configuration</h2>
                        <div class="panel-sub">Customizing criteria for: <strong>{html.escape(active_profile.get('name'))}</strong></div>
                    </div>
                    <button onclick="deleteActiveProfile('{profile_id}')" class="btn btn-danger btn-sm">🗑️ Delete Profile</button>
                </div>

                <form id="profileConfigForm" onsubmit="saveProfileConfig(event)">
                    <input type="hidden" id="prof_id" value="{html.escape(profile_id)}">
                    
                    <div class="form-group">
                        <label class="form-label">Profile Name</label>
                        <input type="text" id="prof_name" class="form-input" value="{html.escape(active_profile.get('name', ''))}" required>
                    </div>

                    <div class="form-group">
                        <label class="form-label">User / Owner Label</label>
                        <input type="text" id="prof_owner" class="form-input" value="{html.escape(active_profile.get('owner', ''))}" placeholder="e.g. Uncle, Brother, Personal">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Target Industry</label>
                        <input type="text" id="prof_industry" class="form-input" value="{html.escape(active_profile.get('industry', ''))}">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Target Role Keywords (comma-separated)</label>
                        <textarea id="prof_role_keywords" class="form-textarea" rows="3">{html.escape(', '.join(active_profile.get('role_keywords', [])))}</textarea>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Target Skills & Tools (comma-separated)</label>
                        <textarea id="prof_skills" class="form-textarea" rows="3">{html.escape(', '.join(active_profile.get('skills', [])))}</textarea>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Target Locations (comma-separated)</label>
                        <input type="text" id="prof_locations" class="form-input" value="{html.escape(', '.join(active_profile.get('target_locations', [])))}">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Excluded Keywords (comma-separated)</label>
                        <input type="text" id="prof_exclude" class="form-input" value="{html.escape(', '.join(active_profile.get('exclude_keywords', [])))}">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Google Sheet Webhook URL (1-Click Logging)</label>
                        <input type="url" id="prof_webhook_url" class="form-input" value="{html.escape(active_profile.get('sheet_webhook_url', ''))}" placeholder="https://script.google.com/macros/s/.../exec">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Google Sheet Published CSV URL (Pipeline Sync)</label>
                        <input type="url" id="prof_csv_url" class="form-input" value="{html.escape(active_profile.get('sheet_csv_url', ''))}" placeholder="https://docs.google.com/spreadsheets/d/.../pub?output=csv">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Accent Color</label>
                        <input type="color" id="prof_color" class="form-color" value="{html.escape(active_profile.get('color_accent', '#FF8000'))}">
                    </div>

                    <div style="display:flex; gap:12px; margin-top:20px;">
                        <button type="submit" class="btn btn-apply">💾 Save Profile Settings</button>
                        <button type="button" onclick="openCreateProfileModal()" class="btn btn-ghost">➕ Create New Profile</button>
                    </div>
                </form>
            </div>

            <div class="settings-col glass-panel">
                <div class="panel-header">
                    <div>
                        <h2 class="panel-title">🌐 Global ATS Scraper Targets</h2>
                        <div class="panel-sub">Managed companies across Greenhouse, Lever, Ashby, and SmartRecruiters</div>
                    </div>
                </div>

                <form id="globalSettingsForm" onsubmit="saveGlobalSettings(event)">
                    <div class="form-group">
                        <label class="form-label">Greenhouse Boards (slugs)</label>
                        <textarea id="gh_comps" class="form-textarea" rows="3">{html.escape(gh_list)}</textarea>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Lever Boards (slugs)</label>
                        <textarea id="lev_comps" class="form-textarea" rows="2">{html.escape(lev_list)}</textarea>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Ashby Boards (slugs)</label>
                        <textarea id="ash_comps" class="form-textarea" rows="2">{html.escape(ash_list)}</textarea>
                    </div>

                    <div class="form-group">
                        <label class="form-label">SmartRecruiters Boards (slugs)</label>
                        <textarea id="sr_comps" class="form-textarea" rows="2">{html.escape(sr_list)}</textarea>
                    </div>

                    <button type="submit" class="btn btn-apply" style="margin-top:12px;">💾 Save ATS Companies</button>
                </form>

                <div style="margin-top:24px; border-top:1px solid rgba(255,255,255,0.08); padding-top:16px;">
                    <h3 style="font-size:15px; color:var(--text-white); margin-bottom:8px;">🖥️ Infrastructure Telemetry</h3>
                    <div style="font-size:13px; color:var(--text-dim); line-height:1.6;">
                        <div>• <strong>Host:</strong> HP Stream 11 local server (Ubuntu / macOS)</div>
                        <div>• <strong>Tailscale URL:</strong> <code>http://{HP_STREAM_TAILSCALE_IP}:{PORT}</code></div>
                        <div>• <strong>GitOps Repo:</strong> <code>JogzzJLM/jobTrackr</code> (branch <code>main</code>)</div>
                        <div>• <strong>Portainer Port:</strong> <code>5001</code> (Separate from applicationTrackr on 5000)</div>
                    </div>
                </div>
            </div>
        </div>
        """

    elif active_tab == "diagnostics":
        source_status = SCRAPER_STATUS.get("source_status", {})
        source_cards = ""
        for src, stat in source_status.items():
            source_cards += f"""
            <div class="stat-mini-card">
                <div class="stat-mini-title">{html.escape(src)}</div>
                <div class="stat-mini-val">{html.escape(stat)}</div>
            </div>
            """

        tab_content_html = f"""
        <div class="diagnostics-container">
            <div class="glass-panel" style="margin-bottom:20px;">
                <div class="panel-header">
                    <div>
                        <h2 class="panel-title">📡 Scraper Status & Ingestion Health</h2>
                        <div class="panel-sub">Last scrape run: <strong>{html.escape(SCRAPER_STATUS.get('last_run', 'Never'))}</strong></div>
                    </div>
                    <button onclick="triggerScrapers()" class="btn btn-apply btn-sm">⚡ Run Full Crawl</button>
                </div>
                <div class="source-status-grid">
                    {source_cards}
                </div>
            </div>

            <div class="terminal-card glass-panel">
                <div class="terminal-header">
                    <div class="terminal-title">
                        <span class="terminal-dot red"></span>
                        <span class="terminal-dot yellow"></span>
                        <span class="terminal-dot green"></span>
                        <span style="margin-left:8px;">jobTrackr Container Log Stream (Live)</span>
                    </div>
                    <div style="display:flex; gap:8px;">
                        <button onclick="clearTerminalLogs()" class="btn btn-ghost btn-sm">Clear</button>
                        <button onclick="refreshTerminalLogs()" class="btn btn-ghost btn-sm">🔄 Refresh</button>
                    </div>
                </div>
                <div class="terminal-body" id="terminalLogsBody">Loading log stream...</div>
            </div>
        </div>
        """

    elif active_tab == "closed":
        reported_items = ""
        for j_id, c in closed_map.items():
            reported_items += f"""
            <div class="closed-item-card glass-panel">
                <strong style="color:var(--text-white);">{html.escape(c.get('company', ''))}</strong> - {html.escape(c.get('title', ''))}
                <div style="font-size:12px; color:var(--text-muted); margin-top:4px;">Reported: {html.escape(c.get('date_reported', ''))}</div>
            </div>
            """
        if not reported_items:
            reported_items = '<div class="empty-state"><div class="empty-title">No reported closed positions</div></div>'

        kb_chips = "".join([f'<span class="kb-chip">{html.escape(p)}</span>' for p in kb_phrases])

        tab_content_html = f"""
        <div class="settings-grid">
            <div class="glass-panel">
                <div class="panel-header">
                    <div>
                        <h2 class="panel-title">🚫 Reported Closed Positions ({len(closed_map)})</h2>
                        <div class="panel-sub">Positions removed from feeds and permanently cached as closed</div>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; gap:10px; margin-top:12px;">
                    {reported_items}
                </div>
            </div>

            <div class="glass-panel">
                <div class="panel-header">
                    <div>
                        <h2 class="panel-title">🧠 Learned Closure Knowledge Base ({len(kb_phrases)})</h2>
                        <div class="panel-sub">Heuristic phrases used to detect closed job postings across all ATS platforms</div>
                    </div>
                </div>
                <div class="kb-chips-container" style="margin-top:14px;">
                    {kb_chips}
                </div>
            </div>
        </div>
        """

    # HTML Shell
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>jobTrackr • Universal Multi-Industry Job & Application Engine</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --papaya: #FF8000;
            --papaya-glow: rgba(255, 128, 0, 0.25);
            --papaya-subtle: rgba(255, 128, 0, 0.1);
            --bg-deep: #0A0E17;
            --bg-card: rgba(17, 24, 39, 0.75);
            --bg-card-hover: rgba(24, 34, 53, 0.85);
            --border-glass: rgba(255, 255, 255, 0.08);
            --border-highlight: rgba(255, 128, 0, 0.35);
            --text-white: #FFFFFF;
            --text-dim: #94A3B8;
            --text-muted: #64748B;
            --green: #10B981;
            --red: #EF4444;
            --blue: #3B82F6;
            --purple: #8B5CF6;
            --amber: #F59E0B;
            --profile-accent: {accent_color};
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-deep);
            background-image: 
                radial-gradient(at 0% 0%, rgba(255, 128, 0, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(59, 130, 246, 0.08) 0px, transparent 50%),
                radial-gradient(at 50% 50%, rgba(139, 92, 246, 0.04) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-white);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            -webkit-font-smoothing: antialiased;
        }}

        /* Glassmorphism primitives */
        .glass-panel {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        /* Topbar & Navbar */
        .topbar {{
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(10, 14, 23, 0.82);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border-glass);
            padding: 12px 28px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
        }}

        .brand-box {{
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
            color: var(--text-white);
        }}

        .brand-logo {{
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, var(--papaya), #FF5500);
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 17px;
            box-shadow: 0 0 16px var(--papaya-glow);
        }}

        .brand-text {{
            font-size: 19px;
            font-weight: 800;
            letter-spacing: -0.5px;
        }}

        .brand-accent {{
            color: var(--papaya);
        }}

        .brand-tag {{
            font-size: 11px;
            font-weight: 700;
            background: rgba(255, 128, 0, 0.15);
            color: var(--papaya);
            padding: 2px 8px;
            border-radius: 20px;
            border: 1px solid rgba(255, 128, 0, 0.3);
            text-transform: uppercase;
        }}

        .profile-selector-box {{
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-glass);
            padding: 4px 12px;
            border-radius: 30px;
        }}

        .profile-dropdown {{
            background: transparent;
            border: none;
            color: var(--text-white);
            font-size: 13.5px;
            font-weight: 600;
            cursor: pointer;
            outline: none;
            padding: 4px 6px;
        }}

        .profile-dropdown option {{
            background: #111827;
            color: #FFFFFF;
        }}

        .nav-tabs {{
            display: flex;
            gap: 6px;
        }}

        .nav-link {{
            text-decoration: none;
            font-size: 13.5px;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 10px;
            color: var(--text-dim);
            transition: all 0.2s ease;
        }}

        .nav-link:hover {{
            color: var(--text-white);
            background: rgba(255, 255, 255, 0.05);
        }}

        .nav-link.active {{
            color: var(--text-white);
            background: rgba(255, 128, 0, 0.15);
            border: 1px solid rgba(255, 128, 0, 0.35);
            box-shadow: 0 0 14px rgba(255, 128, 0, 0.2);
        }}

        /* Container Layout */
        .app-container {{
            max-width: 1440px;
            margin: 0 auto;
            padding: 28px 28px 60px 28px;
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }}

        /* KPI Grid */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
        }}

        .kpi-card {{
            padding: 20px 22px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}

        .kpi-card:hover {{
            transform: translateY(-2px);
            border-color: var(--border-highlight);
        }}

        .kpi-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .kpi-icon-box {{
            font-size: 22px;
        }}

        .kpi-badge {{
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 12px;
            text-transform: uppercase;
        }}

        .kpi-badge-success {{
            background: rgba(16, 185, 129, 0.15);
            color: var(--green);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .kpi-badge-papaya {{
            background: rgba(255, 128, 0, 0.15);
            color: var(--papaya);
            border: 1px solid rgba(255, 128, 0, 0.3);
        }}

        .kpi-badge-neutral {{
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-dim);
        }}

        .kpi-val {{
            font-size: 32px;
            font-weight: 800;
            letter-spacing: -1px;
            color: var(--text-white);
        }}

        .kpi-title {{
            font-size: 14px;
            font-weight: 600;
            color: var(--text-dim);
        }}

        .kpi-sub {{
            font-size: 12px;
            color: var(--text-muted);
        }}

        /* Ambiguous Banner */
        .pending-banner-container {{
            background: rgba(255, 128, 0, 0.07);
            border: 2px solid var(--papaya);
            border-radius: 16px;
            padding: 20px 24px;
            box-shadow: 0 0 25px rgba(255, 128, 0, 0.15);
        }}

        .banner-header {{
            font-size: 16px;
            font-weight: 800;
            color: var(--papaya);
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .pending-card {{
            background: rgba(17, 24, 39, 0.9);
            border: 1px solid rgba(255, 128, 0, 0.3);
            border-radius: 12px;
            padding: 16px;
            margin-top: 12px;
        }}

        .badge-alert {{
            background: var(--papaya);
            color: #000;
            font-weight: 800;
            font-size: 11px;
            padding: 2px 7px;
            border-radius: 4px;
        }}

        .stage-tag-alert {{
            color: var(--papaya);
            font-weight: 800;
            margin-left: 6px;
        }}

        /* Flow Grid */
        .flow-grid {{
            display: grid;
            grid-template-columns: 1fr 400px;
            gap: 20px;
        }}

        @media (max-width: 1100px) {{
            .flow-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .sankey-wrapper {{
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            min-height: 480px;
        }}

        .sankey-iframe {{
            width: 100%;
            height: 410px;
            border: none;
            border-radius: 12px;
            margin-top: 14px;
            background: transparent;
        }}

        .pipeline-list-wrapper {{
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
        }}

        .apps-scroll-list {{
            max-height: 600px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 16px;
            padding-right: 4px;
        }}

        .app-row {{
            padding: 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .app-row:hover {{
            background: var(--bg-card-hover);
        }}

        .app-header-line {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .app-comp-title {{
            font-size: 15px;
            font-weight: 700;
            color: var(--text-white);
        }}

        .app-role-subtitle {{
            font-size: 13px;
            color: var(--text-dim);
        }}

        .app-history {{
            font-size: 12px;
            color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
        }}

        .breadcrumb-stage {{
            color: var(--text-dim);
        }}

        .app-actions {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            padding-top: 8px;
            margin-top: 4px;
        }}

        .app-date {{
            font-size: 12px;
            color: var(--text-muted);
        }}

        .app-stage-badge {{
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 12px;
        }}

        .stage-offer {{ background: rgba(16, 185, 129, 0.2); color: var(--green); }}
        .stage-rejected {{ background: rgba(239, 68, 68, 0.2); color: var(--red); }}
        .stage-interview {{ background: rgba(59, 130, 246, 0.2); color: var(--blue); }}
        .stage-oa {{ background: rgba(245, 158, 11, 0.2); color: var(--amber); }}
        .stage-applied {{ background: rgba(255, 128, 0, 0.2); color: var(--papaya); }}

        /* Jobs Tab */
        .jobs-controls-bar {{
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 20px;
        }}

        .search-input-box {{
            display: flex;
            align-items: center;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-glass);
            border-radius: 10px;
            padding: 8px 14px;
            flex: 1;
            max-width: 460px;
        }}

        .search-input {{
            background: transparent;
            border: none;
            color: var(--text-white);
            font-size: 14px;
            width: 100%;
            outline: none;
            margin-left: 8px;
        }}

        .filter-btn-group {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}

        .filter-pill {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-glass);
            color: var(--text-dim);
            font-size: 13px;
            font-weight: 600;
            padding: 7px 14px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .filter-pill:hover {{
            color: var(--text-white);
            background: rgba(255, 255, 255, 0.1);
        }}

        .filter-pill.active {{
            background: rgba(255, 128, 0, 0.2);
            color: var(--papaya);
            border-color: var(--papaya);
        }}

        .jobs-feed-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
            gap: 18px;
        }}

        @media (max-width: 600px) {{
            .jobs-feed-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .job-card {{
            padding: 20px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 14px;
        }}

        .job-card:hover {{
            transform: translateY(-2px);
            border-color: var(--border-highlight);
        }}

        .job-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
        }}

        .job-company-row {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .job-company {{
            font-size: 16px;
            font-weight: 700;
            color: var(--text-white);
        }}

        .job-title {{
            font-size: 15px;
            font-weight: 600;
            color: #E2E8F0;
            margin-top: 4px;
            line-height: 1.35;
        }}

        .job-loc {{
            font-size: 12.5px;
            color: var(--text-dim);
            margin-top: 6px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .dept-tag {{
            background: rgba(255, 255, 255, 0.07);
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 11px;
        }}

        .score-badge {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 6px 10px;
            border-radius: 12px;
            min-width: 54px;
        }}

        .score-high {{
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid rgba(16, 185, 129, 0.4);
            color: var(--green);
        }}

        .score-mid {{
            background: rgba(255, 128, 0, 0.15);
            border: 1px solid rgba(255, 128, 0, 0.4);
            color: var(--papaya);
        }}

        .score-low {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-glass);
            color: var(--text-muted);
        }}

        .score-num {{
            font-size: 15px;
            font-weight: 800;
        }}

        .score-lbl {{
            font-size: 9.5px;
            text-transform: uppercase;
            font-weight: 700;
        }}

        .job-card-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            padding-top: 12px;
        }}

        .source-tags-box {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }}

        .source-tag {{
            font-size: 11px;
            background: rgba(255, 255, 255, 0.07);
            color: var(--text-dim);
            padding: 2px 7px;
            border-radius: 6px;
        }}

        .date-found {{
            font-size: 11.5px;
            color: var(--text-muted);
        }}

        .action-btn-group {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .status-applied-pill {{
            font-size: 11px;
            font-weight: 700;
            background: rgba(16, 185, 129, 0.15);
            color: var(--green);
            padding: 2px 7px;
            border-radius: 6px;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        /* Buttons */
        .btn {{
            font-family: inherit;
            font-size: 13.5px;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 10px;
            border: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        .btn-sm {{
            padding: 6px 12px;
            font-size: 12.5px;
            border-radius: 8px;
        }}

        .btn-icon {{
            padding: 6px 9px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-glass);
            color: var(--text-dim);
            border-radius: 8px;
        }}

        .btn-icon:hover {{
            background: rgba(255, 255, 255, 0.15);
            color: var(--text-white);
        }}

        .btn-ghost {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--border-glass);
            color: var(--text-dim);
        }}

        .btn-ghost:hover {{
            background: rgba(255, 255, 255, 0.12);
            color: var(--text-white);
        }}

        .btn-apply {{
            background: linear-gradient(135deg, var(--papaya), #FF6600);
            color: #FFFFFF;
            box-shadow: 0 4px 12px var(--papaya-glow);
        }}

        .btn-apply:hover {{
            box-shadow: 0 6px 18px rgba(255, 128, 0, 0.45);
            transform: translateY(-1px);
        }}

        .btn-applied {{
            background: rgba(16, 185, 129, 0.15);
            color: var(--green);
            border: 1px solid rgba(16, 185, 129, 0.3);
            cursor: default;
        }}

        .btn-danger {{
            background: rgba(239, 68, 68, 0.15);
            color: var(--red);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}

        .btn-danger:hover {{
            background: var(--red);
            color: #fff;
        }}

        /* Settings & Diagnostics Layout */
        .settings-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
            gap: 20px;
        }}

        .panel-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 18px;
            gap: 12px;
        }}

        .panel-title {{
            font-size: 17px;
            font-weight: 700;
            color: var(--text-white);
        }}

        .panel-sub {{
            font-size: 13px;
            color: var(--text-dim);
            margin-top: 2px;
        }}

        .form-group {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            margin-bottom: 14px;
        }}

        .form-label {{
            font-size: 13px;
            font-weight: 600;
            color: var(--text-dim);
        }}

        .form-input, .form-textarea, .form-color {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-glass);
            border-radius: 8px;
            padding: 10px 14px;
            color: var(--text-white);
            font-family: inherit;
            font-size: 13.5px;
            outline: none;
            transition: border-color 0.2s ease;
        }}

        .form-input:focus, .form-textarea:focus {{
            border-color: var(--papaya);
            background: rgba(255, 255, 255, 0.07);
        }}

        .source-status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 12px;
            margin-top: 12px;
        }}

        .stat-mini-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-glass);
            border-radius: 10px;
            padding: 12px 14px;
        }}

        .stat-mini-title {{
            font-size: 13px;
            font-weight: 700;
            color: var(--text-white);
        }}

        .stat-mini-val {{
            font-size: 12px;
            color: var(--text-dim);
            margin-top: 4px;
        }}

        /* Terminal Console */
        .terminal-card {{
            background: #0D1117;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 14px;
            overflow: hidden;
        }}

        .terminal-header {{
            background: #161B22;
            padding: 10px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }}

        .terminal-title {{
            display: flex;
            align-items: center;
            font-size: 13px;
            font-weight: 600;
            color: var(--text-dim);
            font-family: 'JetBrains Mono', monospace;
        }}

        .terminal-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 5px;
        }}

        .terminal-dot.red {{ background: #EF4444; }}
        .terminal-dot.yellow {{ background: #F59E0B; }}
        .terminal-dot.green {{ background: #10B981; }}

        .terminal-body {{
            padding: 16px;
            max-height: 480px;
            overflow-y: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: #38BDF8;
            line-height: 1.6;
            white-space: pre-wrap;
            background: #090D14;
        }}

        .kb-chips-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}

        .kb-chip {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-glass);
            color: var(--text-dim);
            font-size: 12px;
            padding: 4px 10px;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
        }}

        /* Empty state */
        .empty-state {{
            padding: 48px 24px;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}

        .empty-icon {{ font-size: 40px; margin-bottom: 12px; }}
        .empty-title {{ font-size: 17px; font-weight: 700; color: var(--text-white); }}
        .empty-sub {{ font-size: 13.5px; color: var(--text-dim); margin-top: 6px; max-width: 440px; }}

        /* Modal Overlay */
        .modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(8px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }}

        .modal-card {{
            background: #111827;
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            width: 90%;
            max-width: 540px;
            padding: 24px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
        }}

        /* Toast notifications */
        .toast-container {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        .toast {{
            background: #1E293B;
            color: #fff;
            padding: 12px 18px;
            border-radius: 10px;
            border-left: 4px solid var(--papaya);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            font-size: 13.5px;
            font-weight: 600;
            animation: slideIn 0.3s ease;
        }}

        @keyframes slideIn {{
            from {{ transform: translateX(100%); opacity: 0; }}
            to {{ transform: translateX(0); opacity: 1; }}
        }}
    </style>
</head>
<body>
    <!-- Top Navigation Bar -->
    <header class="topbar">
        <a href="/" class="brand-box">
            <div class="brand-logo">⚡</div>
            <div class="brand-text">job<span class="brand-accent">Trackr</span></div>
            <span class="brand-tag">v2.0 Universal</span>
        </a>

        <div class="profile-selector-box">
            <span style="font-size:12px; color:var(--text-muted); font-weight:700;">PROFILE:</span>
            <select class="profile-dropdown" id="topbarProfileSelect" onchange="switchUserProfile(this.value)">
                {profile_options_html}
            </select>
        </div>

        <nav class="nav-tabs">
            <a href="/?profile={profile_id}" class="nav-link {'active' if active_tab == 'flow' else ''}">📊 Flow & Pipeline</a>
            <a href="/jobs?profile={profile_id}" class="nav-link {'active' if active_tab == 'jobs' else ''}">💼 Discovered ({len(visible_jobs)})</a>
            <a href="/status?profile={profile_id}" class="nav-link {'active' if active_tab == 'diagnostics' else ''}">📡 Diagnostics & Logs</a>
            <a href="/closed?profile={profile_id}" class="nav-link {'active' if active_tab == 'closed' else ''}">🚫 Closed ({len(closed_map)})</a>
            <a href="/settings?profile={profile_id}" class="nav-link {'active' if active_tab == 'settings' else ''}">⚙️ Settings & Profiles</a>
        </nav>
    </header>

    <!-- Main Content Container -->
    <main class="app-container">
        <!-- Ambiguous Email Resolution Banner -->
        {pending_banner_html}

        <!-- Hero KPI Stat Cards -->
        <section class="kpi-grid">
            {render_kpi_card("Applications Tracked", total_tracked, f"Active across {active_profile.get('name')}", "📋", "Live", "papaya")}
            {render_kpi_card("Active Pipeline", active_pipe, "Interviews & Assessments Pending", "⏳", f"{round(active_pipe/total_tracked*100, 1) if total_tracked else 0}%", "neutral")}
            {render_kpi_card("Offers & Conversion", f"{offers_count} ({conv_rate}%)", f"{rejections_count} logged rejections", "🎯", "Metrics", "success")}
            {render_kpi_card("Live Discovered Jobs", len(visible_jobs), f"Across Greenhouse, Lever, Ashby & SmartRecruiters", "🚀", "Feed", "papaya")}
        </section>

        <!-- Active View Tab Content -->
        {tab_content_html}
    </main>

    <!-- Modal: Log Application -->
    <div class="modal-overlay" id="logAppModal">
        <div class="modal-card">
            <div class="panel-header">
                <h3 class="panel-title">📝 Log Application to Google Sheet</h3>
                <button onclick="closeModal('logAppModal')" class="btn btn-icon btn-sm">✕</button>
            </div>
            <form id="manualLogForm" onsubmit="submitManualLog(event)">
                <input type="hidden" id="modal_pending_id" value="">
                <div class="form-group">
                    <label class="form-label">Company Name</label>
                    <input type="text" id="modal_comp" class="form-input" required placeholder="e.g. Monzo, Deliveroo">
                </div>
                <div class="form-group">
                    <label class="form-label">Role Title</label>
                    <input type="text" id="modal_role" class="form-input" required placeholder="e.g. Senior Backend Engineer">
                </div>
                <div class="form-group">
                    <label class="form-label">Current Stage</label>
                    <select id="modal_stage" class="form-input">
                        <option value="Applied">Applied</option>
                        <option value="Assessment 1">Assessment 1 / OA</option>
                        <option value="Interview 1">Interview 1</option>
                        <option value="Interview 2">Interview 2</option>
                        <option value="Final Round">Final Round</option>
                        <option value="Offer">Offer</option>
                        <option value="Rejected">Rejected</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Job Post URL (Optional)</label>
                    <input type="url" id="modal_link" class="form-input" placeholder="https://...">
                </div>
                <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
                    <button type="button" onclick="closeModal('logAppModal')" class="btn btn-ghost">Cancel</button>
                    <button type="submit" class="btn btn-apply">🚀 Submit to Sheet</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal: Create Profile -->
    <div class="modal-overlay" id="createProfileModal">
        <div class="modal-card">
            <div class="panel-header">
                <h3 class="panel-title">➕ Create New Profile</h3>
                <button onclick="closeModal('createProfileModal')" class="btn btn-icon btn-sm">✕</button>
            </div>
            <form id="newProfileForm" onsubmit="submitNewProfile(event)">
                <div class="form-group">
                    <label class="form-label">Profile Name</label>
                    <input type="text" id="new_prof_name" class="form-input" required placeholder="e.g. Marketing Lead, Sister's Profile">
                </div>
                <div class="form-group">
                    <label class="form-label">Owner / Nickname</label>
                    <input type="text" id="new_prof_owner" class="form-input" placeholder="e.g. Sister, Uncle, Second Persona">
                </div>
                <div class="form-group">
                    <label class="form-label">Industry</label>
                    <input type="text" id="new_prof_industry" class="form-input" placeholder="e.g. Product Management, Marketing">
                </div>
                <div class="form-group">
                    <label class="form-label">Role Keywords (comma-separated)</label>
                    <input type="text" id="new_prof_role_keywords" class="form-input" placeholder="e.g. growth manager, digital marketing, seo" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Accent Color</label>
                    <input type="color" id="new_prof_color" class="form-color" value="#FF8000">
                </div>
                <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
                    <button type="button" onclick="closeModal('createProfileModal')" class="btn btn-ghost">Cancel</button>
                    <button type="submit" class="btn btn-apply">Create Profile</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Toast Container -->
    <div class="toast-container" id="toastContainer"></div>

    <script>
        function showToast(msg) {{
            const c = document.getElementById('toastContainer');
            const t = document.createElement('div');
            t.className = 'toast';
            t.innerText = msg;
            c.appendChild(t);
            setTimeout(() => {{
                t.style.opacity = '0';
                setTimeout(() => t.remove(), 300);
            }}, 3500);
        }}

        function switchUserProfile(profId) {{
            fetch('/api/profile/switch', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ profile_id: profId }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    const url = new URL(window.location.href);
                    url.searchParams.set('profile', profId);
                    window.location.href = url.toString();
                }}
            }});
        }}

        function logAppliedDirect(comp, title, link, jobId) {{
            const btn = document.getElementById('btn_log_' + jobId);
            if (btn) {{
                btn.innerText = '⏳ Logging...';
                btn.disabled = true;
            }}

            fetch('/api/log-application', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    company: comp,
                    role: title,
                    stage: 'Applied',
                    link: link,
                    profile_id: '{profile_id}'
                }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    showToast('✅ Logged application for ' + comp + ' to Google Sheet!');
                    if (btn) {{
                        btn.innerText = '✓ Applied in Sheet';
                        btn.className = 'btn btn-applied btn-sm';
                    }}
                }} else {{
                    showToast('⚠️ Notice: ' + (data.message || 'Logged locally'));
                    if (btn) btn.innerText = '✓ Applied';
                }}
            }})
            .catch(e => {{
                showToast('⚠️ Logged application locally');
                if (btn) btn.innerText = '✓ Applied';
            }});
        }}

        function hideJobDirect(jobId) {{
            fetch('/api/hide-job', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ job_id: jobId }})
            }})
            .then(() => {{
                const el = document.getElementById('card_' + jobId);
                if (el) {{
                    el.style.opacity = '0';
                    setTimeout(() => el.remove(), 250);
                }}
                showToast('Job hidden from feed.');
            }});
        }}

        function reportClosedDirect(jobId, comp, title, link) {{
            if (!confirm('Report position at ' + comp + ' as closed? This will purge it from all feeds.')) return;

            fetch('/api/report-closed', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ job_id: jobId, company: comp, title: title, link: link }})
            }})
            .then(() => {{
                const el = document.getElementById('card_' + jobId);
                if (el) {{
                    el.style.opacity = '0';
                    setTimeout(() => el.remove(), 250);
                }}
                showToast('Reported ' + comp + ' as closed.');
            }});
        }}

        function resolvePendingUpdate(updateId, comp, role, stage, profId) {{
            fetch('/api/resolve-pending-email', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    update_id: updateId,
                    company: comp,
                    role: role,
                    stage: stage,
                    profile_id: profId || '{profile_id}'
                }})
            }})
            .then(r => r.json())
            .then(data => {{
                showToast('✅ Assigned ' + stage + ' update to ' + comp + ' (' + role + ')');
                setTimeout(() => window.location.reload(), 800);
            }});
        }}

        function dismissPendingUpdate(updateId) {{
            fetch('/api/dismiss-pending-email', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ update_id: updateId }})
            }})
            .then(() => {{
                showToast('Dismissed pending update.');
                setTimeout(() => window.location.reload(), 400);
            }});
        }}

        function triggerScrapers() {{
            const btn = document.getElementById('btn_trigger_scrape');
            if (btn) btn.innerText = '⏳ Crawling ATS APIs...';
            showToast('🚀 Running live scraper crawl across Greenhouse, Lever, Ashby, SmartRecruiters...');

            fetch('/api/run-scrapers', {{ method: 'POST' }})
            .then(r => r.json())
            .then(data => {{
                showToast('✅ Ingestion complete! Discovered ' + (data.new_jobs || 0) + ' new jobs.');
                setTimeout(() => window.location.reload(), 1000);
            }})
            .catch(() => {{
                showToast('Crawl initiated in background.');
            }});
        }}

        function refreshSankey() {{
            const ifr = document.getElementById('sankey_iframe');
            if (ifr) ifr.src = '/sankey-embed?profile={profile_id}&_cb=' + Date.now();
            showToast('Refreshed Sankey Flow.');
        }}

        function openModal(id) {{
            const el = document.getElementById(id);
            if (el) el.style.display = 'flex';
        }}

        function closeModal(id) {{
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        }}

        function openLogModal() {{
            document.getElementById('manualLogForm').reset();
            document.getElementById('modal_pending_id').value = '';
            openModal('logAppModal');
        }}

        function openLogModalForPending(pendingId, comp, stage) {{
            document.getElementById('manualLogForm').reset();
            document.getElementById('modal_pending_id').value = pendingId;
            document.getElementById('modal_comp').value = comp;
            document.getElementById('modal_stage').value = stage;
            openModal('logAppModal');
        }}

        function openCreateProfileModal() {{
            document.getElementById('newProfileForm').reset();
            openModal('createProfileModal');
        }}

        function advanceStageModal(comp, role) {{
            document.getElementById('modal_comp').value = comp;
            document.getElementById('modal_role').value = role;
            openModal('logAppModal');
        }}

        function submitManualLog(e) {{
            e.preventDefault();
            const comp = document.getElementById('modal_comp').value;
            const role = document.getElementById('modal_role').value;
            const stage = document.getElementById('modal_stage').value;
            const link = document.getElementById('modal_link').value;
            const pendingId = document.getElementById('modal_pending_id').value;

            fetch('/api/log-application', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    company: comp,
                    role: role,
                    stage: stage,
                    link: link,
                    profile_id: '{profile_id}',
                    pending_id: pendingId
                }})
            }})
            .then(r => r.json())
            .then(data => {{
                closeModal('logAppModal');
                showToast('✅ Logged ' + comp + ' -> ' + stage);
                setTimeout(() => window.location.reload(), 700);
            }});
        }}

        function submitNewProfile(e) {{
            e.preventDefault();
            const name = document.getElementById('new_prof_name').value;
            const owner = document.getElementById('new_prof_owner').value;
            const industry = document.getElementById('new_prof_industry').value;
            const roleKws = document.getElementById('new_prof_role_keywords').value.split(',').map(s => s.trim()).filter(Boolean);
            const color = document.getElementById('new_prof_color').value;

            fetch('/api/profile/save', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    name: name,
                    owner: owner,
                    industry: industry,
                    role_keywords: roleKws,
                    color_accent: color
                }})
            }})
            .then(r => r.json())
            .then(data => {{
                closeModal('createProfileModal');
                showToast('✅ Profile created!');
                switchUserProfile(data.profile.id);
            }});
        }}

        function saveProfileConfig(e) {{
            e.preventDefault();
            const profId = document.getElementById('prof_id').value;
            const name = document.getElementById('prof_name').value;
            const owner = document.getElementById('prof_owner').value;
            const industry = document.getElementById('prof_industry').value;
            const roleKws = document.getElementById('prof_role_keywords').value.split(',').map(s => s.trim()).filter(Boolean);
            const skills = document.getElementById('prof_skills').value.split(',').map(s => s.trim()).filter(Boolean);
            const locs = document.getElementById('prof_locations').value.split(',').map(s => s.trim()).filter(Boolean);
            const excl = document.getElementById('prof_exclude').value.split(',').map(s => s.trim()).filter(Boolean);
            const webhookUrl = document.getElementById('prof_webhook_url').value;
            const csvUrl = document.getElementById('prof_csv_url').value;
            const color = document.getElementById('prof_color').value;

            fetch('/api/profile/save', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    id: profId,
                    name: name,
                    owner: owner,
                    industry: industry,
                    role_keywords: roleKws,
                    skills: skills,
                    target_locations: locs,
                    exclude_keywords: excl,
                    sheet_webhook_url: webhookUrl,
                    sheet_csv_url: csvUrl,
                    color_accent: color
                }})
            }})
            .then(r => r.json())
            .then(data => {{
                showToast('💾 Saved profile configuration!');
                setTimeout(() => window.location.reload(), 600);
            }});
        }}

        function deleteActiveProfile(profId) {{
            if (!confirm('Are you sure you want to delete this profile?')) return;
            fetch('/api/profile/delete', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ profile_id: profId }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    showToast('Profile deleted.');
                    window.location.href = '/settings';
                }} else {{
                    showToast('Cannot delete the only remaining profile.');
                }}
            }});
        }}

        function saveGlobalSettings(e) {{
            e.preventDefault();
            const gh = document.getElementById('gh_comps').value.split(',').map(s => s.trim()).filter(Boolean);
            const lev = document.getElementById('lev_comps').value.split(',').map(s => s.trim()).filter(Boolean);
            const ash = document.getElementById('ash_comps').value.split(',').map(s => s.trim()).filter(Boolean);
            const sr = document.getElementById('sr_comps').value.split(',').map(s => s.trim()).filter(Boolean);

            fetch('/api/settings/save', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    greenhouse_companies: gh,
                    lever_companies: lev,
                    ashby_companies: ash,
                    smartrecruiters_companies: sr
                }})
            }})
            .then(() => {{
                showToast('💾 Saved ATS target companies!');
            }});
        }}

        function filterJobsList() {{
            const q = (document.getElementById('jobSearchInput')?.value || '').toLowerCase();
            const cards = document.querySelectorAll('.job-card');
            cards.forEach(c => {{
                const text = c.innerText.toLowerCase();
                c.style.display = text.includes(q) ? 'flex' : 'none';
            }});
        }}

        function setFilter(type) {{
            document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
            const activeBtn = document.getElementById('btn_filter_' + type);
            if (activeBtn) activeBtn.classList.add('active');

            const cards = document.querySelectorAll('.job-card');
            cards.forEach(c => {{
                if (type === 'all') {{
                    c.style.display = 'flex';
                }} else if (type === 'match90') {{
                    const scoreEl = c.querySelector('.score-num');
                    const score = parseInt(scoreEl?.innerText || '0');
                    c.style.display = score >= 80 ? 'flex' : 'none';
                }} else if (type === 'remote') {{
                    const loc = c.querySelector('.job-loc')?.innerText.toLowerCase() || '';
                    c.style.display = (loc.includes('remote') || loc.includes('flexible')) ? 'flex' : 'none';
                }} else if (type === 'unapplied') {{
                    const isApplied = c.querySelector('.status-applied-pill');
                    c.style.display = !isApplied ? 'flex' : 'none';
                }}
            }});
        }}

        // Terminal Log Stream
        function refreshTerminalLogs() {{
            const el = document.getElementById('terminalLogsBody');
            if (!el) return;
            fetch('/api/logs')
            .then(r => r.json())
            .then(logs => {{
                el.innerText = logs.length ? logs.join('\\n') : '[No logs recorded yet]';
                el.scrollTop = el.scrollHeight;
            }})
            .catch(() => {{}});
        }}

        function clearTerminalLogs() {{
            fetch('/api/logs/clear', {{ method: 'POST' }})
            .then(() => refreshTerminalLogs());
        }}

        if (document.getElementById('terminalLogsBody')) {{
            refreshTerminalLogs();
            setInterval(refreshTerminalLogs, 4000);
        }}
    </script>
</body>
</html>"""
