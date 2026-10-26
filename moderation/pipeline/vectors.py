"""Stage 1, port of n8n/code/pack_embed.js + vector_search.js.

Each chunk of a post is compared with every phrase in the bank (moderation/scam_patterns.json,
embedded by build_index into pattern_index.json). A chunk is a hit only when it is
  (a) about as close to a scam phrase as two phrasings of the same trick are, and
  (b) clearly closer to that scam phrase than to the nearest HONEST phrase
- (b) keeps "There is no registration fee" from matching "Pay the registration fee".
"""
import json
import math
import os
import time
from functools import lru_cache
from pathlib import Path

import requests

from moderation.env import load_env

INDEX = Path(__file__).resolve().parents[1] / "pattern_index.json"
MAX_TEXTS = 90           # texts per embedding call (chunks of several posts share one call)
SEVERITY_WEIGHT = {"high": 0.9, "medium": 0.6, "low": 0.3}


@lru_cache(maxsize=1)
def _bank_cached(mtime: float) -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def load_bank() -> dict | None:
    if not INDEX.exists():
        return None
    return _bank_cached(INDEX.stat().st_mtime)


def _unit(values, dims):
    v = list(values[:dims])
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _request_item(text, bank):
    item = {"model": f"models/{bank['model']}", "content": {"parts": [{"text": text}]}}
    if bank.get("request_style") == "config":
        item["embedContentConfig"] = {"taskType": bank["task_type"], "outputDimensionality": bank["dims"]}
    elif bank.get("request_style") == "legacy":
        item["taskType"] = bank["task_type"]
        item["outputDimensionality"] = bank["dims"]
    return item


def pack(posts: list, bank: dict) -> list:
    """Chunks of many posts in shared calls; each batch remembers whose slice is whose."""
    batches, cur = [], None
    for idx, p in enumerate(posts):
        if cur is None or cur["texts"] + len(p["chunks"]) > MAX_TEXTS:
            cur = {"members": [], "texts": 0, "chunks": []}
            batches.append(cur)
        cur["members"].append({"idx": idx, "start": cur["texts"], "n": len(p["chunks"])})
        cur["chunks"] += p["chunks"]
        cur["texts"] += len(p["chunks"])
    return batches


def embed_call(texts: list, bank: dict, timeout: float = 20.0) -> dict:
    """One call; returns the API's answer, or {"error": ...} (the n8n node never failed the run)."""
    load_env()
    try:
        if bank.get("provider") == "azure":
            key = (os.environ.get("AZURE_OPENAI_KEY") or "").strip()
            body, headers = {"input": texts, "dimensions": bank["dims"]}, {"api-key": key}
        else:
            key = (os.environ.get("GEMINI_API_KEY") or "").strip()
            body, headers = {"requests": [_request_item(t, bank) for t in texts]}, {"x-goog-api-key": key}
        for attempt in range(3):
            r = requests.post(bank["embed_url"], json=body, headers=headers, timeout=timeout)
            if r.status_code == 429 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            break
        if r.status_code != 200:
            return {"error": {"code": r.status_code, "message": r.text[:200]}}
        return r.json()
    except requests.RequestException as e:
        return {"error": {"message": type(e).__name__}}


