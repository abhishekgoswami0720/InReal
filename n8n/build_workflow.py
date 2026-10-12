"""
Builds n8n/inreal_moderation.json (the file you import into n8n) from the Code-node
sources in n8n/code/. Edit the .js files, then run:

    python n8n/build_workflow.py

Keeping the logic in .js files means it can be tested outside n8n (tests/test_n8n_code.py).
"""
import json
import uuid
from pathlib import Path

HERE = Path(__file__).parent
CODE = HERE / "code"
OUT = HERE / "inreal_moderation.json"
GLUE = "// ==== n8n glue (below this line runs only inside n8n) ===="
GEMINI_CRED = {"httpHeaderAuth": {"id": "inrealGeminiKey", "name": "Gemini API key"}}
# One Header Auth credential for both Azure OpenAI nodes (embeddings + gpt-4o judge): Name "api-key".
# To go back to Gemini, give those nodes a Header Auth with Name "x-goog-api-key" instead.
AZURE_CRED = {"httpHeaderAuth": {"id": "inrealAzureKey", "name": "Azure OpenAI key"}}
CFG = "$('Config').first().json"


def _id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "inreal-moderation/" + name))


def code_source(*files: str) -> str:
    return "\n\n".join((CODE / f).read_text(encoding="utf-8").strip() for f in files) + "\n"


def node(name, type_, version, pos, params, **extra):
    n = {"parameters": params, "id": _id(name), "name": name, "type": type_, "typeVersion": version, "position": pos}
    n.update(extra)
    return n


def code_node(name, pos, *files, all_items=False):
    params = {"jsCode": code_source(*files)}
    if not all_items:
        params["mode"] = "runOnceForEachItem"
    return node(name, "n8n-nodes-base.code", 2, pos, params)


def http(name, pos, url, method="GET", body_expr=None, gemini=False, batch=None, must_work=False, embed_cred=False, judge_cred=False, **extra):
    params = {"url": url, "options": {"response": {"response": {"neverError": not must_work}}, "timeout": 30000}}
    if method != "GET":
        params["method"] = method
    if body_expr:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body_expr})
    if gemini or embed_cred or judge_cred:
        params.update({"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"})
        extra["credentials"] = AZURE_CRED if (embed_cred or judge_cred) else GEMINI_CRED
    if batch:
        params["options"]["batching"] = {"batch": {"batchSize": batch[0], "batchInterval": batch[1]}}
    if not must_work:
        extra["onError"] = "continueRegularOutput"
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, params, **extra)


def if_node(name, pos, left, rights):
    conditions = [{"id": _id(f"{name}-{r}"), "leftValue": left, "rightValue": r,
                   "operator": {"type": "string", "operation": "equals"}} for r in rights]
    return node(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "conditions": conditions, "combinator": "or"},
        "options": {}})


def assignment(name, value, type_):
    return {"id": _id("cfg-" + name), "name": name, "value": value, "type": type_}


def sticky(name, pos, text, w, h, color=None):
    p = {"content": text, "height": h, "width": w}
    if color:
        p["color"] = color
    return node(name, "n8n-nodes-base.stickyNote", 1, pos, p)


