"""The scam check (moderation/pipeline). It replaced the n8n workflow on 26 Oct 2026; the answers
the n8n JavaScript gave on these inputs are kept in tests/fixtures/n8n_golden.json and the Python
code must still give them. Then the whole round with fake APIs."""
import json
import math
import random
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moderation.pipeline import fuse as F  # noqa: E402
from moderation.pipeline import judge as J  # noqa: E402
from moderation.pipeline import rules as R  # noqa: E402
from moderation.pipeline import vectors as V  # noqa: E402
from moderation.pipeline.runner import judge_posts  # noqa: E402

CFG = {"blockAt": 0.7, "reviewAt": 0.4, "hitFloor": "", "strongFloor": "", "margin": "", "judgeBatch": 5, "judgeParallel": 2}


# What the old n8n JavaScript returned for each comparison below, recorded on 27 Oct 2026 before the
# n8n/ folder was deleted (it gave the same answers as this Python code then). The Python pipeline
# must keep giving the same answers: a change to a threshold or a prompt shows up here.
GOLDEN = Path(__file__).parent / "fixtures" / "n8n_golden.json"
_golden = json.loads(GOLDEN.read_text(encoding="utf-8"))


def js(files, fn, *args):
    """The recorded n8n answer for this call (files and fn name the old JavaScript)."""
    import hashlib
    args = json.loads(json.dumps(args))
    key = hashlib.sha256(json.dumps([files, fn, args], sort_keys=True).encode()).hexdigest()[:24]
    assert key in _golden, f"no recorded n8n answer for {fn}: the test input changed"
    return _golden[key]


def same(a, b):
    """Equal after a JSON round trip, floats compared to 1e-9 (JS and Python print 0.1+0.2 alike,
    but a sum can differ in the last bit)."""
    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(a, b, abs_tol=1e-9)
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


LONG = ("About us. We build logistics software for warehouses across India and our platform tracks inventory. "
        "What you will do • Build REST APIs in Python • Write tests for every endpoint and keep the CI green • "
        "Join daily stand-ups. " + "This is a very long sentence that keeps going " * 12 + "and ends here. Ok then. "
        "Pay a one-time registration fee of Rs 999 to confirm your seat. Contact HR on WhatsApp 9876543210 or "
        "mail hr.desk@gmail.com, UPI hr.jobs@ybl - Apply Now")
LISTINGS = [
    {"id": "a1", "role_title": "AI Intern", "company_name": "Acme", "stipend": "15,000/month", "description": LONG,
     "apply_link": "https://bit.ly/x1", "source_platform": "Naukri", "trust_flags": "Employer is new; Few posts"},
    {"id": "a2", "role_title": "Web Intern", "company_name": "Beta", "stipend": "", "description": "Short post.",
     "apply_link": "https://www.unstop.com/p/1", "source_platform": "Unstop", "trust_flags": ""},
    {"id": "a4", "role_title": "Edge Intern", "company_name": "Delta", "stipend": "5000", "source_platform": "Apna",
     "apply_link": "https://forms.gle/abc", "trust_flags": "",
     # sentences of 4, 5, 44, 45 and 46 words: the edges of the chunking rules
     "description": " ".join(". ".join(" ".join(f"w{n}x{i}" for i in range(n)) for n in (4, 5, 44, 45, 46)).split()) + "."},
    {"id": "a3", "role_title": "Data Intern", "company_name": "Gamma", "stipend": "Unpaid", "description": "",
     "apply_link": "not a url", "source_platform": "Shine", "trust_flags": ""},
]
LINKS = [
    {"link_state": "ok", "final_url": "https://wa.me/919876543210", "final_domain": "wa.me",
     "chain": ["https://bit.ly/x1", "https://wa.me/919876543210"], "http_status": 200},
    {"link_state": "bad_certificate", "final_url": "https://unstop.com/p/1", "chain": []},
    {"final_url": "https://forms.gle/abc", "chain": ["https://forms.gle/abc"]},
    {},
]


def test_rules_match_n8n():
    for listing, link in zip(LISTINGS, LINKS):
        assert same(R.analyse(listing, link), js("signals.js", "analyse", listing, link, {})), listing["id"]
    sizes = [len(c.split()) for c in R.analyse(LISTINGS[2], {})["chunks"][1:]]
    assert sizes == [9, 44, 45, 35, 21]   # 4+5 carried together, 44 and 45 whole, 46 cut in windows


def _bank(dims=8, seed=3):
    rnd = random.Random(seed)
    unit = lambda v: [x / (math.sqrt(sum(y * y for y in v)) or 1) for x in v]  # noqa: E731
    items = []
    for i, (kind, cat, sev) in enumerate([("scam", "upfront_fee", "high"), ("scam", "task_scam", "medium"),
                                          ("scam", "off_platform_contact", "low"), ("genuine", "", ""), ("genuine", "", "")]):
        items.append({"kind": kind, "category": cat, "severity": sev, "label": f"label {i}", "text": f"phrase {i}",
                      "vector": unit([rnd.uniform(-1, 1) for _ in range(dims)])})
    return {"provider": "gemini", "model": "m", "dims": dims, "request_style": "config", "task_type": "SEMANTIC_SIMILARITY",
            "calibration": {"hit_floor": 0.55, "strong_floor": 0.8, "margin": 0.05}, "items": items}


