import time
import threading
import sys
import signal
from config import PORT, HP_STREAM_TAILSCALE_IP, add_scraper_log
from web.handlers import ThreadedHTTPServer, CleanHandler
from email_listener import email_listener_loop
from scrapers_engine.audit import run_all_scrapers, recheck_existing_open_jobs_for_closure
from core.storage import load_discovered_jobs

def scraper_scheduler_loop():
    """Background loop running ATS ingestion every 4 hours and periodic closure audit."""
    time.sleep(5)  # Wait 5s on startup for web server to bind
    
    # Run initial scrape if discovered jobs is empty
    existing = load_discovered_jobs()
    if not existing or len(existing) < 5:
        try:
            print("🚀 [Scheduler] Running initial job discovery crawl...")
            run_all_scrapers()
        except Exception as e:
            print(f"⚠️ [Scheduler] Initial crawl notice: {e}")

    while True:
        try:
            time.sleep(4 * 3600)  # Every 4 hours
            run_all_scrapers()
            recheck_existing_open_jobs_for_closure()
        except Exception as e:
            print(f"⚠️ [Scheduler] Error during scheduled crawl: {e}")
            time.sleep(60)

def main():
    port = PORT
    server_address = ("0.0.0.0", port)
    
    print("\n" + "=" * 62)
    print(f"⚡ jobTrackr • Universal Job Discovery & Application Engine")
    print(f"🖥️ Server binding on: http://0.0.0.0:{port}")
    print(f"🌐 Tailscale Access:  http://{HP_STREAM_TAILSCALE_IP}:{port}")
    print("=" * 62 + "\n")

    # Start Background Email Listener Thread
    email_thread = threading.Thread(target=email_listener_loop, args=(300,), daemon=True)
    email_thread.start()
    print("📧 [System] Background Gmail IMAP Listener thread started.")

    # Start Background Scraper Scheduler Thread
    scheduler_thread = threading.Thread(target=scraper_scheduler_loop, daemon=True)
    scheduler_thread.start()
    print("🤖 [System] Background ATS Scraper Scheduler thread started.")

    # Start Web Server
    httpd = ThreadedHTTPServer(server_address, CleanHandler)
    
    def shutdown_handler(signum, frame):
        print("\n🛑 Shutting down jobTrackr gracefully...")
        httpd.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("🛑 Server terminated.")

if __name__ == "__main__":
    main()
