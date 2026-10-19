import re
import json
import csv
import threading
import time
from datetime import datetime
from pathlib import Path

# Paths relative to this file
DATA_DIR = Path(__file__).parent
LOG_FILE = DATA_DIR / "internships_log.json"
CSV_FILE = DATA_DIR / "internships.csv"

CSV_HEADERS = [
    "id", "company_name", "role_title", "location", "location_type",
    "duration", "stipend", "stipend_numeric", "stipend_currency",
    "required_skills", "application_deadline", "apply_link",
    "source_platform", "date_scraped", "is_new", 
    "org_type", "role_type", "match_score",
    "posted", "trust_flags",
    # text the n8n moderation pipeline reads, and what it decided
    "description", "moderation_status", "scam_risk", "moderation_reasons", "moderated_at",
    "field",   # which field of study the run searched for (fields.py); empty on old rows = ai_ml
    "last_run",   # tag of the latest search that found this post; the dashboard shows one search at a time
]
MODERATION_FIELDS = ["moderation_status", "scam_risk", "moderation_reasons", "moderated_at"]
# If any of these change, the listing is a different post and must be moderated again
CONTENT_FIELDS = ["company_name", "role_title", "stipend", "apply_link", "description"]
MODERATION_STATUSES = {"approved", "review", "blocked", "expired"}   # "checking" is set only by a claim
DESCRIPTION_LIMIT = 6000   # 19 Oct: a fee can sit near the end of a long post
# Sites whose search page gives only a snippet; the full text comes from the post page (sites/details.py)
SNIPPET_SOURCES = {"Talent.com", "SimplyHired", "Careerjet"}

# The scraper thread and the n8n verdict calls both write internships.csv
_CSV_LOCK = threading.RLock()

def load_log():
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "last_run": None,
        "total_scraped": 0,
        "seen_ids": [],
        "run_history": []
    }

def save_log(log_data):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)

def is_duplicate(internship_id: str, log_data: dict = None) -> bool:
    if log_data is None:
        log_data = load_log()
    return internship_id in log_data.get("seen_ids", [])

def _read_rows() -> list:
    if not CSV_FILE.exists():
        return []
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_rows(rows: list):
    rows.sort(key=lambda r: str(r.get("date_scraped", "")), reverse=True)
    tmp = CSV_FILE.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in CSV_HEADERS})
    # Windows refuses to replace a file another reader has open ("WinError 5 Access is denied",
    # laptop 12 Oct 10:46: one n8n verdict was lost and stayed "checking"). Retry briefly.
    for attempt in range(20):
        try:
            tmp.replace(CSV_FILE)   # the dashboard never reads a half-written file
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.1 * (attempt + 1))


def clean_description(text) -> str:
    """Spaces squeezed, line breaks kept (paragraphs, headings and '• ' points stay readable)."""
    lines = (" ".join(line.split()) for line in str(text or "").replace("\r", "\n").split("\n"))
    return "\n".join(line for line in lines if line)[:DESCRIPTION_LIMIT]


def _same_text(a, b) -> bool:
    """Equal apart from spacing and line breaks (a post saved as one line is not a changed post)."""
    return " ".join(str(a or "").split()) == " ".join(str(b or "").split())


def _record(item: dict) -> dict:
    rec = {k: item.get(k, "") for k in CSV_HEADERS if k not in MODERATION_FIELDS}
    rec["description"] = clean_description(item.get("description"))
    return rec


