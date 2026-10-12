"""The scam-moderation pipeline: pattern index, moderation API, link check and the n8n Code-node logic."""
import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import mock_gemini  # noqa: E402
import output_handler as oh  # noqa: E402
from moderation import build_index  # noqa: E402
from moderation.link_check import resolve  # noqa: E402

NODE = shutil.which("node")


@pytest.fixture(scope="module")
def gemini():
    srv = mock_gemini.serve(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture(scope="module")
def index(gemini, tmp_path_factory, monkeypatch_module=None):
    out = tmp_path_factory.mktemp("idx") / "pattern_index.json"
    old = build_index.INDEX
    build_index.INDEX = out
    env = {"GEMINI_API_KEY": "test-key", "GEMINI_API_BASE": gemini}
    saved = {k: build_index.os.environ.get(k) for k in env}
    build_index.os.environ.update(env)
    try:
        build_index.main()
    finally:
        build_index.INDEX = old
        for k, v in saved.items():
            if v is None:
                build_index.os.environ.pop(k, None)
            else:
                build_index.os.environ[k] = v
    return json.loads(out.read_text(encoding="utf-8"))


def test_index_built_with_calibration(index):
    assert index["request_style"] == "config" and index["dims"] == 768
    assert len(index["items"][0]["vector"]) == 768
    cats = {it["category"] for it in index["items"] if it["kind"] == "scam"}
    assert {"upfront_fee", "task_scam", "data_harvest", "training_sale"} <= cats
    cal = index["calibration"]
    assert cal["strong_floor"] >= cal["hit_floor"] and cal["margin"] >= 0.02


# ---------- moderation storage + API ----------

def _row(id_, title, desc="Build ML models with our team.", **kw):
    return {"id": id_, "company_name": "Acme", "role_title": title, "stipend": "15,000/month", "stipend_numeric": 15000,
            "apply_link": f"https://example.com/{id_}", "source_platform": "Naukri", "date_scraped": "2026-10-12",
            "description": desc, **kw}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "internships_log.json")
    return tmp_path


def test_verdict_survives_refresh_but_not_a_changed_post(store):
    oh.sync_listings([_row("a", "AI Intern"), _row("b", "ML Intern")], [])
    assert [p["id"] for p in oh.pending_moderation()] == ["a", "b"] or len(oh.pending_moderation()) == 2
    assert oh.save_verdict("a", "approved", 0.08, ["LLM: genuine"]) is True
    assert oh.save_verdict("b", "blocked", 0.91, ["fee"]) is True
    assert oh.pending_moderation() == []

    # same posts again (e.g. next scrape): verdicts stay
    oh.sync_listings([_row("a", "AI Intern"), _row("b", "ML Intern")], [])
    assert oh.pending_moderation() == []
    # post "b" edited by the employer: judged again
    oh.sync_listings([_row("a", "AI Intern"), _row("b", "ML Intern", "Pay a refundable deposit to join.")], [])
    assert [p["id"] for p in oh.pending_moderation()] == ["b"]

    with pytest.raises(ValueError):
        oh.save_verdict("a", "maybe", 0.5, [])
    with pytest.raises(ValueError):
        oh.save_verdict("a", "approved", 1.5, [])
    assert oh.save_verdict("zzz", "approved", 0.1, []) is False


def test_flask_moderation_api(store, monkeypatch, index, tmp_path):
    import app as app_module
    idx = tmp_path / "pattern_index.json"
    idx.write_text(json.dumps(index), encoding="utf-8")
    monkeypatch.setattr(app_module, "PATTERN_INDEX", idx)
    oh.sync_listings([_row("a", "AI Intern")], [])
    c = app_module.app.test_client()
    pending = c.get("/api/moderation/pending?limit=5").get_json()
    assert [p["id"] for p in pending] == ["a"] and pending[0]["description"]
    assert c.get("/api/moderation/patterns").get_json()["model"] == "gemini-embedding-001"
    r = c.post("/api/moderation/verdict", json={"id": "a", "status": "review", "scam_risk": 0.5, "reasons": ["x", "y"]})
    assert r.status_code == 200 and r.get_json()["saved"] is True
    row = oh._read_rows()[0]
    assert row["moderation_status"] == "review" and row["scam_risk"] == "0.50" and row["moderation_reasons"] == "x | y"
    assert c.post("/api/moderation/verdict", json={"id": "a", "status": "nope", "scam_risk": 0.5}).status_code == 400


