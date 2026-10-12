"""
Quick live check of the two Azure OpenAI deployments the scam check uses.

    python -m moderation.check_azure

Reads .env (EMBED_PROVIDER=azure, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_EMBED_DEPLOYMENT,
AZURE_OPENAI_KEY, AZURE_OPENAI_JUDGE_URL). Sends one embedding request and one 2-post judge
request built by the same code n8n runs, and prints what came back. Costs a fraction of a rupee.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

from moderation.build_index import DIMS, settings
from moderation.env import load_env

ROOT = Path(__file__).resolve().parents[1]
POSTS = [
    {"id": "fake", "role_title": "Data Science Intern", "company_name": "Brightpath", "stipend": "25,000/month",
     "source_platform": "test", "description": "Selected candidates must pay a refundable security deposit of Rs 1500 "
     "to confirm the internship. Contact HR on WhatsApp."},
    {"id": "real", "role_title": "ML Intern", "company_name": "Acme Robotics", "stipend": "20,000/month",
     "source_platform": "test", "description": "Train and evaluate computer vision models with our team. "
     "Selection is through a technical interview. We never charge candidates any fee."},
]


def _post(url, body, key, what):
    try:
        return requests.post(url, json=body, headers={"api-key": key}, timeout=60)
    except requests.exceptions.RequestException as e:
        host = url.split("/")[2] if "//" in url else url
        print(f"❌ {what}: could not reach {host} ({type(e).__name__}). Check the URL in .env.")
        return None


def _explain_401(what):
    print(f"   → {what}: Azure rejected the key. Copy KEY 1 again from the portal (Keys and Endpoint) into "
          f"AZURE_OPENAI_KEY, with no quotes or spaces. If you regenerated the key, the old one stops working.")


def preflight():
    """Catches the usual .env mistakes before calling Azure, without printing the key."""
    problems = []
    for k in ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_EMBED_DEPLOYMENT", "AZURE_OPENAI_KEY", "AZURE_OPENAI_JUDGE_URL"]:
        v = os.environ.get(k, "").strip()
        if not v:
            problems.append(f"{k} is empty")
        elif "YOUR-RESOURCE" in v.upper() or v.startswith("<"):
            problems.append(f"{k} still has the placeholder from .env.example: {v[:60]}")
    from moderation.env import ENV_FILE, LOADED_FROM_FILE
    print(f".env file: {ENV_FILE} ({'found' if ENV_FILE.exists() else 'NOT FOUND'})")
    for k in ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_EMBED_DEPLOYMENT", "AZURE_OPENAI_JUDGE_URL"]:
        v = os.environ.get(k, "")
        print(f"  {k} = {v[:110]}  [{'from .env' if k in LOADED_FROM_FILE else 'from Windows/terminal'}]")
    key = os.environ.get("AZURE_OPENAI_KEY", "").strip()
    if key:
        print(f"Key in .env: {len(key)} characters, starts '{key[:4]}', ends '{key[-4:]}'")
        if key != key.strip("'\"") or " " in key:
            problems.append("AZURE_OPENAI_KEY has quotes or spaces in it")
    for p in problems:
        print(f"❌ .env: {p}")
    return not problems


def main():
    load_env()
    if not preflight():
        sys.exit(1)
    ok = True
    cfg = settings()
    if cfg["provider"] != "azure":
        print("EMBED_PROVIDER is not 'azure' in .env, checking the judge only")
    else:
        t = time.time()
        r = _post(cfg["url"], {"input": ["pay a registration fee", "we never charge a fee"], "dimensions": DIMS},
                  cfg["key"], "Embeddings")
        if r is None:
            ok = False
        elif r.status_code == 200:
            d = r.json()["data"]
            print(f"✅ Embeddings: {len(d)} vectors of {len(d[0]['embedding'])} numbers in {time.time() - t:.1f}s")
        else:
            ok = False
            print(f"❌ Embeddings HTTP {r.status_code}: {r.text[:300]}")
            if r.status_code == 401:
                _explain_401("Embeddings")

    url = os.environ.get("AZURE_OPENAI_JUDGE_URL", "").strip()
    key = os.environ.get("AZURE_OPENAI_KEY", "").strip()
    if not url:
        sys.exit("AZURE_OPENAI_JUDGE_URL is missing in .env")
    node = shutil.which("node")
    if not node:
        sys.exit("Node.js is needed to build the judge request exactly like n8n does")
    items = [{"id": p["id"], "listing": p, "stage1": {"categories": []}, "signals": []} for p in POSTS]
    out = subprocess.run([node, str(ROOT / "tests" / "js_runner.js"), "judge_prompt.js", "packJudge"],
                         input=json.dumps([items, "azure"]), capture_output=True, text=True, timeout=30)
    if out.returncode:
        sys.exit(out.stderr)
    body = json.loads(out.stdout)[0]["judgeRequest"]
    t = time.time()
    r = _post(url, body, key, "Judge (gpt-4o)")
    if r is None:
        sys.exit(1)
    if r.status_code != 200:
        print(f"❌ Judge HTTP {r.status_code}: {r.text[:400]}")
        if r.status_code == 401:
            _explain_401("Judge")
        sys.exit(1)
    msg = r.json()["choices"][0]["message"]["content"]
    usage = r.json().get("usage", {})
    print(f"✅ Judge answered in {time.time() - t:.1f}s, {usage.get('total_tokens', '?')} tokens")
    for res in json.loads(msg)["results"]:
        print(f"   {res['id']:>5}: {res['verdict']:<10} p={res['scam_probability']}  {res['summary'][:90]}")
        for ev in res["evidence"][:2]:
            print(f"          quote: \"{ev['quote']}\"")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
