from flask import Flask, render_template, jsonify, request
from pathlib import Path
import threading
import json
import time
import sys
import os
import tempfile

# Import the scraper orchestrator
# We need to add the current dir to path to import scraper properly if needed, but it's in the same dir
from scraper import run_scrapers
from output_handler import moderation_counts
from moderation.env import load_env

load_env()
app = Flask(__name__)

# ---- Who may change data ----
# Visitors coming through a public tunnel (Cloudflare) or a host like Render can only READ.
# Writes (scrape, clear, scam-check buttons) are allowed from this laptop itself, or with the
# secret INREAL_ADMIN_TOKEN in the X-InReal-Token header.
# cloudflared connects from 127.0.0.1 too, but it always adds these headers, so a tunnelled
# request is never mistaken for a local one.
PROXY_HEADERS = ("Cf-Connecting-Ip", "Cf-Ray", "X-Forwarded-For", "X-Forwarded-Host", "Forwarded", "X-Real-Ip")
LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
PROTECTED = {"/api/scrape", "/api/clear", "/api/alerts/dismiss", "/api/session/new"}


LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
# Asked only by the laptop's own tools: tunnel visitors don't need the run log or autopilot state
LOCAL_ONLY_READS = {"/api/logs", "/api/autopilot"}


def _host_name() -> str:
    """The Host header without its port: 'localhost', '127.0.0.1', '[::1]'."""
    host = (request.host or "").lower()
    return host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]


def _from_loopback() -> bool:
    return request.remote_addr in LOOPBACK and not any(request.headers.get(h) for h in PROXY_HEADERS)


def is_local_request() -> bool:
    # The Host must be the laptop's own name too. Without that, a website using DNS rebinding
    # (evil.com pointed at 127.0.0.1) would reach the app from the browser as a "local" visitor.
    return _from_loopback() and _host_name() in LOCAL_HOSTS


def has_admin_token() -> bool:
    import hmac
    token = os.environ.get("INREAL_ADMIN_TOKEN", "")
    sent = request.headers.get("X-InReal-Token", "")
    return bool(token) and hmac.compare_digest(sent, token)


app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024   # no request body here needs more than a few KB
app.config["JSON_SORT_KEYS"] = False


def _refuse(message, code=403):
    return jsonify({"status": "error", "message": message}), code


@app.before_request
def guard_hosts():
    """DNS rebinding: a request that reaches the laptop directly (no tunnel in front) must name the
    laptop itself. Extra names (a LAN setup) go in INREAL_ALLOWED_HOSTS, comma separated."""
    if not _from_loopback():
        return None
    extra = {h.strip().lower() for h in os.environ.get("INREAL_ALLOWED_HOSTS", "").split(",") if h.strip()}
    if _host_name() not in LOCAL_HOSTS | extra:
        return _refuse("Unknown host name.", 400)
    return None