# ---------- link check ----------

class _Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/short":
            self.send_response(302)
            self.send_header("Location", "/job")
            self.end_headers()
            return
        pages = {"/job": (200, "<html><body><h1>ML Intern</h1><p>Apply now</p></body></html>"),
                 "/old": (200, "<html><body><div>This internship is no longer accepting applications</div></body></html>")}
        code, html = pages.get(self.path, (404, "not found"))
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())


@pytest.fixture(scope="module")
def site():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_link_check(site):
    r = resolve(site + "/short")
    assert r["link_state"] == "ok" and r["final_url"].endswith("/job") and len(r["chain"]) == 2
    assert resolve(site + "/gone")["link_state"] == "dead"
    closed = resolve(site + "/old")
    assert closed["link_state"] == "closed" and "no longer accepting" in closed["closed_phrase"]
    assert resolve("not a url")["link_state"] == "invalid"


# ---------- n8n Code-node logic (run with node) ----------

def js(files, fn, *args):
    out = subprocess.run(["node", str(Path(__file__).parent / "js_runner.js"), files, fn],
                         input=json.dumps(args), capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

SCAM_TEXT = ("Work on AI projects. Selected candidates must pay a refundable security deposit of Rs 2000 "
             "to confirm the internship. Contact HR on WhatsApp 9876543210. UPI: hr.jobs@ybl")
CLEAN_TEXT = ("You will train and evaluate machine learning models with our engineering team. "
              "We do not charge any fee from candidates at any stage of hiring. Selection is through a technical interview.")


def _listing(id_, text, link="https://www.naukri.com/job-listings-x"):
    return {"id": id_, "role_title": "AI Intern", "company_name": "Acme", "stipend": "15,000/month",
            "description": text, "apply_link": link, "source_platform": "Naukri", "trust_flags": ""}


@needs_node
def test_signals_and_chunks(index):
    bank = {k: index[k] for k in ("model", "dims", "request_style", "task_type")}
    out = js("signals.js", "analyse", _listing("s", SCAM_TEXT, "https://bit.ly/abc"),
             {"link_state": "ok", "chain": ["https://bit.ly/abc", "https://forms.gle/xyz"], "final_url": "https://forms.gle/xyz",
              "final_domain": "forms.gle"}, bank)
    codes = {s["code"] for s in out["signals"]}
    assert {"short_link", "form_link", "upi_id", "whatsapp", "phone", "redirect"} <= codes
    assert 0.75 < out["signal_risk"] <= 0.95   # 1 - product of (1 - weight)
    assert out["chunks"][0].startswith("AI Intern at Acme") and len(out["chunks"]) >= 3
    assert out["listing"]["id"] == "s"

    clean = js("signals.js", "analyse", _listing("c", CLEAN_TEXT), {"link_state": "portal_blocks_bots"}, bank)
    assert clean["signals"] == [] and clean["signal_risk"] == 0


@needs_node
def test_vector_search_contrast_and_gate(index):
    def run(text):
        chunks = js("signals.js", "chunkText", _listing("x", text))
        embs = [{"values": mock_gemini.embed(c)} for c in chunks]
        stage1 = js("vector_search.js", "search", chunks, embs, index, {})
        return stage1, js("vector_search.js", "gate", stage1, [])

    scam1, gate1 = run("Selected candidates must pay a security deposit which will be returned after the internship.")
    assert scam1["categories"] and scam1["categories"][0]["category"] == "upfront_fee"
    assert gate1["decision"] == "block"
    clean1, gate2 = run(CLEAN_TEXT)
    assert clean1["categories"] == [] and gate2["decision"] == "judge"
    assert clean1["nearest"]   # reviewers still see how close it came


@needs_node
def test_fuse_checks_quotes_and_never_lets_llm_block_alone():
    cfg = {"blockAt": 0.7, "reviewAt": 0.4}
    listing = _listing("f", "Great team. Interns pay a refundable deposit of Rs 1500 to join.")
    item = {"id": "f", "stage1": {"vector_risk": 0.0, "categories": []}, "signals": [], "signal_risk": 0.0}

    def llm(p, quotes):
        body = {"scam_probability": p, "verdict": "scam" if p > 0.5 else "genuine", "categories": ["upfront_fee"],
                "evidence": [{"quote": q, "why": "fee"} for q in quotes], "summary": "s"}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]}

    real = js("_verdict_lib.js,fuse.js", "fuse", listing, item, llm(0.95, ["Interns pay a refundable deposit of Rs 1500"]), cfg)
    assert real["parts"]["verified_quotes"] == 1 and real["status"] == "review"          # LLM alone: review, not blocked
    fake = js("_verdict_lib.js,fuse.js", "fuse", listing, item, llm(0.95, ["pay the processing fee before joining"]), cfg)
    assert fake["parts"]["rejected_quotes"] == 1 and fake["parts"]["llm_adjusted"] < 0.65   # made-up quote discounted
    assert any("not in the post" in r for r in fake["reasons"])

    item_hit = {**item, "stage1": {"vector_risk": 0.8, "categories": []}, "signal_risk": 0.3}
    both = js("_verdict_lib.js,fuse.js", "fuse", listing, item_hit, llm(0.95, ["Interns pay a refundable deposit of Rs 1500"]), cfg)
    assert both["status"] == "blocked"
    calm = js("_verdict_lib.js,fuse.js", "fuse", listing, item_hit, llm(0.05, []), cfg)
    assert calm["status"] == "review" and any("disagree" in r for r in calm["reasons"])  # disagreement goes to a person
    down = js("_verdict_lib.js,fuse.js", "fuse", listing, item_hit, {"error": {"code": 429}}, cfg)
    assert down["decided_by"] == "vector_search" and down["status"] in ("review", "blocked")


