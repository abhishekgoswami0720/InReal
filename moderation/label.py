"""Label checked posts by hand, so the scam check can be measured (2 Nov 2026).

    python -m moderation.label                     # judged posts in internships.csv not labelled yet
    python -m moderation.label --source Internshala --limit 30
    python -m moderation.label --show-verdict      # also show what InReal decided (see below)

For each post: s = scam, g = genuine, u = can't tell, k = skip for now, b = back to the last one, q = quit.
Every answer is saved at once in moderation/labels.jsonl, with a copy of the post and the verdict it had,
so the label still counts after the post is pruned from internships.csv (3 days).

The verdict is HIDDEN by default: a person who sees "Verified" first tends to agree with it, and then the
measurement measures nothing. Label from the post, then run  python -m moderation.accuracy.

Posts are offered by turns from each verdict (verified, needs a look, likely scam), so the labelled set is
not 90% verified posts just because most posts are.
"""
import argparse
import json
import textwrap
from datetime import datetime
from pathlib import Path

LABELS = Path(__file__).with_name("labels.jsonl")
JUDGED = ("approved", "review", "blocked")
SNAPSHOT_FIELDS = ("id", "role_title", "company_name", "source_platform", "apply_link", "stipend",
                   "location", "trust_flags", "description")
ANSWERS = {"s": "scam", "g": "genuine", "u": "unsure"}


def load_labels(path: Path = LABELS) -> dict:
    """id -> the latest label line for it."""
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("id"):
                    out[rec["id"]] = rec
    return out


def save_label(row: dict, label: str, path: Path = LABELS) -> dict:
    rec = {
        "id": row["id"],
        "label": label,
        "labelled_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "post": {k: str(row.get(k, "") or "")[:6000] for k in SNAPSHOT_FIELDS},
        "verdict": {"status": row.get("moderation_status", ""), "scam_risk": row.get("scam_risk", ""),
                    "reasons": str(row.get("moderation_reasons", "") or "")[:1500]},
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def to_label(rows: list, labelled: dict, source: str = "", limit: int = 0) -> list:
    """Judged, not yet labelled posts, taken by turns from each verdict."""
    groups = {s: [] for s in JUDGED}
    for r in rows:
        status = (r.get("moderation_status") or "").strip()
        if status in groups and r.get("id") not in labelled:
            if not source or (r.get("source_platform") or "").lower() == source.lower():
                groups[status].append(r)
    out = []
    while any(groups.values()):
        for s in JUDGED:
            if groups[s]:
                out.append(groups[s].pop(0))
    return out[:limit] if limit else out


def show(row: dict, n: int, total: int, with_verdict: bool):
    print("\n" + "=" * 78)
    print(f"[{n}/{total}]  {row.get('role_title', '')}  at  {row.get('company_name', '')}")
    print(f"Site: {row.get('source_platform', '')}   Stipend: {row.get('stipend', '') or 'not stated'}   "
          f"Where: {row.get('location', '')}")
    print(f"Link: {row.get('apply_link', '')}")
    if row.get("trust_flags"):
        print(f"Notes from the site checks: {row['trust_flags']}")
    print("-" * 78)
    desc = str(row.get("description", "") or "(no text)")
    for para in desc.split("\n")[:60]:
        print(textwrap.fill(para, 78) if para.strip() else "")
    if with_verdict:
        print("-" * 78)
        print(f"InReal said: {row.get('moderation_status')} (risk {row.get('scam_risk')})  {row.get('moderation_reasons', '')[:300]}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Label checked posts as scam / genuine")
    ap.add_argument("--source", default="", help="only posts from this site, e.g. Internshala")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many")
    ap.add_argument("--show-verdict", action="store_true", help="also show InReal's verdict (biases the label)")
    args = ap.parse_args(argv)

    from output_handler import read_all_rows
    labelled = load_labels()
    queue = to_label(read_all_rows(), labelled, args.source, args.limit)
    if not queue:
        print(f"Nothing to label: every judged post is labelled ({len(labelled)} so far). Run a search first.")
        return
    print(f"{len(queue)} post(s) to label, {len(labelled)} labelled before. "
          "s = scam, g = genuine, u = can't tell, k = skip, b = back, q = quit")
    i, done = 0, []
    while i < len(queue):
        row = queue[i]
        show(row, i + 1, len(queue), args.show_verdict)
        ans = input("Scam (s) / genuine (g) / can't tell (u) / skip (k) / back (b) / quit (q)? ").strip().lower()
        if ans == "q":
            break
        if ans == "b":
            i = max(0, i - 1)
            continue
        if ans == "k":
            i += 1
            continue
        if ans in ANSWERS:
            save_label(row, ANSWERS[ans])   # a later answer for the same post replaces the earlier one
            done.append(ans)
            i += 1
        else:
            print("Type s, g, u, k, b or q.")
    print(f"\nSaved {len(done)} label(s) in {LABELS.name}. Now:  python -m moderation.accuracy")


if __name__ == "__main__":
    main()
