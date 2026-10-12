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


def main():
    load_env()
    ok = True
    cfg = settings()
    if cfg["provider"] != "azure":
        print("EMBED_PROVIDER is not 'azure' in .env, checking the judge only")
    else:
        t = time.time()
        r = requests.post(cfg["url"], json={"input": ["pay a registration fee", "we never charge a fee"], "dimensions": DIMS},
                          headers={"api-key": cfg["key"]}, timeout=30)
        if r.status_code == 200:
            d = r.json()["data"]
            print(f"✅ Embeddings: {len(d)} vectors of {len(d[0]['embedding'])} numbers in {time.time() - t:.1f}s")
        else:
            ok = False
            print(f"❌ Embeddings HTTP {r.status_code}: {r.text[:300]}")

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
    r = requests.post(url, json=body, headers={"api-key": key}, timeout=60)
    if r.status_code != 200:
        print(f"❌ Judge HTTP {r.status_code}: {r.text[:400]}")
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