@needs_node
def test_fuse_rejects_quotes_that_say_no_fee():
    cfg = {"blockAt": 0.7, "reviewAt": 0.4}
    listing = _listing("n", CLEAN_TEXT)
    item = {"id": "n", "stage1": {"vector_risk": 0.0, "categories": []}, "signals": [], "signal_risk": 0.0}
    body = {"scam_probability": 0.9, "verdict": "scam", "categories": ["upfront_fee"], "summary": "fee",
            "evidence": [{"quote": "We do not charge any fee from candidates at any stage of hiring", "why": "fee"}]}
    v = js("_verdict_lib.js,fuse.js", "fuse", listing, item, {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]}, cfg)
    assert v["parts"]["verified_quotes"] == 0 and any("says the opposite" in r for r in v["reasons"])
    assert v["scam_risk"] < 0.4 and v["status"] == "review"   # discounted, but the disagreement still goes to a person


def test_description_arriving_later_triggers_new_moderation(store):
    oh.sync_listings([_row("old", "AI Intern", desc="")], [])
    oh.save_verdict("old", "approved", 0.1, ["title only"])
    oh.sync_listings([_row("old", "AI Intern", desc="Pay a registration fee to join.")], [])
    assert [p["id"] for p in oh.pending_moderation()] == ["old"]


