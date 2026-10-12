"""
Builds moderation/pattern_index.json: every phrase in scam_patterns.json turned into an
embedding vector, plus thresholds measured on the bank itself.

    python -m moderation.build_index

Needs GEMINI_API_KEY in .env (or the environment). Run it again whenever you add phrases.
The n8n workflow reads the result from http://localhost:5000/api/moderation/patterns and
embeds each listing with the SAME model and settings, so the two can be compared.
"""
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from moderation.env import load_env

HERE = Path(__file__).parent
BANK = HERE / "scam_patterns.json"
INDEX = HERE / "pattern_index.json"
DIMS = 768            # gemini-embedding-001 is trained so the first N values work on their own (truncation)
BATCH = 90
# Request shapes the Gemini API has accepted for embedding options, newest first.
# The one that works is saved in the index so n8n sends the same thing.
REQUEST_STYLES = ["config", "legacy", "plain"]


def settings():
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit("GEMINI_API_KEY is not set. Put GEMINI_API_KEY=... in the .env file next to app.py.")
    return {
        "key": key,
        "base": os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com").rstrip("/"),
        "model": os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001"),
    }


def request_item(model: str, text: str, style: str) -> dict:
    item = {"model": f"models/{model}", "content": {"parts": [{"text": text}]}}
    if style == "config":
        item["embedContentConfig"] = {"taskType": "SEMANTIC_SIMILARITY", "outputDimensionality": DIMS}
    elif style == "legacy":
        item["taskType"] = "SEMANTIC_SIMILARITY"
        item["outputDimensionality"] = DIMS
    return item


def normalise(values: list) -> list:
    v = values[:DIMS]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed(texts: list, cfg: dict, style: str) -> list:
    url = f"{cfg['base']}/v1beta/models/{cfg['model']}:batchEmbedContents"
    out = []
    for i in range(0, len(texts), BATCH):
        body = {"requests": [request_item(cfg["model"], t, style) for t in texts[i:i + BATCH]]}
        for attempt in range(4):
            r = requests.post(url, json=body, headers={"x-goog-api-key": cfg["key"]}, timeout=60)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            break
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        out += [normalise(e["values"]) for e in r.json()["embeddings"]]
    return out


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def calibrate(items: list) -> dict:
    """Thresholds from the bank itself, so they fit whatever embedding model is used."""
    scam = [it for it in items if it["kind"] == "scam"]
    genuine = [it for it in items if it["kind"] == "genuine"]
    same = [cos(a["vector"], b["vector"]) for i, a in enumerate(scam) for b in scam[i + 1:]
            if a["category"] == b["category"]]
    cross = [cos(a["vector"], b["vector"]) for a in scam for b in genuine]
    same_med, cross_med = statistics.median(same), statistics.median(cross)
    return {
        "same_category_median": round(same_med, 4),
        "scam_vs_genuine_median": round(cross_med, 4),
        # a chunk "hits" a pattern when it is about as close as two phrasings of the same trick
        "hit_floor": round(same_med, 4),
        # and is a near-copy when it is closer than most phrasings of the same trick are to each other
        "strong_floor": round(statistics.quantiles(same, n=4)[2], 4),
        # it must also be closer to the scam phrase than to the nearest honest phrase by this much
        "margin": round(max(0.02, (same_med - cross_med) / 4), 4),
    }


def main():
    cfg = settings()
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    items = []
    for cat, spec in bank["categories"].items():
        for i, text in enumerate(spec["patterns"]):
            items.append({"id": f"{cat}-{i + 1}", "kind": "scam", "category": cat, "label": spec["label"],
                          "severity": spec["severity"], "text": text})
    for i, text in enumerate(bank["genuine"]):
        items.append({"id": f"genuine-{i + 1}", "kind": "genuine", "category": "genuine", "label": "Honest wording",
                      "severity": "none", "text": text})

    vectors, used, errors = None, None, []
    for style in REQUEST_STYLES:
        try:
            vectors = embed([it["text"] for it in items], cfg, style)
            used = style
            break
        except RuntimeError as e:
            errors.append(f"{style}: {e}")
            if "HTTP 400" not in str(e):
                break
    if vectors is None:
        sys.exit("Embedding failed:\n  " + "\n  ".join(errors))

    for it, v in zip(items, vectors):
        it["vector"] = [round(x, 6) for x in v]
    cal = calibrate(items)
    index = {
        "model": cfg["model"], "dims": DIMS, "request_style": used, "task_type": "SEMANTIC_SIMILARITY",
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "bank_version": bank["version"],
        "calibration": cal, "categories": {k: {"label": v["label"], "severity": v["severity"]}
                                           for k, v in bank["categories"].items()},
        "items": items,
    }
    INDEX.write_text(json.dumps(index), encoding="utf-8")
    n_scam = sum(it["kind"] == "scam" for it in items)
    print(f"Wrote {INDEX.name}: {n_scam} scam phrases, {len(items) - n_scam} honest phrases, "
          f"{DIMS} dims, model {cfg['model']}, request style '{used}'")
    print(f"Calibration: {cal}")


if __name__ == "__main__":
    main()