def search(chunks: list, embeddings: list, bank: dict, cfg: dict | None = None) -> dict:
    cal = {**bank["calibration"], **{k: v for k, v in (cfg or {}).items() if v not in ("", None)}}
    hit_floor, strong_floor, margin = float(cal["hit_floor"]), float(cal["strong_floor"]), float(cal["margin"])
    scam = [it for it in bank["items"] if it["kind"] == "scam"]
    honest = [it for it in bank["items"] if it["kind"] == "genuine"]

    per_chunk = []
    for i, text in enumerate(chunks):
        v = _unit(embeddings[i]["values"], bank["dims"])
        best = max(((_dot(v, it["vector"]), it) for it in scam), key=lambda x: x[0])
        best_h = max(((_dot(v, it["vector"]), it) for it in honest), key=lambda x: x[0], default=None)
        m = best[0] - (best_h[0] if best_h else 0)
        per_chunk.append({"chunk": text, "sim": best[0], "margin": m, "pattern": best[1],
                          "hit": best[0] >= hit_floor and m >= margin,
                          "strong": best[0] >= strong_floor and m >= 2 * margin})

    by_cat = {}
    for c in per_chunk:
        if c["hit"]:
            cat = c["pattern"]["category"]
            if cat not in by_cat or c["sim"] > by_cat[cat]["sim"]:
                by_cat[cat] = c
    categories = sorted(({
        "category": c["pattern"]["category"],
        "label": c["pattern"]["label"],
        "severity": c["pattern"]["severity"],
        "strong": c["strong"],
        "strength": round(SEVERITY_WEIGHT.get(c["pattern"]["severity"], 0.3) * (1 if c["strong"] else 0.6), 3),
        "similarity": round(c["sim"], 3),
        "margin": round(c["margin"], 3),
        "chunk": c["chunk"],
        "matched_pattern": c["pattern"]["text"],
    } for c in by_cat.values()), key=lambda c: -c["strength"])

    p = 1.0
    for c in categories:
        p *= 1 - c["strength"]
    nearest = [{"chunk": c["chunk"], "pattern": c["pattern"]["text"], "similarity": round(c["sim"], 3),
                "margin": round(c["margin"], 3)} for c in sorted(per_chunk, key=lambda c: -c["sim"])[:3]]
    return {"thresholds": {"hit_floor": hit_floor, "strong_floor": strong_floor, "margin": margin},
            "chunks_checked": len(chunks), "categories": categories, "vector_risk": round(1 - p, 3),
            "nearest": nearest}


def gate(stage1: dict, signals: list) -> dict:
    """Block without asking the AI only on strong, high-severity evidence."""
    strong_high = [c for c in stage1["categories"] if c["severity"] == "high" and c["strong"]]
    upi = next((s for s in signals if s["code"] == "upi_id"), None)
    fee = next((c for c in stage1["categories"] if c["category"] == "upfront_fee"), None)
    if strong_high:
        return {"decision": "block", "why": "Near-copy of a known scam: " + ", ".join(c["label"] for c in strong_high)}
    if upi and fee:
        return {"decision": "block", "why": "Payment wording together with a UPI payment ID"}
    return {"decision": "judge", "why": "No conclusive match; sent to the LLM judge"}


def unpack(posts: list, batches: list, answers: list, bank: dict, cfg: dict) -> list:
    out = []
    for bi, b in enumerate(batches):
        ans = answers[bi] if bi < len(answers) and answers[bi] else {}
        if "embeddings" in ans:
            embs = ans["embeddings"]
        else:   # Azure: {data: [{embedding, index}]}
            embs = [{"values": d["embedding"]} for d in sorted(ans.get("data") or [], key=lambda d: d["index"])]
        for m in b["members"]:
            post = posts[m["idx"]]
            mine = embs[m["start"]:m["start"] + m["n"]]
            if len(mine) != m["n"]:
                # embedding failed: skip the vector stage, the AI judge still runs and the reason says so
                err = json.dumps(ans["error"], separators=(",", ":"))[:200] if ans.get("error") else "no vectors"
                stage1 = {"error": f"Embedding failed ({err})", "categories": [], "vector_risk": 0,
                          "nearest": [], "chunks_checked": 0}
                out.append({**post, "stage1": stage1, "gate": {"decision": "judge", "why": stage1["error"]}})
                continue
            stage1 = search(post["chunks"], mine, bank,
                            {"hit_floor": cfg.get("hitFloor"), "strong_floor": cfg.get("strongFloor"), "margin": cfg.get("margin")})
            out.append({**post, "stage1": stage1, "gate": gate(stage1, post["signals"])})
    return out
