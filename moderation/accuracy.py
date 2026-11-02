"""How good is the scam check? Compares InReal's verdicts with the hand labels in labels.jsonl (2 Nov 2026).

    python -m moderation.accuracy              # the verdict each post had when it was labelled (free)
    python -m moderation.accuracy --rerun      # run TODAY's scam check again on the labelled posts
                                               # (costs Azure calls; use it after changing a rule or prompt)
    python -m moderation.accuracy --save       # also write moderation/accuracy_report.md

What it reports, counting only posts labelled scam or genuine ("can't tell" and closed posts are left out):
  scams caught    : scams InReal hid as "likely scam"
  scams flagged   : scams hidden OR sent to "needs a look" (not shown as Verified)
  scams missed    : scams shown as Verified, the worst mistake for a student
  genuine blocked : real internships hidden as scams, the worst mistake for a company
  genuine to look : real internships sent to "needs a look"
Each rate comes with a 95% range (Wilson): with 20 scams, "90%" can really be anywhere from about 70% to 97%.
"""
import argparse
import math
from datetime import datetime
from pathlib import Path

from moderation.label import load_labels

REPORT = Path(__file__).with_name("accuracy_report.md")


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """95% range of a rate k/n (Wilson score interval), as fractions."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def score(pairs: list) -> dict:
    """pairs: (label, status). Returns counts and rates."""
    scams = [s for lab, s in pairs if lab == "scam" and s in ("approved", "review", "blocked")]
    genuine = [s for lab, s in pairs if lab == "genuine" and s in ("approved", "review", "blocked")]

    def rate(k, n):
        lo, hi = wilson(k, n)
        return {"k": k, "n": n, "rate": (k / n if n else 0.0), "lo": lo, "hi": hi}

    return {
        "scams": len(scams), "genuine": len(genuine),
        "left_out": len(pairs) - len(scams) - len(genuine),
        "scams_caught": rate(scams.count("blocked"), len(scams)),
        "scams_flagged": rate(scams.count("blocked") + scams.count("review"), len(scams)),
        "scams_missed": rate(scams.count("approved"), len(scams)),
        "genuine_blocked": rate(genuine.count("blocked"), len(genuine)),
        "genuine_review": rate(genuine.count("review"), len(genuine)),
        "genuine_verified": rate(genuine.count("approved"), len(genuine)),
    }


def _pct(r: dict) -> str:
    if not r["n"]:
        return "n/a"
    return f"{r['rate'] * 100:.0f}%  ({r['k']}/{r['n']}, 95% range {r['lo'] * 100:.0f}–{r['hi'] * 100:.0f}%)"


def report(s: dict, mistakes: list, how: str) -> str:
    lines = [
        f"# Scam check accuracy ({datetime.now():%d %b %Y})",
        "",
        f"{s['scams']} posts labelled scam and {s['genuine']} labelled genuine by hand "
        f"({s['left_out']} left out: can't tell or closed). Verdicts: {how}.",
        "",
        "| | |",
        "|---|---|",
        f"| Scams caught (hidden) | {_pct(s['scams_caught'])} |",
        f"| Scams flagged (hidden or needs a look) | {_pct(s['scams_flagged'])} |",
        f"| **Scams shown as Verified** | {_pct(s['scams_missed'])} |",
        f"| **Genuine posts hidden as scams** | {_pct(s['genuine_blocked'])} |",
        f"| Genuine posts sent to needs a look | {_pct(s['genuine_review'])} |",
        f"| Genuine posts verified | {_pct(s['genuine_verified'])} |",
    ]
    if s["scams"] + s["genuine"] < 100:
        lines += ["", "_Fewer than 100 labelled posts: the ranges are wide. Label more before quoting these numbers._"]
    if mistakes:
        lines += ["", "## The two worst kinds of mistake", ""]
        for m in mistakes:
            lines.append(f"- **{m['kind']}**: {m['title']} at {m['company']} ({m['site']}): {m['reasons'][:200]}")
    return "\n".join(lines) + "\n"


def collect(labels: dict, rerun: bool = False) -> tuple:
    """(label, status) pairs and the worst mistakes. rerun=True judges the saved posts again (Azure)."""
    recs = [r for r in labels.values() if r.get("label") in ("scam", "genuine", "unsure")]
    if rerun:
        from moderation.pipeline.runner import judge_posts
        posts = [dict(r["post"]) for r in recs]
        verdicts = {v["id"]: v for v in judge_posts(posts)} if posts else {}
        status = {i: (v["status"], " | ".join(v.get("reasons") or [])) for i, v in verdicts.items()}
    else:
        status = {r["id"]: (r["verdict"].get("status", ""), r["verdict"].get("reasons", "")) for r in recs}
    pairs, mistakes = [], []
    for r in recs:
        st, why = status.get(r["id"], ("", ""))
        pairs.append((r["label"], st))
        kind = ("Scam shown as Verified" if r["label"] == "scam" and st == "approved"
                else "Genuine post hidden" if r["label"] == "genuine" and st == "blocked" else "")
        if kind:
            p = r["post"]
            mistakes.append({"kind": kind, "title": p.get("role_title", ""), "company": p.get("company_name", ""),
                             "site": p.get("source_platform", ""), "reasons": why})
    return pairs, mistakes


def main(argv=None):
    ap = argparse.ArgumentParser(description="Measure the scam check against the hand labels")
    ap.add_argument("--rerun", action="store_true", help="judge the labelled posts again with today's check (Azure)")
    ap.add_argument("--save", action="store_true", help=f"also write {REPORT.name}")
    args = ap.parse_args(argv)
    labels = load_labels()
    if not labels:
        print("No labels yet. Label some posts first:  python -m moderation.label")
        return
    pairs, mistakes = collect(labels, args.rerun)
    text = report(score(pairs), mistakes, "today's check run again" if args.rerun else "as saved when labelled")
    print(text)
    if args.save:
        REPORT.write_text(text, encoding="utf-8")
        print(f"Saved {REPORT}")


if __name__ == "__main__":
    main()