@needs_node
def test_mini_batches_map_answers_back_to_the_right_posts(index):
    bank = {k: index[k] for k in ("model", "dims", "request_style", "task_type")}
    posts = [{"id": f"p{i}", "chunks": [f"chunk {i}.{j}" for j in range(n)]} for i, n in enumerate([30, 40, 30, 5])]
    batches = js("pack_embed.js", "packEmbeds", posts, bank)
    assert [len(b["embedRequest"]["requests"]) for b in batches] == [70, 35]        # max 90 texts per call
    assert batches[1]["members"] == [{"idx": 2, "start": 0, "n": 30}, {"idx": 3, "start": 30, "n": 5}]
    assert batches[0]["embedRequest"]["requests"][0]["embedContentConfig"]["outputDimensionality"] == 768

    # unpack: second batch failed -> its posts still go on, marked, to the LLM judge
    full = [{**p, "signals": [], "signal_risk": 0, "listing": {"id": p["id"]}} for p in posts]
    answers = [{"embeddings": [{"values": mock_gemini.embed(c)} for b in [batches[0]] for r in b["embedRequest"]["requests"]
                               for c in [r["content"]["parts"][0]["text"]]]}, {"error": {"code": 429}}]
    out = js("vector_search.js", "unpack", full, batches, answers, index, {})
    assert [o["id"] for o in out] == ["p0", "p1", "p2", "p3"]
    assert out[0]["stage1"]["chunks_checked"] == 30 and "Embedding failed" in out[3]["stage1"]["error"]


@needs_node
def test_judge_batches_split_per_post():
    items = [{"id": f"x{i}", "stage1": {"categories": []}, "signals": [], "signal_risk": 0,
              "listing": _listing(f"x{i}", SCAM_TEXT if i == 3 else CLEAN_TEXT)} for i in range(10)]
    packed = js("judge_prompt.js", "packJudge", items)
    assert [len(b["posts"]) for b in packed] == [8, 2]
    prompt = packed[0]["judgeRequest"]["contents"][-1]["parts"][0]["text"]
    assert prompt.count("POST x") == 8 and "results" in json.dumps(packed[0]["judgeRequest"]["generationConfig"])

    def answer(batch, drop=None):
        res = [{"id": p["id"], **mock_gemini.judge("Text: " + p["listing"]["description"])} for p in batch["posts"] if p["id"] != drop]
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"results": res})}]}}]}

    out = js("_verdict_lib.js,fuse.js", "fuseBatches", packed, [answer(packed[0], drop="x5"), {"error": {"code": 500}}],
             {"blockAt": 0.7, "reviewAt": 0.4})
    v = {o["verdict"]["id"]: o["verdict"] for o in out}
    assert len(v) == 10
    assert v["x3"]["parts"]["verified_quotes"] == 1 and v["x0"]["status"] == "approved"
    assert v["x5"]["decided_by"] == "vector_search" and "no result for this post" in v["x5"]["reasons"][0]
    assert v["x9"]["decided_by"] == "vector_search"                       # whole second call failed


def test_claims_split_work_between_overlapping_runs(store):
    oh.sync_listings([_row(f"c{i}", "AI Intern") for i in range(5)], [])
    first = oh.pending_moderation(limit=3, claim=True)
    second = oh.pending_moderation(limit=3, claim=True)
    assert len(first) == 3 and len(second) == 2 and not {p["id"] for p in first} & {p["id"] for p in second}
    assert oh.pending_moderation(limit=10, claim=True) == []
    assert oh.moderation_counts()["checking"] == 5
    # a claim nobody finished comes back after the timeout
    rows = oh._read_rows()
    rows[0]["moderated_at"] = "2026-01-01 00:00:00"
    oh._write_rows(rows)
    assert len(oh.pending_moderation(limit=10)) == 1
    oh.save_verdict(first[0]["id"], "approved", 0.1, [])
    assert oh.moderation_counts()["approved"] == 1