def _answers(posts, batches, bank, seed=5, broken=()):
    """Embeddings near the bank's phrases (some near-copies), Gemini and Azure shapes, one broken call."""
    rnd = random.Random(seed)
    out = []
    for bi, b in enumerate(batches):
        vecs = []
        for _ in range(b["texts"]):
            base = rnd.choice(bank["items"])["vector"]
            noise = rnd.choice([0.0, 0.03, 0.08, 0.15, 0.25, 0.4, 1.0])
            vecs.append([x + rnd.uniform(-noise, noise) for x in base] + [0.0, 0.0])   # longer than dims on purpose
        if bi in broken:
            out.append({"error": {"code": 429, "message": "quota"}})
        elif bi % 2:
            out.append({"data": [{"embedding": v, "index": i} for i, v in reversed(list(enumerate(vecs)))]})
        else:
            out.append({"embeddings": [{"values": v} for v in vecs]})
    return out


def _posts(n=14):
    rnd = random.Random(1)
    posts = []
    for i in range(n):
        listing = dict(LISTINGS[i % len(LISTINGS)], id=f"p{i}")
        posts.append(R.analyse(listing, LINKS[i % len(LINKS)]))
        posts[-1]["chunks"] = posts[-1]["chunks"][: rnd.randint(1, 12)]
    return posts


def test_embedding_batches_and_vector_search_match_n8n():
    bank = _bank()
    posts = _posts(60)
    bank_js = dict(bank)
    batches = V.pack(posts, bank)
    js_batches = js("pack_embed.js", "packEmbeds", posts, bank_js)
    assert [b["members"] for b in batches] == [b["members"] for b in js_batches]
    assert [len(b["embedRequest"]["requests"]) for b in js_batches] == [len(b["chunks"]) for b in batches]
    answers = _answers(posts, batches, bank, broken={1})
    cfg = {"hitFloor": "", "strongFloor": "", "margin": ""}
    py = V.unpack(posts, batches, answers, bank, cfg)
    jsv = js("vector_search.js", "unpack", posts, js_batches, answers, bank, cfg)
    assert same(py, jsv)
    assert {i["gate"]["decision"] for i in py} >= {"judge"} and any(i["stage1"].get("error") for i in py)
    cats = [c for i in py for c in i["stage1"]["categories"]]
    assert any(c["strong"] for c in cats) and any(not c["strong"] for c in cats)   # both sides of each threshold
    near = [n["margin"] for i in py for n in i["stage1"]["nearest"]]
    assert min(near) < 0.1 < max(near)
    for f in (0.9, 1.1):   # moved thresholds must change the result, or the comparison proves nothing
        moved = {**bank, "calibration": {k: v * f for k, v in bank["calibration"].items()}}
        assert not same(V.unpack(posts, batches, answers, moved, cfg), py)


def test_judge_requests_match_n8n():
    bank = _bank()
    posts = _posts(7)
    batches = V.pack(posts, bank)
    items = V.unpack(posts, batches, _answers(posts, batches, bank), bank, CFG)
    for provider in ("azure", "gemini"):
        py = [b["judgeRequest"] for b in J.pack(items, provider)]
        assert same(py, [b["judgeRequest"] for b in js("judge_prompt.js", "packJudge", items, provider)]), provider


def _judge_answer(posts, mode):
    res = []
    for k, p in enumerate(posts):
        text = p["listing"].get("description") or ""
        if mode == "sure" and "registration fee" in text:
            res.append({"id": p["id"], "scam_probability": 0.97, "verdict": "scam", "categories": ["upfront_fee"],
                        "evidence": [{"quote": "Pay a one-time registration fee of Rs 999", "why": "fee"}], "genuine_signs": [], "summary": "fee"})
        elif k % 3 == 0:
            res.append({"id": p["id"], "scam_probability": 0.8, "verdict": "suspicious", "categories": [],
                        "evidence": [{"quote": "a sentence that is not in the post at all", "why": "made up"},
                                     {"quote": "We do not charge any fee", "why": "x"}], "genuine_signs": [], "summary": "unsure"})
        elif k % 3 == 1:
            continue                                            # the model skipped this post
        else:
            res.append({"id": p["id"], "scam_probability": 0.05, "verdict": "genuine", "categories": [],
                        "evidence": [], "genuine_signs": ["clear work"], "summary": "fine"})
    body = json.dumps({"results": res})
    return {"choices": [{"finish_reason": "stop", "message": {"content": body}}]} if mode != "gemini" else \
        {"candidates": [{"content": {"parts": [{"text": body}]}}]}