def sync_listings(kept: list, dropped_ids: list, max_new: int = None, hold: bool = False, run_tag: str = "") -> dict:
    """
    Saves one scraper run and keeps earlier rows up to date.

    The old append-only save never touched a row again, so a listing saved before a
    rule changed kept its old warnings forever (12 Oct 2026: "AI Intern" at Fireblaze
    AI School, saved at 06:52, never got the training-institute warning added at 07:15).
      - kept listing already saved   -> its fields are refreshed (trust_flags, stipend, ...)
      - kept listing not seen before -> added and marked new
      - listing this run re-checked and dropped -> removed from the dashboard
    Listings that simply did not appear in this run are left alone.
    The n8n verdict is kept unless the post's own text changed; then it is moderated again.
    """
    with _CSV_LOCK:
        log_data = load_log()
        seen_ids = set(log_data.setdefault("seen_ids", []))
        rows = _read_rows()
        by_id = {r.get("id"): r for r in rows}
        keep_as_is = {"id", "date_scraped", "is_new", "last_run", *MODERATION_FIELDS}
        added = updated = held = 0

        for item in kept:
            rec = _record(item)
            old = by_id.get(item["id"])
            if old is not None:
                changed = False
                if run_tag:
                    old["last_run"] = run_tag   # found again: shows in this search, verdict kept
                # includes a description arriving for a row saved before descriptions were stored
                # a search page's short snippet must not replace the full text read from the post's page
                # (only for these sites: elsewhere a shorter text can be a real edit, e.g. "pay a deposit")
                if (rec.get("source_platform") in SNIPPET_SOURCES
                        and len(str(rec.get("description") or "")) < len(str(old.get("description") or ""))):
                    rec["description"] = old.get("description")
                    if not str(rec.get("stipend") or "").strip() and str(old.get("stipend") or "").strip():
                        # ... and so must the stipend read from that full text (with its flags)
                        for k in ("stipend", "stipend_numeric", "stipend_currency", "trust_flags"):
                            rec[k] = old.get(k, "")
                content_changed = any(not _same_text(old.get(k, ""), rec.get(k, "")) if k == "description"
                                      else str(old.get(k, "") or "") != str(rec.get(k, "") or "")
                                      for k in CONTENT_FIELDS)
                for k, v in rec.items():
                    if k in keep_as_is:
                        continue
                    if k == "field":
                        # a post can match two fields (e.g. AI/ML and Data Analytics): keep both
                        have = [f for f in str(old.get("field") or "").split(";") if f]
                        if v and v not in have:
                            old["field"] = ";".join(have + [v])
                            changed = True
                        continue
                    if k == "description" and _same_text(old.get(k), v) and "\n" in str(old.get(k) or ""):
                        continue    # keep the version with its line breaks
                    if str(old.get(k, "") or "") != str(v if v is not None else ""):
                        old[k] = v
                        changed = True
                if content_changed and old.get("moderation_status") and old.get("moderation_status") != "held":
                    for k in MODERATION_FIELDS:
                        old[k] = ""
                    if hold:   # a changed post waits for "Load more" too, it doesn't jump into the pipeline
                        old["moderation_status"] = "held"
                updated += changed
            elif item["id"] not in seen_ids and max_new is not None and added >= max_new:
                # over this run's limit: not saved and not marked seen, so "Search more" finds it next time
                held += 1
            elif item["id"] not in seen_ids:
                rec["is_new"] = True
                rec["last_run"] = run_tag
                if hold:
                    # saved, but NOT sent to the scam check until "Load more" releases it (13 Oct night)
                    rec["moderation_status"] = "held"
                rows.append(rec)
                by_id[item["id"]] = rec
                seen_ids.add(item["id"])
                added += 1

        gone = set(dropped_ids) & set(by_id)
        if gone:
            rows = [r for r in rows if r.get("id") not in gone]
            seen_ids -= gone   # so it can come back if the post changes or the rules relax

        _write_rows(rows)
        log_data["seen_ids"] = sorted(seen_ids)
        log_data["total_scraped"] = len(seen_ids)
        log_data["last_run"] = datetime.now().strftime("%Y-%m-%d")
        save_log(log_data)
    out = {"added": added, "updated": updated, "removed": len(gone)}
    if max_new is not None:
        out["held"] = held
    return out


PENDING_FIELDS = ["id", "company_name", "role_title", "location", "duration", "stipend", "stipend_numeric",
                  "required_skills", "apply_link", "source_platform", "org_type", "trust_flags", "description"]


CLAIM_TIMEOUT_MIN = 4   # a "checking" claim older than this is treated as lost (n8n stopped mid-run)


def _is_pending(r: dict, now: datetime) -> bool:
    status = (r.get("moderation_status") or "").strip()
    if not status:
        return True
    if status == "checking":
        try:
            return (now - datetime.strptime(r.get("moderated_at", ""), "%Y-%m-%d %H:%M:%S")).total_seconds() > CLAIM_TIMEOUT_MIN * 60
        except ValueError:
            return True
    return False


def clear_all():
    """New session or new search: empty internships.csv and forget the seen IDs."""
    with _CSV_LOCK:
        _write_rows([])
        log = load_log()
        log["seen_ids"] = []
        log["total_scraped"] = 0
        save_log(log)


def round_robin(rows: list, limit: int) -> list:
    """[a1, a2, a3, b1, c1, c2] -> [a1, b1, c1, a2, c2, a3], cut to limit. Keeps each site's own order."""
    queues = {}
    for r in rows:
        queues.setdefault((r.get("source_platform") or "").strip().lower(), []).append(r)
    out, lists = [], list(queues.values())
    i = 0
    while len(out) < limit and any(lists):
        q = lists[i % len(lists)]
        if q:
            out.append(q.pop(0))
        i += 1
    return out


