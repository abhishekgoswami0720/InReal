from flask import Flask, render_template, jsonify, request
import pandas as pd
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
from output_handler import moderation_counts, pending_moderation, save_verdict
from moderation.env import load_env
from moderation.link_check import resolve as resolve_link

load_env()
app = Flask(__name__)
DATA_FILE = Path(__file__).parent / "internships.csv"
PATTERN_INDEX = Path(__file__).parent / "moderation" / "pattern_index.json"

# Global state for scraping
scraper_t = None

@app.route("/")
def index():
    return render_template("index.html")

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

@app.route("/api/scrape", methods=["POST"])
def trigger_scrape():
    global scraper_t
    
    if scraper_t and scraper_t.is_alive():
        return jsonify({"status": "running", "message": "Scraping is already in progress!"})
        
    config = request.json if request.is_json else None
        
    def scrape_job(cfg):
        # Running the full scraper
        run_scrapers(dry_run=False, config=cfg)   # calls n8n after each site (moderation/notify.py)
        
    scraper_t = threading.Thread(target=scrape_job, args=(config,))
    scraper_t.start()
    
    return jsonify({"status": "started", "message": "Scraper started successfully. This might take a while."})

# ---- Moderation API, called by the n8n workflow in n8n/inreal_moderation.json ----

@app.route("/api/moderation/pending")
def moderation_pending():
    try:
        limit = int(request.args.get("limit", 40))
    except ValueError:
        limit = 40
    return jsonify(pending_moderation(limit, claim=request.args.get("claim") == "1"))


@app.route("/api/moderation/status")
def moderation_status():
    return jsonify(moderation_counts())


@app.route("/api/moderation/patterns")
def moderation_patterns():
    if not PATTERN_INDEX.exists():
        return jsonify({"error": "moderation/pattern_index.json is missing. Run: python -m moderation.build_index"}), 404
    return app.response_class(PATTERN_INDEX.read_text(encoding="utf-8"), mimetype="application/json")


@app.route("/api/moderation/resolve")
def moderation_resolve():
    """Opens one listing's apply link: redirect chain, final domain, status, 'closed' wording."""
    listing_id = request.args.get("id", "")
    from output_handler import _read_rows
    row = next((r for r in _read_rows() if r.get("id") == listing_id), None)
    if row is None:
        return jsonify({"id": listing_id, "error": "unknown id"}), 404
    return jsonify({"id": listing_id, **resolve_link(row.get("apply_link", ""))})


@app.route("/api/moderation/verdict", methods=["POST"])
def moderation_verdict():
    data = request.get_json(silent=True) or {}
    try:
        ok = save_verdict(str(data.get("id", "")), str(data.get("status", "")),
                          data.get("scam_risk", 0), data.get("reasons", []))
    except (TypeError, ValueError) as e:
        return jsonify({"saved": False, "error": str(e)}), 400
    if not ok:
        return jsonify({"saved": False, "error": "unknown id"}), 404
    return jsonify({"saved": True, "id": data.get("id"), "status": data.get("status")})


@app.route("/api/scrape/status")
def scrape_status():
    global scraper_t
    import scraper as scraper_mod
    running = bool(scraper_t and scraper_t.is_alive())
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
    except Exception as e:
        return jsonify({"logs": [f"Error reading logs: {e}"]})


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
        # Auto-expire alerts older than 120 seconds
        ts_str = data.get("timestamp", "")
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
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