def build():
    nodes = [
        node("Run manually", "n8n-nodes-base.manualTrigger", 1, [-1200, 300], {}),
        node("Every 30 minutes", "n8n-nodes-base.scheduleTrigger", 1.2, [-1200, 120],
             {"rule": {"interval": [{"field": "minutes", "minutesInterval": 30}]}}),
        node("After a scrape (webhook)", "n8n-nodes-base.webhook", 2, [-1200, 480],
             {"httpMethod": "POST", "path": "inreal-moderate", "responseMode": "onReceived", "options": {}},
             webhookId=_id("webhook")),
        node("Config", "n8n-nodes-base.set", 3.4, [-960, 300], {"assignments": {"assignments": [
            # not "localhost": Node 24 tries ::1 first and Flask only listens on IPv4
            assignment("flaskBase", "http://127.0.0.1:5000", "string"),
            assignment("geminiBase", "https://generativelanguage.googleapis.com", "string"),
            # LLM judge: "azure" (gpt-4o deployment below) or "gemini" (judgeModel on geminiBase)
            assignment("judgeProvider", "azure", "string"),
            assignment("azureJudgeUrl", "https://YOUR-RESOURCE.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2025-01-01-preview", "string"),
            assignment("judgeModel", "gemini-3.5-flash-lite", "string"),
            assignment("batchLimit", 120, "number"),
            assignment("blockAt", 0.7, "number"),
            assignment("reviewAt", 0.4, "number"),
            # empty = use the thresholds measured by build_index.py
            assignment("hitFloor", "", "string"),
            assignment("strongFloor", "", "string"),
            assignment("margin", "", "string"),
        ]}, "options": {}}),
        http("Fetch pattern bank", [-740, 300], f"={{{{ {CFG}.flaskBase }}}}/api/moderation/patterns", executeOnce=True, must_work=True),
        http("Fetch pending listings", [-520, 300],
             f"={{{{ {CFG}.flaskBase }}}}/api/moderation/pending?claim=1&limit={{{{ {CFG}.batchLimit }}}}", executeOnce=True, must_work=True),
        http("Resolve apply link", [-300, 300],
             f"={{{{ {CFG}.flaskBase }}}}/api/moderation/resolve?id={{{{ $json.id }}}}", batch=(10, 0)),
        if_node("Link dead or closed?", [-80, 300], "={{ $json.link_state }}", ["dead", "closed"]),
        code_node("Expired listing", [160, 80], "expired_verdict.js"),
        code_node("Link + contact signals", [160, 400], "signals.js"),
        code_node("Pack embedding mini-batches", [380, 400], "pack_embed.js", all_items=True),
        # URL comes from the pattern index (Azure OpenAI or Gemini, whichever built it); key from the credential
        http("Embed chunks", [600, 400], "={{ $('Fetch pattern bank').first().json.embed_url }}",
             method="POST", body_expr="={{ JSON.stringify($json.embedRequest) }}", embed_cred=True, batch=(1, 300)),
        code_node("Vector search vs scam patterns", [820, 400], "vector_search.js", all_items=True),
        if_node("Stage 1 conclusive?", [1040, 400], "={{ $json.gate.decision }}", ["block"]),
        code_node("Blocked at stage 1", [1280, 220], "_verdict_lib.js", "stage1_verdict.js"),
        code_node("Pack judge mini-batches", [1280, 520], "judge_prompt.js", all_items=True),
        # gpt-4o deployment: 50k tokens/min; one call of 8 posts is ~6-7k tokens, so 8 s apart
        http("LLM judge (8 posts per call)", [1500, 520],
             f"={{{{ {CFG}.judgeProvider === 'azure' ? {CFG}.azureJudgeUrl : {CFG}.geminiBase + '/v1beta/models/' + {CFG}.judgeModel + ':generateContent' }}}}",
             method="POST", body_expr="={{ JSON.stringify($json.judgeRequest) }}", judge_cred=True, batch=(1, 8000)),
        code_node("Verify evidence + fuse scores", [1720, 520], "_verdict_lib.js", "fuse.js", all_items=True),
        http("Save verdict", [1960, 300], f"={{{{ {CFG}.flaskBase }}}}/api/moderation/verdict",
             method="POST", body_expr="={{ JSON.stringify($json.verdict) }}", batch=(10, 0),
             must_work=True, retryOnFail=True, maxTries=3, waitBetweenTries=1000),
        sticky("About", [-1260, -220], (
            "## InReal scam moderation\n"
            "Runs after EACH site is scraped (claims its own listings, so runs overlap safely). New listings go through 3 stages in mini-batches:\n"
            "**0. Rules** – where the apply link redirects, WhatsApp/Telegram/UPI/free-mail in the post\n"
            "**1. Vector search** – each sentence vs a bank of known scam phrases *and* honest phrases "
            "(moderation/scam_patterns.json). Near-copies of high-risk scams are blocked here.\n"
            "**2. One-shot LLM judge (gpt-4o on Azure)** – 8 posts per call, fixed JSON schema, must quote each post. Quotes are checked "
            "against the real text and the score is fused with stages 0–1, so the LLM can't block a post alone.\n"
            "Verdicts go back to the dashboard: approved / review / blocked / expired."), 520, 300),
        sticky("Stage 1 note", [360, 620], (
            "Thresholds come from the bank itself (`calibration` in pattern_index.json). "
            "Override hitFloor / strongFloor / margin in **Config** if you see too many or too few hits."), 360, 140, 5),
    ]
    c = lambda a, b, out=0: (a, b, out)
    links = [
        c("Run manually", "Config"), c("Every 30 minutes", "Config"), c("After a scrape (webhook)", "Config"),
        c("Config", "Fetch pattern bank"), c("Fetch pattern bank", "Fetch pending listings"),
        c("Fetch pending listings", "Resolve apply link"), c("Resolve apply link", "Link dead or closed?"),
        c("Link dead or closed?", "Expired listing", 0), c("Link dead or closed?", "Link + contact signals", 1),
        c("Expired listing", "Save verdict"),
        c("Link + contact signals", "Pack embedding mini-batches"),
        c("Pack embedding mini-batches", "Embed chunks"), c("Embed chunks", "Vector search vs scam patterns"),
        c("Vector search vs scam patterns", "Stage 1 conclusive?"),
        c("Stage 1 conclusive?", "Blocked at stage 1", 0), c("Stage 1 conclusive?", "Pack judge mini-batches", 1),
        c("Blocked at stage 1", "Save verdict"),
        c("Pack judge mini-batches", "LLM judge (8 posts per call)"),
        c("LLM judge (8 posts per call)", "Verify evidence + fuse scores"), c("Verify evidence + fuse scores", "Save verdict"),
    ]
    connections = {}
    for a, b, out in links:
        outs = connections.setdefault(a, {"main": []})["main"]
        while len(outs) <= out:
            outs.append([])
        outs[out].append({"node": b, "type": "main", "index": 0})

    wf = {"name": "InReal – scam moderation", "nodes": nodes, "connections": connections, "active": False,
          "settings": {"executionOrder": "v1"}, "pinData": {}, "meta": {"templateCredsSetupCompleted": False},
          "tags": []}
    OUT.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT} ({len(nodes)} nodes)")


if __name__ == "__main__":
    build()