def hold_unreleased() -> int:
    """
    Listings with no status were saved before 'held' existed, or released and never picked up.
    They go back to 'held' at app start, so only a "Load 5 more" click ever sends listings to n8n
    (13 Oct 00:04: 30 old ones were checked on their own right after a Load more click).
    """
    with _CSV_LOCK:
        rows = _read_rows()
        moved = 0
        for r in rows:
            if not (r.get("moderation_status") or "").strip():
                r["moderation_status"] = "held"
                moved += 1
        if moved:
            _write_rows(rows)
    return moved


def mark_known(verdicts: dict, run_tag: str = "") -> int:
    """Held posts that the shared list already judged in an earlier automatic round take that
    verdict here and are not sent to the scam check again. Returns how many."""
    marked = 0
    with _CSV_LOCK:
        rows = _read_rows()
        for r in rows:
            v = verdicts.get(r.get("id"))
            if v in MODERATION_STATUSES and r.get("moderation_status") == "held" and (not run_tag or r.get("last_run") == run_tag):
                r["moderation_status"] = v
                r["moderation_reasons"] = "Judged in an earlier automatic round"
                r["moderated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                marked += 1
        if marked:
            _write_rows(rows)
    return marked


def release_held(n: int, run_tag: str = "") -> int:
    """'Load more': moves up to n held listings (round-robin across sites) into the scam-check queue.
    run_tag: only listings of that search (the one on screen)."""
    if n <= 0:
        return 0
    with _CSV_LOCK:
        rows = _read_rows()
        held = [r for r in rows if (r.get("moderation_status") or "").strip() == "held"
                and (not run_tag or r.get("last_run") == run_tag)]
        picked = round_robin(held, n)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in picked:
            # "checking" while the full posts are read, so a second click can't take them too
            # (and if this stops halfway, the claim timeout puts them back in the queue)
            r["moderation_status"] = "checking"
            r["moderated_at"] = now
        if picked:
            _write_rows(rows)
    if not picked:
        return 0

    # Sites that show only a snippet in search: read the post's own page first (sites/details.py),
    # outside the lock so the scraper can keep saving meanwhile.
    from sites.details import fill_details
    from sites.details import add_stipend
    copies = [dict(r) for r in picked]
    fill_details(copies, MIN_TEXT_TO_CHECK)
    added = sum(1 for c in copies
                if c.get("source_platform") in SNIPPET_SOURCES and add_stipend(c))   # also for posts read earlier
    stated = sum(1 for c in copies if c.get("source_platform") in SNIPPET_SOURCES and c.get("stipend"))
    if any(c.get("source_platform") in SNIPPET_SOURCES for c in copies):
        from loguru import logger
        logger.info(f"Stipend from the post text: {stated} of {len(copies)} state one ({added} filled now)")
    full = {c["id"]: c for c in copies}
    with _CSV_LOCK:
        rows = _read_rows()
        for r in rows:
            if r.get("id") in full and r.get("moderation_status") == "checking":
                c = full[r["id"]]
                if len(c.get("description") or "") > len(r.get("description") or ""):
                    r["description"] = clean_description(c["description"])
                if c.get("stipend") and not r.get("stipend"):   # the stipend the full post states
                    for k in ("stipend", "stipend_numeric", "stipend_currency", "trust_flags"):
                        r[k] = c.get(k, "")
                r["moderation_status"] = ""
                r["moderated_at"] = ""
        _write_rows(rows)
    return len(picked)


def pending_moderation(limit: int = 40, claim: bool = False) -> list:
    """
    Listings the n8n pipeline has not judged yet, taken ROUND-ROBIN across sites (one from each
    site in turn, newest first within a site), so a batch never goes to a single site while the
    others wait (13 Oct: a 400-listing Content & Media run filled every batch from two sites).
    claim=True marks them "checking", so a second n8n run started meanwhile (the scraper calls
    n8n after EACH site, so runs overlap) takes different listings instead of the same ones.
    """
    now = datetime.now()
    with _CSV_LOCK:
        rows = _read_rows()
        todo = round_robin([r for r in rows if _is_pending(r, now)], max(1, limit))
        if claim and todo:
            for r in todo:
                r["moderation_status"] = "checking"
                r["moderated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
            _write_rows(rows)
    return [{k: r.get(k, "") for k in PENDING_FIELDS} for r in todo]


def moderation_counts() -> dict:
    now = datetime.now()
    with _CSV_LOCK:
        rows = _read_rows()
    out = {"pending": 0, "checking": 0, "approved": 0, "review": 0, "blocked": 0, "expired": 0, "held": 0}
    for r in rows:
        st = (r.get("moderation_status") or "").strip()
        key = "pending" if _is_pending(r, now) else st
        out[key] = out.get(key, 0) + 1
    return out


MIN_TEXT_TO_CHECK = 300   # characters of post text the scam check needs to say anything


def approval_doubts(row: dict, reasons: str) -> list:
    """
    Reasons NOT to show an n8n "approved" as verified; the post goes to "review" instead.
    Added 18 Oct 2026 after a batch where every post was approved:
      1. the AI judge itself called it suspicious/scam and quoted the post (The SmartBridge and
         VDOIT were approved at risk 0.39, just under the 0.40 review line);
      2. the post had too little text to check (SimplyHired gave ~150 characters, so
         "no scam signs" only meant "nothing to read");
      3. the scam-wording search failed (embedding timeout), so only the AI judge had looked.
    """
    doubts = []
    if re.search(r"\bLLM: (suspicious|scam)\b", reasons, re.I) and "Quote:" in reasons:
        doubts.append("The AI judge called this suspicious and quoted the post, so a person should look")
    text = len(str(row.get("description", "")).strip())
    if text < MIN_TEXT_TO_CHECK:
        doubts.append(f"Only {text} characters of the post could be read, too little to check for scams")
    if "Embedding failed" in reasons:
        doubts.append("The scam-wording check did not run, so this was not approved on the AI judge alone")
    return doubts


def save_verdict(listing_id: str, status: str, scam_risk, reasons) -> bool:
    """Stores the n8n verdict on one listing. Returns False if the id is unknown."""
    if status == "retry":   # the checks could not run (API down): back to the queue
        with _CSV_LOCK:
            rows = _read_rows()
            row = next((r for r in rows if r.get("id") == listing_id), None)
            if row is None:
                return False
            for k in MODERATION_FIELDS:
                row[k] = ""
            _write_rows(rows)
        return True
    if status not in MODERATION_STATUSES:
        raise ValueError(f"status must be one of {sorted(MODERATION_STATUSES)} or 'retry'")
    risk = float(scam_risk)
    if not 0.0 <= risk <= 1.0:
        raise ValueError("scam_risk must be between 0 and 1")
    if isinstance(reasons, (list, tuple)):
        reasons = " | ".join(str(r).replace("|", "/").strip() for r in reasons if str(r).strip())
    with _CSV_LOCK:
        rows = _read_rows()
        row = next((r for r in rows if r.get("id") == listing_id), None)
        if row is None:
            return False
        if status == "approved":
            held_back = approval_doubts(row, str(reasons or ""))
            if held_back:
                status = "review"
                reasons = " | ".join(held_back + [str(reasons or "")])
        row.update({"moderation_status": status, "scam_risk": f"{risk:.2f}",
                    "moderation_reasons": str(reasons or "")[:1500],
                    "moderated_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
        _write_rows(rows)
    _share(row)
    return True


def _share(row: dict):
    """Puts a judged post on the shared list the website reads (Supabase), in the background."""
    try:
        from supabase_sync import publish_later
        publish_later([dict(row)])
    except Exception as e:   # the local app must keep working without Supabase
        print(f"Supabase publish skipped: {e}")


def unblock(listing_id: str) -> bool:
    """A person says a blocked post is not a scam: it moves to "review" (needs a look), with a note,
    and keeps its scam reasons so anyone can still see why it was blocked."""
    with _CSV_LOCK:
        rows = _read_rows()
        row = next((r for r in rows if r.get("id") == listing_id), None)
        if row is None or row.get("moderation_status") != "blocked":
            return False
        row["moderation_status"] = "review"
        row["moderation_reasons"] = " | ".join(filter(None, [
            f"Moved out of 'likely scam' by hand on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            row.get("moderation_reasons", "")]))[:1500]
        _write_rows(rows)
    _share(row)
    return True


def update_run_history(new_listings_count: int, sources_failed: list):
    log_data = load_log()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Check if we already have an entry for today
    history = log_data.get("run_history", [])
    today_entry = next((item for item in history if item["date"] == today_str), None)
    
    if today_entry:
        today_entry["new_listings"] += new_listings_count
        # Merge sources_failed without duplicates
        today_entry["sources_failed"] = list(set(today_entry.get("sources_failed", []) + sources_failed))
    else:
        history.append({
            "date": today_str,
            "new_listings": new_listings_count,
            "sources_failed": sources_failed
        })
        
    log_data["run_history"] = history
    log_data["last_run"] = today_str
    save_log(log_data)


def read_all_rows() -> list:
    """For the dashboard: read under the same lock the writers use, so a read never blocks a write."""
    with _CSV_LOCK:
        return _read_rows()