def test_verdicts_match_n8n():
    bank = _bank()
    posts = _posts(12)
    batches = V.pack(posts, bank)
    items = V.unpack(posts, batches, _answers(posts, batches, bank, broken={0}), bank, CFG)
    jb = J.pack(items, "azure")
    answers = [_judge_answer(jb[0]["posts"], "sure"), _judge_answer(jb[1]["posts"], "gemini"), {"error": {"code": 500}}]
    assert same(F.fuse_batches(jb, answers, CFG), js("_verdict_lib.js,fuse.js", "fuseBatches", jb, answers, CFG))
    statuses = {v["verdict"]["status"] for v in F.fuse_batches(jb, answers, CFG)}
    assert "blocked" in statuses and "retry" in statuses       # sure-and-proven, and both AIs down
    for it in items[:4]:
        it = {**it, "gate": {"decision": "block", "why": "test"}}
        assert same(F.stage1_verdict(it, CFG), js("_verdict_lib.js,stage1_verdict.js", "stage1Verdict", it, CFG))
    for link in ({"link_state": "closed", "closed_phrase": "applications closed"}, {"link_state": "dead", "http_status": 404}):
        assert same(F.expired_verdict(LISTINGS[0], link), js("expired_verdict.js", "expiredVerdict", LISTINGS[0], link))


def test_a_whole_round_with_fake_apis():
    bank = _bank()
    rows = [dict(LISTINGS[0], id="r1"), dict(LISTINGS[1], id="r2", description="Build React pages. We never charge any fee."),
            dict(LISTINGS[1], id="r3", apply_link="https://example.com/closed")]
    links = {rows[0]["apply_link"]: LINKS[0], rows[1]["apply_link"]: {"link_state": "ok"},
             rows[2]["apply_link"]: {"link_state": "closed", "closed_phrase": "this job has expired"}}
    calls = []

    def fake_call(req):
        calls.append(req)
        ids = [line.split(" ", 1)[1] for line in req["messages"][-1]["content"].splitlines() if line.startswith("POST ")]
        res = [{"id": i, "scam_probability": 0.97 if i == "r1" else 0.03, "verdict": "scam" if i == "r1" else "genuine",
                "categories": [], "summary": "",
                "evidence": [{"quote": "Pay a one-time registration fee of Rs 999", "why": "fee"}] if i == "r1" else []}
               for i in ids]
        return {"choices": [{"message": {"content": json.dumps({"results": res})}}]}

    embed = lambda texts: {"embeddings": [{"values": bank["items"][3]["vector"]} for _ in texts]}  # noqa: E731 - all honest
    out = {v["id"]: v for v in judge_posts(rows, CFG, bank, resolve=links.get, embed=embed, call=fake_call)}
    assert out["r1"]["status"] == "blocked" and out["r2"]["status"] == "approved" and out["r3"]["status"] == "expired"
    assert len(calls) == 1                                      # r3's page is closed: never sent to the AI


def test_every_threshold_edge_matches_n8n():
    """One-chunk posts swept across angles between a scam phrase and an honest one, so every
    threshold (hit, near-copy, margin, 2x margin) is crossed somewhere."""
    bank = {"provider": "gemini", "model": "m", "dims": 2, "request_style": "plain", "task_type": "X",
            "calibration": {"hit_floor": 0.6, "strong_floor": 0.85, "margin": 0.05},
            "items": [{"kind": "scam", "category": "upfront_fee", "severity": "high", "label": "fee", "text": "pay fee", "vector": [1.0, 0.0]},
                      {"kind": "genuine", "category": "", "severity": "", "label": "", "text": "no fee",
                       "vector": [math.cos(0.9), math.sin(0.9)]}]}
    posts = [{"id": f"s{i}", "chunks": ["c"], "signals": [], "signal_risk": 0, "listing": {}} for i in range(600)]
    batches = [{"members": [{"idx": i, "start": 0, "n": 1}], "texts": 1, "chunks": ["c"]} for i in range(600)]
    answers = [{"embeddings": [{"values": [math.cos(-0.6 + i * 0.002), math.sin(-0.6 + i * 0.002)]}]} for i in range(600)]
    cfg = {"hitFloor": "", "strongFloor": "", "margin": ""}
    py = V.unpack(posts, batches, answers, bank, cfg)
    assert same(py, js("vector_search.js", "unpack", posts, batches, answers, bank, cfg))
    kinds = {(bool(p["stage1"]["categories"]), bool(p["stage1"]["categories"] and p["stage1"]["categories"][0]["strong"])) for p in py}
    assert kinds == {(False, False), (True, False), (True, True)}


def test_long_posts_are_cut_like_n8n():
    risky = ("Pay the registration fee " + "x" * 900)[:899] + "."   # exactly the 900 characters allowed
    for extra in (risky, risky + "y", "Kit charge applies.\n" + risky):
        item = {"id": "L", "stage1": {"categories": []}, "signals": [], "listing": {
            "role_title": "T", "company_name": "C", "stipend": "", "source_platform": "S", "description": "z" * 1800 + "\n" + extra}}
        assert J.post_block(item) == js("judge_prompt.js", "postBlock", item)
