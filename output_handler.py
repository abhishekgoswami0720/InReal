import json
import csv
import pandas as pd
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
    "posted", "trust_flags"
]

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

def append_to_csv(internships: list) -> int:
    """
    Saves a list of internship dicts to CSV. 
    Also updates the json log.
    Returns: Number of new records added.
    """
    if not internships:
        return 0
        
    log_data = load_log()
    seen_ids = set(log_data.setdefault("seen_ids", []))
    
    new_records = []
    
    for item in internships:
        if item["id"] not in seen_ids:
            item["is_new"] = True
            new_records.append(item)
            seen_ids.add(item["id"])
        
    if not new_records:
        return 0
        
    log_data["seen_ids"] = list(seen_ids)
    log_data["total_scraped"] = len(seen_ids)
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_data["last_run"] = today_str
    
    file_exists = CSV_FILE.exists()
    if file_exists:
        # Older CSVs were written before new columns were added; rewrite the header once
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            header = f.readline().strip().split(",")
        if header != CSV_HEADERS:
            old = pd.read_csv(CSV_FILE)
            old.reindex(columns=CSV_HEADERS).to_csv(CSV_FILE, index=False)
    
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        for rec in new_records:
            filtered_rec = {k: rec.get(k, "") for k in CSV_HEADERS}
            writer.writerow(filtered_rec)
            
    # Read and sort by date_scraped descending
    try:
        df = pd.read_csv(CSV_FILE)
        if "date_scraped" in df.columns:
            df["date_scraped"] = pd.to_datetime(df["date_scraped"], errors='coerce')
            df = df.sort_values(by="date_scraped", ascending=False)
            df["date_scraped"] = df["date_scraped"].dt.strftime("%Y-%m-%d")
            df.to_csv(CSV_FILE, index=False)
    except Exception as e:
        print(f"Warning: Could not sort CSV: {e}")
            
    save_log(log_data)
    return len(new_records)
    
def _read_rows() -> list:
    if not CSV_FILE.exists():
        return []
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sync_listings(kept: list, dropped_ids: list) -> dict:
    """
    Saves one scraper run and keeps earlier rows up to date.

    The old append-only save never touched a row again, so a listing saved before a
    rule changed kept its old warnings forever (12 Oct 2026: "AI Intern" at Fireblaze
    AI School, saved at 06:52, never got the training-institute warning added at 07:15).
      - kept listing already saved   -> its fields are refreshed (trust_flags, stipend, ...)
      - kept listing not seen before -> added and marked new
      - listing this run re-checked and dropped -> removed from the dashboard
    Listings that simply did not appear in this run are left alone.
    """
    log_data = load_log()
    seen_ids = set(log_data.setdefault("seen_ids", []))
    rows = _read_rows()
    by_id = {r.get("id"): r for r in rows}
    keep_as_is = {"id", "date_scraped", "is_new"}
    added = updated = 0

    for item in kept:
        rec = {k: item.get(k, "") for k in CSV_HEADERS}
        old = by_id.get(item["id"])
        if old is not None:
            changed = False
            for k in CSV_HEADERS:
                if k in keep_as_is:
                    continue
                if str(old.get(k, "") or "") != str(rec[k] if rec[k] is not None else ""):
                    old[k] = rec[k]
                    changed = True
            updated += changed
        elif item["id"] not in seen_ids:
            rec["is_new"] = True
            rows.append(rec)
            by_id[item["id"]] = rec
            seen_ids.add(item["id"])
            added += 1

    gone = set(dropped_ids) & set(by_id)
    if gone:
        rows = [r for r in rows if r.get("id") not in gone]
        seen_ids -= gone   # so it can come back if the post changes or the rules relax

    rows.sort(key=lambda r: str(r.get("date_scraped", "")), reverse=True)
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in CSV_HEADERS})

    log_data["seen_ids"] = sorted(seen_ids)
    log_data["total_scraped"] = len(seen_ids)
    log_data["last_run"] = datetime.now().strftime("%Y-%m-%d")
    save_log(log_data)
    return {"added": added, "updated": updated, "removed": len(gone)}


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
