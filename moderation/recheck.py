"""
Puts already-judged listings back in the n8n queue and starts the workflow.

    python -m moderation.recheck              # posts whose AI check failed (e.g. "Embedding failed")
    python -m moderation.recheck --source unstop --limit 10
    python -m moderation.recheck --all        # every listing (costs Azure calls for all of them)

Use it after fixing keys or switching models. The listings live in memory inside app.py, so this
asks the running app (POST /api/moderation/recheck on 127.0.0.1) to do it. app.py must be running.
"""
import argparse
import os

from output_handler import MODERATION_FIELDS, _CSV_LOCK, _read_rows, _write_rows

FAILED_MARKERS = ("Embedding failed", "LLM judge unavailable")


def requeue(source: str = "", all_rows: bool = False, limit: int = 0) -> int:
    with _CSV_LOCK:
        rows = _read_rows()
        picked = []
        for r in rows:
            if not (r.get("moderation_status") or "").strip() or r.get("moderation_status") == "checking":
                continue                       # already waiting
            if source and r.get("source_platform", "").strip().lower() != source.lower():
                continue
            if not (all_rows or source) and not any(m in (r.get("moderation_reasons") or "") for m in FAILED_MARKERS):
                continue
            picked.append(r)
            if limit and len(picked) >= limit:
                break
        for r in picked:
            for k in MODERATION_FIELDS:
                r[k] = ""
        if picked:
            _write_rows(rows)
    return len(picked)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="", help="only this site, e.g. unstop, internshala")
    ap.add_argument("--all", action="store_true", help="every judged listing, not only failed ones")
    ap.add_argument("--limit", type=int, default=0, help="at most this many")
    ap.add_argument("--app", default=f"http://127.0.0.1:{os.environ.get('PORT', 5000)}", help="where app.py runs")
    a = ap.parse_args()
    import requests
    try:
        r = requests.post(f"{a.app}/api/moderation/recheck", json={"source": a.source, "all": a.all, "limit": a.limit}, timeout=30)
    except requests.exceptions.RequestException:
        raise SystemExit(f"app.py is not running at {a.app}. Start it first: the listings only exist inside it.")
    if r.status_code != 200:
        raise SystemExit(f"App answered HTTP {r.status_code}: {r.text[:200]}")
    n = r.json()["requeued"]
    print(f"{n} listing(s) back in the queue" + (" and n8n notified (check its Executions tab)" if n else ""))


if __name__ == "__main__":
    main()
