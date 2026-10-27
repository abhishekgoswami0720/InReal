"""
NOT STARTED BY THE APP (20 Oct 2026): sites are scraped only when someone presses Search
Internships, and only the sites they pick. This module is kept for a later server setup; app.py
no longer calls start(), and the /api/autopilot/run route is gone. To bring it back is a decision,
not a setting.

Automatic update: keeps the shared list (Supabase) fresh without anyone clicking "Search" or
"Load 5 more". Was run inside the app when AUTO_UPDATE=on in .env:

    AUTO_UPDATE=on
    AUTO_EVERY_HOURS=6              # how often a full round runs
    AUTO_FIELDS=software            # comma-separated field keys (fields.py); each one is a separate search
    AUTO_LIMIT=120                  # at most this many new posts per field per round

Each round, for every field: search every live site, skip the posts the shared list already has a
verdict for (they were checked in an earlier round; each check costs Azure tokens), send the rest
to the scam check, and keep waking the scam check until all are judged. Every verdict is published to
Supabase by output_handler.save_verdict. Sites that open a Chrome window (Naukri, Foundit,
SimplyHired, Careerjet, Meta) open it on this laptop during a round.

A person's search comes first: started during a round, it is queued, the round stops after the
site search it is in (the posts already found keep going through the scam check), and the search
starts. A round waits while a manual search runs.
"""
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from loguru import logger

STATE = {"enabled": False, "busy": False, "checking": False, "field": "", "last_round": "",
         "next_round": "", "last_result": {}, "error": "", "yield": False}
_lock = threading.Lock()
JUDGE_TIMEOUT_S = 90 * 60
LAST_ROUND_FILE = Path(__file__).parent / ".cache" / "autopilot_last_round.txt"


def _last_round_at() -> float:
    """When the last round started (seconds since 1970), 0 if never. Kept on disk so a restart of
    the app does not start a new 23-site round every time (19 Oct: one restart, one full round)."""
    try:
        return float(LAST_ROUND_FILE.read_text().strip())
    except (OSError, ValueError):
        return 0.0


def _mark_round_started():
    try:
        LAST_ROUND_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_ROUND_FILE.write_text(str(time.time()))
    except OSError:
        pass


def first_delay(every_h: float, now: float = None) -> float:
    """Seconds until the first round after the app starts: when the last one is due again,
    at least 2 minutes from now."""
    now = now or time.time()
    return max(120.0, _last_round_at() + every_h * 3600 - now)


def settings():
    from moderation.env import load_env
    load_env()
    import fields as F
    wanted = [f.strip() for f in os.environ.get("AUTO_FIELDS", "software").split(",") if f.strip()]
    return {
        "on": os.environ.get("AUTO_UPDATE", "").strip().lower() in ("on", "1", "true", "yes"),
        "every_h": max(1.0, float(os.environ.get("AUTO_EVERY_HOURS", "6") or 6)),
        "fields": [f for f in wanted if f in F.FIELDS],
        "limit": max(10, int(os.environ.get("AUTO_LIMIT", "120") or 120)),
    }


def busy() -> bool:
    return STATE["busy"]


def live_sources():
    from sites import registry
    return [s["key"] for s in registry.SITES if s["status"] in ("tested",)]


def _skip_known(run_tag: str) -> int:
    """Held posts the shared list already judged get that verdict locally and are not re-checked."""
    import output_handler as oh
    from supabase_sync import known_verdicts
    held = [r for r in oh.read_all_rows() if r.get("last_run") == run_tag and r.get("moderation_status") == "held"]
    known = known_verdicts([r["id"] for r in held])
    return oh.mark_known(known, run_tag) if known else 0


def _wait_for_verdicts(run_tag: str):
    import output_handler as oh
    from moderation.notify import start_scam_check
    STATE["checking"] = True
    try:
        start_scam_check("automatic update")
        start, last_kick = time.time(), time.time()
        while time.time() - start < JUDGE_TIMEOUT_S:
            if STATE["yield"]:      # someone is waiting to search; the scam check's own rounds finish these
                return
            rows = [r for r in oh.read_all_rows() if r.get("last_run") == run_tag]
            waiting = sum(1 for r in rows if (r.get("moderation_status") or "") in ("", "checking"))
            if not waiting:
                return
            if time.time() - last_kick > 300:    # no verdict for 5 min with work left: wake the check again
                start_scam_check("automatic update (still waiting)")
                last_kick = time.time()
            time.sleep(15)
        logger.warning(f"Automatic update: {run_tag} still had posts unjudged after {JUDGE_TIMEOUT_S // 60} min")
    finally:
        STATE["checking"] = False


def run_round(manual_scrape_running=lambda: False):
    """One round over every configured field. Returns {field: {...counts}}."""
    import output_handler as oh
    from scraper import run_scrapers
    cfg = settings()
    if not cfg["fields"]:
        STATE["error"] = "AUTO_FIELDS names no known field"
        return {}
    with _lock:
        if STATE["busy"] or manual_scrape_running():
            return {}
        STATE["busy"] = True
    _mark_round_started()
    result = {}
    try:
        for field in cfg["fields"]:
            if STATE["yield"]:
                logger.info("Automatic update: stopped early, a search is waiting")
                break
            STATE["field"] = field
            run_tag = f"auto-{datetime.now().strftime('%Y%m%d-%H%M')}-{field}"
            logger.info(f"Automatic update: searching {field} on {len(live_sources())} sites ({run_tag})")
            run_scrapers(dry_run=False, config={"field": field, "sources": live_sources(),
                                                "regions": ["india", "usa", "europe", "remote", "worldwide"],
                                                "limit": cfg["limit"], "run_tag": run_tag})
            skipped = _skip_known(run_tag)
            held = sum(1 for r in oh.read_all_rows() if r.get("last_run") == run_tag and r.get("moderation_status") == "held")
            released = oh.release_held(held, run_tag) if held else 0
            logger.info(f"Automatic update: {field}: {released} new post(s) to the scam check, {skipped} already judged earlier")
            if released:
                _wait_for_verdicts(run_tag)
            result[field] = {"to_check": released, "known": skipped}
        STATE["last_result"] = result
        STATE["error"] = ""
        return result
    except Exception as e:   # a failed round must not stop the next one
        logger.exception(f"Automatic update failed: {e}")
        STATE["error"] = str(e)[:300]
        return result
    finally:
        STATE["busy"] = False
        STATE["yield"] = False
        STATE["field"] = ""
        STATE["last_round"] = datetime.now().strftime("%Y-%m-%d %H:%M")


def start(manual_scrape_running):
    """Background loop: a round every AUTO_EVERY_HOURS, counted from the last round even across
    restarts (the first one ever starts 2 minutes after start)."""
    cfg = settings()
    STATE["enabled"] = cfg["on"]
    if not cfg["on"]:
        return None

    def loop():
        delay = first_delay(cfg["every_h"])
        while True:
            STATE["next_round"] = datetime.fromtimestamp(time.time() + delay).strftime("%Y-%m-%d %H:%M")
            time.sleep(delay)
            if manual_scrape_running():
                delay = 600          # a manual search is on: try again in 10 minutes
                continue
            run_round(manual_scrape_running)
            delay = settings()["every_h"] * 3600

    t = threading.Thread(target=loop, daemon=True, name="autopilot")
    t.start()
    nxt = datetime.fromtimestamp(time.time() + first_delay(cfg["every_h"])).strftime("%d %b %H:%M")
    logger.info(f"Automatic update on: every {cfg['every_h']} h, fields {', '.join(cfg['fields'])}; next round {nxt}")
    return t
