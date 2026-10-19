"""
Does the LLM judge actually catch scams? Runs the test posts in moderation/judge_cases.json
(9 scams written the way real ones hide the trick, 9 genuine posts that look risky at first sight)
through the SAME request n8n sends, then scores the answers.

    python -m moderation.eval_judge            # all 18 posts, 3 calls of up to 8 posts (~20k tokens)
    python -m moderation.eval_judge --only s_late_fee,g_unpaid_ngo

Reads the judge URL and key from .env like check_azure.py. Prints, per post: the judge's verdict and
probability, whether its quotes are really in the post, and what the LLM alone would make of it
(the vector search and link rules are left out here, so this measures the judge only).
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

from moderation.check_azure import _explain_401, _post, preflight
from moderation.env import load_env

ROOT = Path(__file__).resolve().parents[1]
CASES = Path(__file__).with_name("judge_cases.json")
CFG = {"blockAt": 0.7, "reviewAt": 0.4}        # the Config values in n8n

# ~1,900 characters of an ordinary post, so the fee in "s_late_fee" sits past the 1,800 the judge reads
LONG_GENUINE_TEXT = "\n".join([
    "About Orbitstack",
    "Orbitstack Systems builds logistics software used by mid-size warehouses across India. Our platform "
    "tracks inventory, plans pick routes and prints shipping labels for more than 300 customers.",
    "What you will do",
    "• Build and test REST APIs in Python (FastAPI) and PostgreSQL for our inventory service.",
    "• Write unit and integration tests and keep our CI pipeline green.",
    "• Join daily stand-ups and weekly demos with the platform team.",
    "• Pair with a senior engineer on code reviews and design discussions.",
    "• Help profile slow database queries and fix them.",
    "What we are looking for",
    "• Good understanding of Python and basic SQL.",
    "• Familiarity with Git and the command line.",
    "• Curiosity about how real systems behave under load.",
    "• Final-year or pre-final-year students of any engineering branch.",
    "Selection process",
    "An online coding test, followed by a technical interview with two engineers and a short conversation "
    "with the engineering manager. We share feedback after every round.",
    "Benefits",
    "• Stipend of 15,000 per month, paid on the first working day of each month.",
    "• Internship certificate and a recommendation letter for strong performers.",
    "• Possibility of a full-time offer after graduation.",
    "• Flexible hours and one work-from-home day each week.",
    "Location and duration",
    "Pune office, six months, starting in January. Laptops are provided by the company for all interns.",
    "Our team",
    "You will work with a team of eight engineers who care about clean code, good tests and clear writing. "
    "We are a small company and interns ship real features to customers in their first month.",
    "How we work",
    "We plan in two-week sprints, write a short design note before large changes and keep our documentation "
    "next to the code. Every intern gets a buddy from the team for questions about the codebase, tools and "
    "the product, and a mid-internship review with written feedback on what went well and what to improve.",
])


def node_js(fn, files, args):
    node = shutil.which("node")
    if not node:
        sys.exit("Node.js is needed to build the judge request exactly like n8n does")
    out = subprocess.run([node, str(ROOT / "tests" / "js_runner.js"), files, fn],
                         input=json.dumps(args), capture_output=True, text=True, timeout=60)
    if out.returncode:
        sys.exit(out.stderr)
    return json.loads(out.stdout)


def load_cases(only=None):
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    for c in cases:
        c["description"] = c["description"].replace("LONG_GENUINE_TEXT", LONG_GENUINE_TEXT)
        c.setdefault("source_platform", "test")
    if only:
        cases = [c for c in cases if c["id"] in only]
    random.Random(7).shuffle(cases)     # scams and genuine posts mixed in every call, like real batches
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated case ids")
    a = ap.parse_args()
    load_env()
    if not preflight():
        sys.exit(1)
    url = os.environ.get("AZURE_OPENAI_JUDGE_URL", "").strip()
    key = (os.environ.get("AZURE_OPENAI_JUDGE_KEY") or os.environ.get("AZURE_OPENAI_KEY", "")).strip()

    cases = load_cases(set(filter(None, a.only.split(","))))
    items = [{"id": c["id"], "listing": c, "stage1": {"categories": [], "vector_risk": 0.0}, "signals": [],
              "signal_risk": 0.0} for c in cases]
    batches = node_js("packJudge", "judge_prompt.js", [items, "azure"])
    answers, tokens = [], 0
    for i, b in enumerate(batches):
        if i:
            time.sleep(8)     # gpt-4o deployment: 50k tokens/min
        t = time.time()
        r = _post(url, b["judgeRequest"], key, "Judge")
        if r is None:
            sys.exit(1)
        if r.status_code != 200:
            print(f"❌ Judge HTTP {r.status_code}: {r.text[:300]}")
            if r.status_code == 401:
                _explain_401("Judge")
            sys.exit(1)
        tokens += r.json().get("usage", {}).get("total_tokens", 0)
        print(f"call {i + 1}/{len(batches)}: {len(b['posts'])} posts in {time.time() - t:.1f}s")
        answers.append(r.json())
    verdicts = [x["verdict"] for x in node_js("fuseBatches", "_verdict_lib.js,fuse.js", [batches, answers, CFG])]
    by_id = {c["id"]: c for c in cases}

    raw = {}
    for ans in answers:
        for res in json.loads(ans["choices"][0]["message"]["content"]).get("results", []):
            raw[str(res["id"])] = res

    print(f"\n{'post':<22} {'truth':<8} {'judge says':<11} {'p':>5}  {'quotes ok':<9} LLM alone   trick")
    caught = missed = false_alarm = clean = 0
    summaries = []
    for v in verdicts:
        c, res = by_id[v["id"]], raw.get(v["id"], {})
        p = res.get("scam_probability", "-")
        ok_q, bad_q = v["parts"]["verified_quotes"], v["parts"]["rejected_quotes"]
        flagged = v["status"] in ("review", "blocked") or res.get("verdict") in ("suspicious", "scam")
        if c["label"] == "scam":
            caught += flagged
            missed += not flagged
        else:
            false_alarm += flagged
            clean += not flagged
        mark = "✅" if flagged == (c["label"] == "scam") else "❌"
        summaries.append(res.get("summary", ""))
        print(f"{mark} {v['id']:<20} {c['label']:<8} {res.get('verdict', 'NO ANSWER'):<11} {p!s:>5}  "
              f"{ok_q} ok/{bad_q} bad  {v['status']:<10} {c['trick']}")
        for ev in res.get("evidence", [])[:2]:
            print(f"      quote: \"{ev['quote'][:100]}\"")
        print(f"      summary: {res.get('summary', '')[:150]}")

    n_scam, n_gen = caught + missed, false_alarm + clean
    print("\n================ RESULT ================")
    print(f"Scams caught (judge said suspicious/scam): {caught} of {n_scam}")
    print(f"Genuine posts wrongly flagged:            {false_alarm} of {n_gen}")
    print(f"Same summary sentence used more than once: {len(summaries) - len(set(summaries))}")
    print(f"Tokens used: {tokens}")
    print("'LLM alone' = the status this post would get if the vector search and link rules found nothing.")


if __name__ == "__main__":
    main()
