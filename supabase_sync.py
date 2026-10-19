"""
Laptop -> Supabase: puts judged listings on the shared list the website reads (table `listings`,
see supabase/schema.sql). Called after every n8n verdict and after an unblock; can also push
everything judged in the local CSV:

    python -m supabase_sync            # push every approved / review / blocked row in internships.csv

Uses SUPABASE_URL and SUPABASE_SECRET_KEY from .env. The secret key bypasses row-level security,
so it stays on this laptop; it is sent on the `apikey` header only (the new sb_secret_ keys are not
JWTs and are refused on `Authorization: Bearer`). verified_at / first_seen_at are set by a database
trigger, so re-sending a row never moves them. Nothing here ever raises: if Supabase is down or not
set up, the local app keeps working and the row is pushed again with its next verdict or backfill.
"""
import os
import sys
import threading

import requests
from loguru import logger

PUBLISHED = {"approved", "review", "blocked"}
COLUMNS = ["id", "source_platform", "company_name", "role_title", "location", "location_type", "duration",
           "stipend", "stipend_numeric", "stipend_currency", "required_skills", "apply_link", "description",
           "org_type", "posted", "trust_flags", "scam_risk", "moderation_reasons"]
TIMEOUT = 20
CHUNK = 200


def settings():
    from moderation.env import load_env
    load_env()
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    return url, key


def enabled() -> bool:
    url, key = settings()
    return bool(url and key)


def _number(value):
    try:
        return float(value) if str(value).strip() not in ("", "None", "nan") else None
    except (TypeError, ValueError):
        return None


def to_listing(row: dict):
    """One CSV row -> one `listings` record, or None if it has no verdict to publish."""
    status = (row.get("moderation_status") or "").strip()
    if status not in PUBLISHED or not row.get("id") or not row.get("role_title"):
        return None
    rec = {k: (row.get(k) if row.get(k) not in ("",) else None) for k in COLUMNS}
    rec["stipend_numeric"] = _number(row.get("stipend_numeric"))
    rec["scam_risk"] = _number(row.get("scam_risk"))
    rec["source_platform"] = row.get("source_platform") or "Unknown"
    rec["fields"] = [f for f in str(row.get("field") or "").split(";") if f]
    rec["status"] = status
    return rec


def publish(rows) -> int:
    """Upserts the judged rows; returns how many Supabase accepted (0 if off or failed)."""
    url, key = settings()
    records = [r for r in (to_listing(row) for row in rows) if r]
    if not (url and key) or not records:
        return 0
    headers = {"apikey": key, "Content-Type": "application/json",
               "Prefer": "resolution=merge-duplicates,return=minimal"}
    sent = 0
    for i in range(0, len(records), CHUNK):
        part = records[i:i + CHUNK]
        try:
            r = requests.post(f"{url}/rest/v1/listings?on_conflict=id", json=part, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            logger.warning(f"Supabase: could not reach {url.split('//')[-1]} ({type(e).__name__}); {len(part)} listing(s) not published")
            return sent
        if r.status_code >= 300:
            logger.warning(f"Supabase: HTTP {r.status_code} publishing {len(part)} listing(s): {r.text[:200]}")
            return sent
        sent += len(part)
    return sent


def known_verdicts(ids) -> dict:
    """{id: status} for the ids already on the shared list, so the automatic update doesn't send
    posts judged in an earlier run to the scam check again (each check costs Azure tokens)."""
    url, key = settings()
    ids = [str(i) for i in ids if i]
    if not (url and key) or not ids:
        return {}
    out = {}
    for i in range(0, len(ids), 100):
        part = ids[i:i + 100]
        try:
            r = requests.get(f"{url}/rest/v1/listings", headers={"apikey": key}, timeout=TIMEOUT,
                             params={"select": "id,status", "id": "in.(" + ",".join(part) + ")"})
            r.raise_for_status()
            out.update({x["id"]: x["status"] for x in r.json()})
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"Supabase: could not look up earlier verdicts ({type(e).__name__})")
            break
    return out


def publish_later(rows):
    """Same, in the background, so a verdict from n8n is answered at once."""
    if enabled():
        threading.Thread(target=publish, args=(list(rows),), daemon=True).start()


def main():
    from output_handler import read_all_rows
    if not enabled():
        sys.exit("SUPABASE_URL and SUPABASE_SECRET_KEY are not both set in .env")
    rows = read_all_rows()
    n = publish(rows)
    judged = sum(1 for r in rows if to_listing(r))
    print(f"Published {n} of {judged} judged listing(s) to Supabase")


if __name__ == "__main__":
    main()
