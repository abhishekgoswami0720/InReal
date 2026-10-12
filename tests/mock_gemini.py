"""
A stand-in for the Gemini API, for tests only (no key, no network).

Embeddings are hashed bags of words and word pairs, so texts that share wording get similar
vectors. That is enough to test the pipeline's plumbing and arithmetic; the real thresholds
come from build_index.py running against the real model.

    python tests/mock_gemini.py --port 8765
"""
import argparse
import hashlib
import json
import math
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = "test-key"
STOP = {"the", "a", "an", "to", "of", "and", "for", "on", "in", "your", "our", "is", "be", "will", "with", "at", "by", "you"}
REQUESTS = []


def embed(text: str, dims: int = 768) -> list:
    words = re.findall(r"[a-z0-9₹]+", text.lower())
    feats = [(w, 0.3 if w in STOP else 1.0) for w in words]
    feats += [(f"{a} {b}", 0.7) for a, b in zip(words, words[1:])]
    v = [0.0] * dims
    for f, w in feats:
        h = hashlib.md5(f.encode()).hexdigest()
        v[int(h[:8], 16) % dims] += w if int(h[8], 16) % 2 else -w
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def judge(post: str) -> dict:
    text = post.split("Text:", 1)[-1].split("Automated findings:", 1)[0]
    if "MOCK_HALLUCINATE" in text:
        return {"scam_probability": 0.95, "verdict": "scam", "categories": ["upfront_fee"],
                "evidence": [{"quote": "pay the processing fee before joining", "why": "fee"}], "summary": "Asks for a fee."}
    m = re.search(r"[^.]*\b(deposit|fee|pay)\b[^.]*", text, re.I)
    if m:
        quote = " ".join(m.group(0).split()[:20])
        return {"scam_probability": 0.9, "verdict": "scam", "categories": ["upfront_fee"],
                "evidence": [{"quote": quote, "why": "Asks the candidate to pay."}], "summary": "Asks for money."}
    return {"scam_probability": 0.06, "verdict": "genuine", "categories": ["none"], "evidence": [],
            "genuine_signs": ["Describes real work"], "summary": "Ordinary internship post."}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        REQUESTS.append({"path": self.path, "body": data})
        if self.headers.get("x-goog-api-key") != KEY:
            return self._send(403, {"error": {"code": 403, "message": "API key not valid"}})
        if self.path.endswith(":batchEmbedContents"):
            out = []
            for r in data.get("requests", []):
                if "outputDimensionality" in r and "embedContentConfig" not in r:
                    return self._send(400, {"error": {"code": 400, "message": "Unknown name outputDimensionality"}})
                dims = (r.get("embedContentConfig") or {}).get("outputDimensionality", 1024)
                out.append({"values": embed(r["content"]["parts"][0]["text"], dims)})
            return self._send(200, {"embeddings": out})
        if self.path.endswith(":generateContent"):
            text = data["contents"][-1]["parts"][0]["text"]
            results = []
            for block in re.split(r"\n\n---\n\n", text):
                m = re.match(r"POST (\S+)", block)
                if m:
                    results.append({"id": m.group(1), **judge(block)})
            body = {"results": results}
            return self._send(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}], "role": "model"}}]})
        return self._send(404, {"error": {"code": 404, "message": "not found"}})


def serve(port: int):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    serve(ap.parse_args().port).serve_forever()
