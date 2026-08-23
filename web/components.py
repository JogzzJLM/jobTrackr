import html
from core.normalization import normalize_company, normalize_role

def render_kpi_card(title, value, subtitle, icon="💼", badge="", badge_type="neutral"):
    badge_html = ""
    if badge:
        badge_html = f'<span class="kpi-badge kpi-badge-{badge_type}">{html.escape(badge)}</span>'

    return f"""
    <div class="kpi-card glass-panel">
        <div class="kpi-top">
            <div class="kpi-icon-box">{icon}</div>
            {badge_html}
        </div>
        <div class="kpi-val">{html.escape(str(value))}</div>
        <div class="kpi-title">{html.escape(title)}</div>
        <div class="kpi-sub">{html.escape(subtitle)}</div>
    </div>
    """

def render_job_card(job, applied_companies=None, applied_jobs=None, active_profile=None):
    if applied_companies is None:
        applied_companies = set()
    if applied_jobs is None:
        applied_jobs = set()

    job_id = job.get("id", "")
    comp = job.get("company", "Company")
    title = job.get("title", "Role Title")
    loc = job.get("location", "Remote / Flexible")
    dept = job.get("department", "")
    link = job.get("link", "#")
    sources = job.get("sources", [job.get("source", "Direct API")])
    date_found = job.get("date_found", "")
    score = job.get("match_score", 50)

    norm_c = normalize_company(comp)
    norm_t = normalize_role(title)

    is_already_applied = (norm_c in applied_companies) or ((norm_c, norm_t) in applied_jobs)

    score_class = "score-high" if score >= 80 else ("score-mid" if score >= 50 else "score-low")

    source_tags = "".join([f'<span class="source-tag">{html.escape(s)}</span>' for s in sources])
    dept_tag = f'<span class="dept-tag">{html.escape(dept)}</span>' if dept else ''

    status_pill = ''
    apply_btn_label = '⚡ 1-Click Apply'
    apply_btn_class = 'btn-apply'

    if is_already_applied:
        status_pill = '<span class="status-applied-pill">✓ Applied</span>'
        apply_btn_label = '✓ Applied in Sheet'
        apply_btn_class = 'btn-applied'

    safe_comp = comp.replace("'", "\\'").replace('"', '&quot;')
    safe_title = title.replace("'", "\\'").replace('"', '&quot;')
    safe_link = link.replace("'", "\\'").replace('"', '&quot;')

    return f"""
    <div class="job-card glass-panel" id="card_{job_id}">
        <div class="job-card-header">
            <div class="job-meta-left">
                <div class="job-company-row">
                    <h3 class="job-company">{html.escape(comp)}</h3>
                    {status_pill}
                </div>
                <h4 class="job-title">{html.escape(title)}</h4>
                <div class="job-loc">📍 {html.escape(loc)} {dept_tag}</div>
            </div>
            <div class="job-meta-right">
                <div class="score-badge {score_class}" title="Profile Keyword Match Relevance">
                    <span class="score-num">{score}%</span>
                    <span class="score-lbl">Match</span>
                </div>
            </div>
        </div>

        <div class="job-card-footer">
            <div class="source-tags-box">
                {source_tags}
                <span class="date-found">🕒 {html.escape(date_found)}</span>
            </div>
            <div class="action-btn-group">
                <a href="{html.escape(link)}" target="_blank" rel="noopener noreferrer" class="btn btn-ghost btn-sm">
                    View Post ↗
                </a>
                <button onclick="logAppliedDirect('{safe_comp}', '{safe_title}', '{safe_link}', '{job_id}')" class="btn {apply_btn_class} btn-sm" id="btn_log_{job_id}">
                    {apply_btn_label}
                </button>
                <button onclick="hideJobDirect('{job_id}')" class="btn btn-icon btn-sm" title="Hide job">
                    ✕
                </button>
                <button onclick="reportClosedDirect('{job_id}', '{safe_comp}', '{safe_title}', '{safe_link}')" class="btn btn-icon btn-sm" title="Report position closed">
                    🚫
                </button>
            </div>
        </div>
    </div>
    """

def render_application_row(app, active_profile=None):
    comp = app.get("company", "")
    role = app.get("role", "")
    stage = app.get("current_stage", "Applied")
    stages = app.get("stages", [stage])
    date_val = app.get("date", "")
    link = app.get("link", "")

    stage_lower = stage.lower()
    if "offer" in stage_lower:
        badge_cls = "stage-offer"
    elif "reject" in stage_lower or "fail" in stage_lower:
        badge_cls = "stage-rejected"
    elif "interview" in stage_lower:
        badge_cls = "stage-interview"
    elif "assessment" in stage_lower or "oa" in stage_lower:
        badge_cls = "stage-oa"
    else:
        badge_cls = "stage-applied"

    stages_breadcrumbs = " → ".join([f'<span class="breadcrumb-stage">{html.escape(s)}</span>' for s in stages])

    safe_comp = comp.replace("'", "\\'").replace('"', '&quot;')
    safe_role = role.replace("'", "\\'").replace('"', '&quot;')

    link_html = f'<a href="{html.escape(link)}" target="_blank" class="app-link">🔗 Post</a>' if link else ''

    return f"""
    <div class="app-row glass-panel">
        <div class="app-main">
            <div class="app-header-line">
                <strong class="app-comp-title">{html.escape(comp)}</strong>
                <span class="app-stage-badge {badge_cls}">{html.escape(stage)}</span>
                {link_html}
            </div>
            <div class="app-role-subtitle">{html.escape(role)}</div>
            <div class="app-history">{stages_breadcrumbs}</div>
        </div>
        <div class="app-actions">
            <span class="app-date">📅 {html.escape(date_val)}</span>
            <div class="app-btns">
                <button onclick="advanceStageModal('{safe_comp}', '{safe_role}')" class="btn btn-sm btn-ghost">
                    + Advance Stage
                </button>
            </div>
        </div>
    </div>
    """