@app.before_request
def guard_cross_site():
    """CSRF: any website open in the same browser can send a plain form or image request to
    localhost:5000. Browsers say where a request came from (Sec-Fetch-Site, Origin), and a page
    on another site cannot add our X-InReal header without the browser asking first, which this
    app never allows. Scripts (no browser headers) carry on as before."""
    if not request.path.startswith("/api/"):
        return None
    site = request.headers.get("Sec-Fetch-Site", "")
    if site in ("cross-site", "same-site"):
        return _refuse("Requests from other websites are not allowed.")
    origin = request.headers.get("Origin", "")
    if origin and origin != "null":
        from urllib.parse import urlparse
        if (urlparse(origin).netloc or "").lower() != (request.host or "").lower():
            return _refuse("Requests from other websites are not allowed.")
    elif origin == "null":
        return _refuse("Requests from other websites are not allowed.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        from_browser = bool(site or origin or request.headers.get("Sec-Fetch-Mode"))
        if from_browser and request.headers.get("X-InReal") != "1" and not has_admin_token():
            return _refuse("Missing the app's request header. Reload the page and try again.")
    return None


@app.before_request
def guard_writes():
    path = request.path.rstrip("/")
    needs_admin = path.startswith("/api/moderation/") and path != "/api/moderation/status"
    needs_admin |= path in PROTECTED and request.method == "POST"
    needs_admin |= path in LOCAL_ONLY_READS
    if needs_admin and not (is_local_request() or has_admin_token()):
        return _refuse("This is a read-only public view. Run scrapes from the laptop.")
    return None


def _csp() -> str:
    supa = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    connect = ["'self'"] + ([supa, supa.replace("https://", "wss://", 1)] if supa.startswith("https://") else [])
    return "; ".join([
        "default-src 'self'",
        # inline handlers need 'unsafe-inline'; 'unsafe-eval' stays until the Tailwind play CDN is replaced
        # by a built CSS file (it could not be checked from here whether that script evaluates code).
        # The real locks are below: no framing, no plugins, no <base> or form hijack, and the page can
        # only send data to this app and Supabase.
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com",
        "font-src 'self' data: https://fonts.gstatic.com https://unpkg.com",
        "img-src 'self' data: blob: https:",
        "connect-src " + " ".join(connect),
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ])


@app.after_request
def security_headers(resp):
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    if resp.mimetype == "text/html":
        h.setdefault("Content-Security-Policy", _csp())
    if request.path.startswith("/api/"):
        h.setdefault("Cache-Control", "no-store")
    if request.headers.get("X-Forwarded-Proto") == "https" or request.is_secure:
        h.setdefault("Strict-Transport-Security", "max-age=31536000")
    h.pop("Server", None)
    return resp


@app.errorhandler(413)
def too_large(_e):
    return _refuse("Request too large.", 413)


@app.errorhandler(500)
def server_error(_e):
    # no stack traces or file paths to the browser; the details are in the console
    return _refuse("Something went wrong on the server.", 500)


@app.before_request
def same_origin_for_sign_in():
    """Google sign-in comes back to http://localhost:<port> (the address allowed in Supabase), and the
    session lives in that origin's browser storage. Opened as 127.0.0.1 the page would never see it,
    so the pages move to localhost first."""
    from flask import redirect
    host = request.host.split(":")[0]
    if request.method == "GET" and host in ("127.0.0.1", "[::1]") and request.path in ("/", "/app"):
        port = request.host.split(":")[-1] if ":" in request.host.replace("[::1]", "") else ""
        return redirect(f"http://localhost{':' + port if port else ''}{request.full_path.rstrip('?')}", code=302)


@app.route("/api/fields")
def list_fields():
    import fields
    return jsonify(fields.public_list())


@app.route("/api/sites")
def list_sites():
    from sites import registry
    return jsonify(registry.public_list())


@app.route("/api/whoami")
def whoami():
    return jsonify({"can_edit": is_local_request() or has_admin_token()})
DATA_FILE = Path(__file__).parent / "internships.csv"

# Global state for scraping
scraper_t = None
QUEUE = {"waiting": False}   # a search is waiting for the automatic update to stop
QUEUE_WAIT_S = 3 * 3600   # a search queued behind the automatic update is dropped after this

def public_config():
    """What the browser needs to talk to Supabase. The publishable key is public by design;
    the secret key never leaves this laptop (supabase_sync.py)."""
    import fields
    from moderation.env import load_env
    from sites import registry
    load_env()
    return {
        "supabaseUrl": os.environ.get("SUPABASE_URL", "").strip(),
        "supabaseKey": os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip(),
        "liveSites": sum(1 for s in registry.SITES if s["status"] == "tested"),
        "fields": fields.public_list(),
    }


@app.route("/")
def site():
    """Landing page and Google sign-in (static/site.js). A signed-in visitor is sent on to /app."""
    return render_template("site.html", config=public_config())


@app.route("/app")
def user_app():
    """The dashboard (search, Load 5 more, scam check) behind Google sign-in. Signed out, the page
    sends the visitor back to /. The data and the searches are this laptop's, as on /admin."""
    config = dict(public_config(), mode="user")
    return render_template("index.html", user_mode=True, config=config,
                           sites_text=str(config["liveSites"] or "many"))


@app.route("/admin")
def admin():
    """The search / scam-check dashboard: this laptop only."""
    if not (is_local_request() or has_admin_token()):
        return "The admin dashboard opens only on the laptop that runs InReal.", 403
    return render_template("index.html", user_mode=False, config={},
                           sites_text=str(public_config()["liveSites"] or "many"))

@app.route("/api/internships")
def get_internships():
    if not DATA_FILE.exists():
        return jsonify([])
        
    try:
        # Read under the writers' lock: on Windows an open reader makes the writer's file replace fail
        from output_handler import read_all_rows
        rows = read_all_rows()
        for r in rows:
            for k in ("match_score", "stipend_numeric"):
                try:
                    if r.get(k) not in (None, ""):
                        v = float(r[k])
                        r[k] = int(v) if v.is_integer() else v
                except ValueError:
                    pass
        return jsonify(rows)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return jsonify([])

# A new search shows its first internships without a click: as each site finishes, its posts top
# up a batch of FIRST_SHOW that goes to the scam check by itself (scraper.process_and_save).
# "Load 5 more" then sends the rest, 5 at a time. "Search more" adds to the same search and
# waits for "Load 5 more" as before. (25 Oct: the list sat empty behind a "Check next 5" button.)
from scraper import FIRST_SHOW


@app.route("/api/scrape", methods=["POST"])
def trigger_scrape():
    global scraper_t
    
    # Only the sites the person picked, never "everything": a request without a site list used
    # to fall back to all 23 sites (scraper.run_scrapers with no config).
    config = request.get_json(silent=True)
    if not isinstance(config, dict) or not [s for s in (config.get("sources") or []) if str(s).strip()]:
        return jsonify({"status": "error", "message": "Pick at least one site to search."}), 400
    config["sources"] = [str(s).strip() for s in config["sources"] if str(s).strip()]

    if scraper_t and scraper_t.is_alive():
        return jsonify({"status": "running", "message": "Scraping is already in progress!"})
    import autopilot
    queued = autopilot.busy()
    if queued:
        autopilot.STATE["yield"] = True   # the round stops after its current site search
    run_tag = ""
    new_search = not config.get("run_tag")   # "Search more" sends the tag of the search on screen
    if config is not None:
        # A new search gets a new tag and the dashboard shows only its results;
        # "Search more" sends the tag of the search on screen to keep adding to it.
        from datetime import datetime as _dt
        if not config.get("run_tag"):
            # A new search no longer empties the list: the page shows only this search's tag, and
            # posts found again keep their verdict (no second Azure check). Old ones are pruned.
            from output_handler import prune_old
            prune_old()
        run_tag = str(config.get("run_tag") or _dt.now().strftime("%Y%m%d-%H%M%S"))
        config["run_tag"] = run_tag

    def scrape_job(cfg):
        if queued:
            deadline = time.time() + QUEUE_WAIT_S
            QUEUE["waiting"] = True
            try:
                while autopilot.busy() and time.time() < deadline:
                    time.sleep(2)
            finally:
                QUEUE["waiting"] = False
            if autopilot.busy():   # never two scrapers at once: they share Chrome and the list
                print("Queued search dropped: the automatic update did not stop in time")
                return
        if new_search:
            cfg["first_show"] = FIRST_SHOW   # the first 10 go to the scam check as sites finish
        run_scrapers(dry_run=False, config=cfg)   # starts the scam check after each site (moderation/notify.py)

    scraper_t = threading.Thread(target=scrape_job, args=(config,), daemon=True)
    scraper_t.start()
    if queued:
        return jsonify({"status": "queued", "run_tag": run_tag,
                        "message": "The automatic update is finishing the site it is on; your search starts right after."})
    return jsonify({"status": "started", "run_tag": run_tag, "message": "Scraper started successfully. This might take a while."})

# ---- Scam check, as the dashboard sees it (the check itself runs in moderation/pipeline) ----

@app.route("/api/moderation/status")
def moderation_status():
    return jsonify(moderation_counts())


def manual_scrape_running() -> bool:
    return bool(scraper_t and scraper_t.is_alive())


@app.route("/api/autopilot")
def autopilot_status():
    import autopilot
    return jsonify({**autopilot.STATE, **{k: v for k, v in autopilot.settings().items() if k != "on"}})


@app.route("/api/moderation/unblock", methods=["POST"])
def moderation_unblock():
    """'Not a scam?' button in View Details: a blocked post goes to 'needs a look' (review)."""
    from output_handler import unblock
    data = request.get_json(silent=True) or {}
    if not unblock(str(data.get("id", ""))):
        return jsonify({"saved": False, "error": "no blocked listing with that id"}), 404
    return jsonify({"saved": True})


@app.route("/api/moderation/load-more", methods=["POST"])
def moderation_load_more():
    """'Load more' on the dashboard: send the next few scraped listings (round-robin) to the scam check."""
    from output_handler import release_held
    data = request.get_json(silent=True) or {}
    try:
        n = max(1, min(20, int(data.get("count") or 5)))
    except (TypeError, ValueError):
        n = 5
    released = release_held(n, str(data.get("run_tag") or ""))
    if released:
        from moderation.notify import start_scam_check
        threading.Thread(target=start_scam_check, args=("load more",), daemon=True).start()
    from output_handler import read_all_rows
    tag = str(data.get("run_tag") or "")
    left = sum(1 for r in read_all_rows() if r.get("moderation_status") == "held" and (not tag or r.get("last_run") == tag))
    return jsonify({"released": released, "held_left": left})


@app.route("/api/session/new", methods=["POST"])
def new_session():
    """A page load. The page starts with an empty view by itself; nothing is deleted here any more
    (wiping internships.csv lost verdicts still being saved and other people's results).
    Only posts no search has found for a few days are removed."""
    from output_handler import prune_old
    return jsonify({"status": "kept", "pruned": prune_old()})


@app.route("/api/scrape/status")
def scrape_status():
    global scraper_t
    import scraper as scraper_mod
    running = bool(scraper_t and scraper_t.is_alive())
    if running and QUEUE["waiting"]:   # the progress on record is the automatic update's, not this search's
        return jsonify({"status": "queued", "progress": None})
    return jsonify({"status": "running" if running else "idle", "progress": scraper_mod.RUN_PROGRESS})

@app.route("/api/logs")
def get_logs():
    log_file = Path(__file__).parent / "scraper_run.log"
    if not log_file.exists():
        return jsonify({"logs": ["No logs yet. Click 'Run Scraper Now' to start!"]})
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Return last N lines
            return jsonify({"logs": [l.strip() for l in lines[-75:]]})
    except Exception:
        return jsonify({"logs": ["The log file could not be read."]})


@app.route("/api/alerts")
def get_alerts():
    """Returns the current action-required alert, if any (polled every 2s by frontend)."""
    alert_file = Path(__file__).parent / "scraper_alerts.json"
    if not alert_file.exists():
        return jsonify({"alert": None})
    try:
        data = json.loads(alert_file.read_text(encoding="utf-8"))
        if data.get("resolved"):
            return jsonify({"alert": None})
        # no time limit: the alert asks for an action in the Chrome window (it is cleared when the
        # next search starts or "Done" is clicked)
        return jsonify({"alert": data})
    except Exception:
        return jsonify({"alert": None})


@app.route("/api/alerts/dismiss", methods=["POST"])
def dismiss_alert():
    """User clicked 'Done' on the dashboard — mark alert as resolved."""
    alert_file = Path(__file__).parent / "scraper_alerts.json"
    try:
        if alert_file.exists():
            data = json.loads(alert_file.read_text(encoding="utf-8"))
            data["resolved"] = True
            
            # Atomic write to prevent race condition data loss
            fd, temp_path = tempfile.mkstemp(dir=alert_file.parent, text=True)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            os.replace(temp_path, alert_file)
    except Exception:
        pass
    return jsonify({"status": "ok"})

@app.route("/api/clear", methods=["POST"])
def clear_data():
    """Clears all historical scraped data to start fresh."""
    global scraper_t
    if scraper_t and scraper_t.is_alive():
        return jsonify({"status": "error", "message": "Cannot clear data while scraper is running!"}), 400
        
    try:
        # Delete CSV Database
        if DATA_FILE.exists():
            DATA_FILE.unlink()
            
        # Delete JSON Logs memory
        log_file = Path(__file__).parent / "internships_log.json"
        if log_file.exists():
            log_file.unlink()
            
        # Delete text log file
        txt_log = Path(__file__).parent / "scraper_run.log"
        if txt_log.exists():
            try:
                txt_log.unlink()
            except PermissionError:
                # On Windows, loguru may hold a lock on this file while running
                with open(txt_log, "w", encoding="utf-8") as f:
                    pass
            
        return jsonify({"status": "success", "message": "All past data has been securely deleted. You have a fresh slate!"})
    except Exception as e:
        print(f"Clear failed: {e}")
        return jsonify({"status": "error", "message": "Could not delete the data files (is one open in another program?)."}), 500


def _hold_old_listings():
    from output_handler import hold_unreleased
    n = hold_unreleased()
    if n:
        print(f"{n} unchecked listings moved to 'held': they go to the scam check only via Load 5 more")


PUBLISH_EVERY_S = 15 * 60


def start_publish_loop():
    """Every verdict goes to Supabase at once (output_handler._share), but a send that fails (no
    internet, Supabase down) is not retried. This re-sends every judged post now and every 15
    minutes; an upsert, so sending one twice changes nothing."""
    import supabase_sync
    from output_handler import read_all_rows
    if not supabase_sync.enabled():
        return None

    def loop():
        while True:
            try:
                n = supabase_sync.publish(read_all_rows())
                if n:
                    print(f"Supabase: {n} judged post(s) up to date")
            except Exception as e:   # never stop the loop
                print(f"Supabase backfill failed: {e}")
            time.sleep(PUBLISH_EVERY_S)

    t = threading.Thread(target=loop, daemon=True, name="supabase-backfill")
    t.start()
    return t


if __name__ == "__main__":
    _hold_old_listings()
    # No automatic searching: sites are scraped only when someone presses Search Internships
    # (19 Oct: rounds at 17:24 and 23:24 opened 23 sites nobody asked for). autopilot.py stays
    # for a later server setup; nothing starts it here, whatever AUTO_UPDATE says.
    start_publish_loop()
    # The scam check runs inside the app, in its own thread (moderation/pipeline)
    from moderation.pipeline import start_worker
    start_worker()
    print("Scam check: running inside the app (moderation/pipeline)")
    port = int(os.environ.get("PORT", 5000))
    if os.environ.get("INREAL_DEBUG") == "1":
        # Flask's debugger can run code on this machine: only for local development, never with a tunnel
        app.run(debug=True, host="127.0.0.1", port=port)
    else:
        try:
            from waitress import serve
        except ImportError:
            sys.exit("Install the production server first:  pip install waitress")
        # 127.0.0.1 only: the tunnel connects locally, the Wi-Fi network can't reach the app directly
        host = os.environ.get("HOST", "127.0.0.1")
        shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
        print(f"InReal running on http://{shown}:{port}  (waitress, debug off)")
        serve(app, host=host, port=port, threads=8, ident="InReal")
