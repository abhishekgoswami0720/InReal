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
CFG = "$('Config').first().json"


def _id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "inreal-moderation/" + name))


def code_source(*files: str) -> str:
    return "\n\n".join((CODE / f).read_text(encoding="utf-8").strip() for f in files) + "\n"


def node(name, type_, version, pos, params, **extra):
    n = {"parameters": params, "id": _id(name), "name": name, "type": type_, "typeVersion": version, "position": pos}
    n.update(extra)
    return n


def code_node(name, pos, *files):
    return node(name, "n8n-nodes-base.code", 2, pos, {"mode": "runOnceForEachItem", "jsCode": code_source(*files)})


def http(name, pos, url, method="GET", body_expr=None, gemini=False, batch=None, must_work=False, **extra):
    params = {"url": url, "options": {"response": {"response": {"neverError": not must_work}}, "timeout": 30000}}
    if method != "GET":
        params["method"] = method
    if body_expr:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body_expr})
    if gemini:
        params.update({"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"})
        extra["credentials"] = GEMINI_CRED
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
            assignment("judgeModel", "gemini-3.5-flash-lite", "string"),
            assignment("batchLimit", 40, "number"),
            assignment("blockAt", 0.7, "number"),
            assignment("reviewAt", 0.4, "number"),
            # empty = use the thresholds measured by build_index.py
            assignment("hitFloor", "", "string"),
            assignment("strongFloor", "", "string"),
            assignment("margin", "", "string"),
        ]}, "options": {}}),
        http("Fetch pattern bank", [-740, 300], f"={{{{ {CFG}.flaskBase }}}}/api/moderation/patterns", executeOnce=True, must_work=True),
        http("Fetch pending listings", [-520, 300],
             f"={{{{ {CFG}.flaskBase }}}}/api/moderation/pending?limit={{{{ {CFG}.batchLimit }}}}", executeOnce=True, must_work=True),
        http("Resolve apply link", [-300, 300],
             f"={{{{ {CFG}.flaskBase }}}}/api/moderation/resolve?id={{{{ $json.id }}}}", batch=(5, 0)),
        if_node("Link dead or closed?", [-80, 300], "={{ $json.link_state }}", ["dead", "closed"]),
        code_node("Expired listing", [160, 80], "expired_verdict.js"),
        code_node("Link + contact signals", [160, 400], "signals.js"),
        http("Embed chunks (Gemini)", [380, 400],
             f"={{{{ {CFG}.geminiBase }}}}/v1beta/models/{{{{ $('Fetch pattern bank').first().json.model }}}}:batchEmbedContents",
             method="POST", body_expr="={{ JSON.stringify($json.embedRequest) }}", gemini=True, batch=(1, 700)),
        code_node("Vector search vs scam patterns", [600, 400], "vector_search.js"),
        if_node("Stage 1 conclusive?", [820, 400], "={{ $json.gate.decision }}", ["block"]),
        code_node("Blocked at stage 1", [1060, 220], "_verdict_lib.js", "stage1_verdict.js"),
        code_node("Build one-shot judge request", [1060, 520], "judge_prompt.js"),
        http("LLM judge (Gemini, one call)", [1280, 520],
             f"={{{{ {CFG}.geminiBase }}}}/v1beta/models/{{{{ {CFG}.judgeModel }}}}:generateContent",
             method="POST", body_expr="={{ JSON.stringify($json.judgeRequest) }}", gemini=True, batch=(1, 4000)),
        code_node("Verify evidence + fuse scores", [1500, 520], "_verdict_lib.js", "fuse.js"),
        http("Save verdict", [1740, 300], f"={{{{ {CFG}.flaskBase }}}}/api/moderation/verdict",
             method="POST", body_expr="={{ JSON.stringify($json.verdict) }}"),
        sticky("About", [-1260, -220], (
            "## InReal scam moderation\n"
            "New listings from the scraper go through 3 stages:\n"
            "**0. Rules** – where the apply link redirects, WhatsApp/Telegram/UPI/free-mail in the post\n"
            "**1. Vector search** – each sentence vs a bank of known scam phrases *and* honest phrases "
            "(moderation/scam_patterns.json). Near-copies of high-risk scams are blocked here.\n"
            "**2. One-shot LLM judge** – one call, fixed JSON schema, must quote the post. Quotes are checked "
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
        c("Link + contact signals", "Embed chunks (Gemini)"), c("Embed chunks (Gemini)", "Vector search vs scam patterns"),
        c("Vector search vs scam patterns", "Stage 1 conclusive?"),
        c("Stage 1 conclusive?", "Blocked at stage 1", 0), c("Stage 1 conclusive?", "Build one-shot judge request", 1),
        c("Blocked at stage 1", "Save verdict"),
        c("Build one-shot judge request", "LLM judge (Gemini, one call)"),
        c("LLM judge (Gemini, one call)", "Verify evidence + fuse scores"), c("Verify evidence + fuse scores", "Save verdict"),
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
