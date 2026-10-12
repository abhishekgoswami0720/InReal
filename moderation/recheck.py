"""
Puts already-judged listings back in the n8n queue and starts the workflow.

    python -m moderation.recheck              # posts whose AI check failed (e.g. "Embedding failed")
    python -m moderation.recheck --source unstop --limit 10
    python -m moderation.recheck --all        # every listing (costs Azure calls for all of them)

Use it after fixing keys or switching models. Run it while no scrape is in progress.
"""
import argparse

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
    a = ap.parse_args()
    n = requeue(a.source, a.all, a.limit)
    print(f"{n} listing(s) back in the queue")
    if n:
        from moderation.notify import notify_n8n
        notify_n8n("recheck")
        print("n8n notified (check its Executions tab). If n8n isn't running, click Execute workflow later.")


if __name__ == "__main__":
    main()