def test_azure_index_and_unpack(gemini, tmp_path, monkeypatch):
    out = tmp_path / "pattern_index.json"
    monkeypatch.setattr(build_index, "INDEX", out)
    for k, v in {"EMBED_PROVIDER": "azure", "AZURE_OPENAI_KEY": "test-key", "AZURE_OPENAI_EMBED_DEPLOYMENT": "emb",
                 "AZURE_OPENAI_ENDPOINT": gemini + "/openai/deployments/emb/embeddings?api-version=2023-05-15"}.items():
        monkeypatch.setenv(k, v)
    build_index.main()
    idx = json.loads(out.read_text(encoding="utf-8"))
    assert idx["provider"] == "azure" and idx["embed_url"] == gemini + "/openai/deployments/emb/embeddings?api-version=2024-10-21"
    assert "test-key" not in out.read_text(encoding="utf-8")            # the key never goes into the index
    fee = [it for it in idx["items"] if it["id"] == "upfront_fee-3"][0]
    assert abs(sum(a * b for a, b in zip(fee["vector"], mock_gemini.embed(fee["text"]))) - 1) < 1e-3   # order kept
    if NODE:
        posts = [{"id": "a", "chunks": ["Selected candidates must pay a security deposit which will be returned after the internship."],
                  "signals": [], "signal_risk": 0, "listing": {"id": "a"}}]
        batches = js("pack_embed.js", "packEmbeds", posts, idx)
        assert batches[0]["embedRequest"] == {"input": posts[0]["chunks"], "dimensions": 768}
        ans = [{"data": [{"index": 0, "embedding": mock_gemini.embed(posts[0]["chunks"][0])}]}]
        res = js("vector_search.js", "unpack", posts, batches, ans, idx, {})
        assert res[0]["stage1"]["categories"][0]["category"] == "upfront_fee"


@needs_node
def test_azure_gpt4o_judge_request_and_answer():
    items = [{"id": f"z{i}", "stage1": {"categories": []}, "signals": [], "signal_risk": 0,
              "listing": _listing(f"z{i}", SCAM_TEXT if i == 1 else CLEAN_TEXT)} for i in range(3)]
    packed = js("judge_prompt.js", "packJudge", items, "azure")
    req = packed[0]["judgeRequest"]
    assert [m["role"] for m in req["messages"]] == ["system", "user", "assistant", "user"]   # one-shot example
    schema = req["response_format"]["json_schema"]["schema"]["properties"]["results"]["items"]
    assert schema["additionalProperties"] is False and set(schema["required"]) == set(schema["properties"])
    body = {"results": [{"id": p["id"], **mock_gemini.judge("Text: " + p["listing"]["description"])} for p in packed[0]["posts"]]}
    ans = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(body)}}]}
    v = {o["verdict"]["id"]: o["verdict"] for o in js("_verdict_lib.js,fuse.js", "fuseBatches", packed, [ans], {"blockAt": 0.7, "reviewAt": 0.4})}
    assert v["z1"]["parts"]["verified_quotes"] == 1 and v["z0"]["status"] == "approved"
    filt = {"choices": [{"finish_reason": "content_filter", "message": {"content": None}}]}
    w = js("_verdict_lib.js,fuse.js", "fuseBatches", packed, [filt], {"blockAt": 0.7, "reviewAt": 0.4})
    assert all("content filter" in o["verdict"]["reasons"][0] for o in w)


@needs_node
def test_both_ai_checks_down_means_retry_not_approved(store):
    listing = _listing("r", "Pay a refundable deposit to join.")
    item = {"id": "r", "stage1": {"vector_risk": 0, "categories": [], "error": "Embedding failed (429)"}, "signals": [], "signal_risk": 0.1}
    v = js("_verdict_lib.js,fuse.js", "fuse", listing, item, {"error": {"code": 429}}, {"blockAt": 0.7, "reviewAt": 0.4})
    assert v["status"] == "retry"
    oh.sync_listings([_row("r", "AI Intern")], [])
    oh.pending_moderation(claim=True)
    assert oh.save_verdict("r", "retry", 0, ["x"]) is True
    assert [p["id"] for p in oh.pending_moderation()] == ["r"]
