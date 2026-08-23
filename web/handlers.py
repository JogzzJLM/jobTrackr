import os
import json
import urllib.parse
import http.server
import socketserver
import threading
from urllib.parse import parse_qs, urlparse

from config import (
    PORT, SCRAPER_STATUS, get_scraper_logs, clear_scraper_logs,
    HP_STREAM_TAILSCALE_IP, get_all_profiles, get_active_profile_id,
    set_active_profile_id, get_active_profile, save_or_update_profile,
    delete_profile, load_settings, save_settings,
    load_hidden_jobs, hide_job,
    load_reported_closed_jobs, save_reported_closed_jobs,
    load_closed_urls_cache, mark_url_as_closed,
    remove_pending_email_update, load_discovered_jobs
)
from core.kb import (
    load_closed_keywords_kb, save_closed_keywords_kb, extract_generic_closure_phrases
)
from sheets import (
    update_google_sheet_via_webhook, generate_sankey_from_google_sheets
)
from scrapers_engine.audit import run_all_scrapers
from web.views import render_unified_dashboard_html

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

class CleanHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        profile_param = qs.get("profile", [None])[0]

        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(render_unified_dashboard_html("flow", selected_profile_id=profile_param).encode("utf-8"))

        elif path in ["/jobs", "/discovered"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(render_unified_dashboard_html("jobs", selected_profile_id=profile_param).encode("utf-8"))

        elif path == "/settings":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(render_unified_dashboard_html("settings", selected_profile_id=profile_param).encode("utf-8"))

        elif path in ["/status", "/diagnostics"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(render_unified_dashboard_html("diagnostics", selected_profile_id=profile_param).encode("utf-8"))

        elif path == "/closed":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(render_unified_dashboard_html("closed", selected_profile_id=profile_param).encode("utf-8"))

        elif path == "/sankey-embed":
            active_prof = get_active_profile()
            if profile_param:
                for p in get_all_profiles():
                    if p.get("id") == profile_param:
                        active_prof = p
                        break
            sankey_filename = generate_sankey_from_google_sheets(profile=active_prof, force_refresh=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_cors_headers()
            self.end_headers()
            try:
                with open(sankey_filename, "r", encoding="utf-8") as f:
                    html_str = f.read()
            except Exception:
                html_str = "<html><body><h3 style='color:#fff;'>Sankey Diagram Loading...</h3></body></html>"
            self.wfile.write(html_str.encode("utf-8"))

        elif path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(SCRAPER_STATUS, indent=2).encode("utf-8"))

        elif path == "/api/profiles":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            resp = {
                "active_profile_id": get_active_profile_id(),
                "profiles": get_all_profiles()
            }
            self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))

        elif path == "/api/jobs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(load_discovered_jobs(), indent=2).encode("utf-8"))

        elif path == "/api/logs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(get_scraper_logs()).encode("utf-8"))

        elif path == "/api/kb-status":
            kb = load_closed_keywords_kb()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"count": len(kb), "phrases": kb}).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            data = json.loads(post_body) if post_body else {}
        except Exception:
            data = {}

        if path == "/api/profile/switch":
            prof_id = data.get("profile_id")
            success = set_active_profile_id(prof_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "active_profile_id": get_active_profile_id()}).encode("utf-8"))

        elif path == "/api/profile/save":
            saved = save_or_update_profile(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "profile": saved}).encode("utf-8"))

        elif path == "/api/profile/delete":
            prof_id = data.get("profile_id")
            res = delete_profile(prof_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": res}).encode("utf-8"))

        elif path == "/api/log-application":
            comp = data.get("company", "")
            role = data.get("role", "Target Role")
            stage = data.get("stage", "Applied")
            link = data.get("link", "")
            prof_id = data.get("profile_id")
            pending_id = data.get("pending_id")

            target_prof = None
            if prof_id:
                for p in get_all_profiles():
                    if p.get("id") == prof_id:
                        target_prof = p
                        break

            success = update_google_sheet_via_webhook(comp, stage, role=role, link=link, resolve_sequential=True, profile=target_prof)

            if pending_id:
                remove_pending_email_update(pending_id)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))

        elif path == "/api/resolve-pending-email":
            u_id = data.get("update_id")
            comp = data.get("company")
            role = data.get("role")
            stage = data.get("stage")
            prof_id = data.get("profile_id")

            target_prof = None
            if prof_id:
                for p in get_all_profiles():
                    if p.get("id") == prof_id:
                        target_prof = p
                        break

            success = update_google_sheet_via_webhook(comp, stage, role=role, resolve_sequential=True, profile=target_prof)
            remove_pending_email_update(u_id)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        elif path == "/api/dismiss-pending-email":
            u_id = data.get("update_id")
            remove_pending_email_update(u_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        elif path == "/api/run-scrapers":
            def run_async():
                run_all_scrapers()

            threading.Thread(target=run_async, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "message": "Scraper run launched in background"}).encode("utf-8"))

        elif path == "/api/hide-job":
            j_id = data.get("job_id")
            if j_id:
                hide_job(j_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        elif path == "/api/report-closed":
            j_id = data.get("job_id")
            comp = data.get("company", "")
            title = data.get("title", "")
            link = data.get("link", "")

            if link:
                mark_url_as_closed(link)

            closed_map = load_reported_closed_jobs()
            import time
            closed_map[j_id or link] = {
                "id": j_id,
                "company": comp,
                "title": title,
                "link": link,
                "date_reported": time.strftime("%Y-%m-%d %H:%M")
            }
            save_reported_closed_jobs(closed_map)

            # Extract closure keywords if text provided
            raw_text = data.get("page_text", "")
            if raw_text:
                new_phrases = extract_generic_closure_phrases(raw_text)
                if new_phrases:
                    kb = load_closed_keywords_kb()
                    kb.extend(new_phrases)
                    save_closed_keywords_kb(kb)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        elif path == "/api/settings/save":
            save_settings(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        elif path == "/api/logs/clear":
            clear_scraper_logs()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
