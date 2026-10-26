"""Verdicts, port of n8n/code/_verdict_lib.js, fuse.js, stage1_verdict.js and expired_verdict.js.

The AI's answer is one witness, not the judge:
  1. every quote it gives is searched for in the real post; quotes that aren't there are thrown out
  2. a high scam probability with no surviving quote is pulled back towards 0.5 ("can't tell")
  3. the AI, the vector search and the link/contact rules are combined with fixed weights,
     so the AI alone can push a post to "review" but never to "blocked"
  4. if the AI and the vector search strongly disagree, a person looks at it
Exception (19 Oct): the AI was sure (0.9+) AND its verified quote asks for money or ID -> blocked.
"""
import json
import re

WEIGHTS = {"llm": 0.6, "vector": 0.25, "signals": 0.15}
SURE = 0.9
A = re.ASCII | re.IGNORECASE
ASKS_MONEY_OR_ID = re.compile(r"\b(fees?|deposit|refundable|charges?|purchase|buy|registration|register for|security (amount|money)|kit|pay|paying|payment)\b|aadhaa?r|\bpan\b|passbook|bank (details|account|statement)|\botp\b", A)
PRICED_PROGRAM = re.compile(r"(₹|\brs\.?\s?\d|\binr\b)[^.]{0,60}\b(training|course|program|programme|certificate|starter|enrol|enroll|emi)\b|\b(training|course|program|programme|certificate|starter|enrol|enroll)\b[^.]{0,60}(₹|\brs\.?\s?\d|\binr\b)", A)
NEGATED_MONEY_RE = re.compile(r"\b(no|not|never|zero|without|free of|nil|dont|doesnt|wont)\b[^.]{0,40}\b(fee|fees|charge|charges|payment|pay|deposit|money)\b", A)


def decide(risk: float, cfg: dict, force_review: bool) -> str:
    block_at, review_at = float(cfg.get("blockAt", 0.7)), float(cfg.get("reviewAt", 0.4))
    status = "blocked" if risk >= block_at else "review" if risk >= review_at else "approved"
    return "review" if force_review and status == "approved" else status


def _num(x) -> str:
    f = float(x)
    return str(int(f)) if f == int(f) else repr(f)


def stage_reasons(item: dict) -> list:
    r = []
    for c in (item.get("stage1") or {}).get("categories") or []:
        r.append(f'Vector match, {c["label"]} (similarity {_num(c["similarity"])}{", near-copy" if c["strong"] else ""}): "{c["chunk"][:160]}"')
    r += [s["label"] for s in item.get("signals") or []]
    if (item.get("stage1") or {}).get("error"):
        r.append(item["stage1"]["error"])
    return r


def stage1_verdict(item: dict, cfg: dict) -> dict:
    risk = max(float(cfg.get("blockAt", 0.7)), 0.6 + 0.4 * item["stage1"]["vector_risk"], item["signal_risk"])
    return {"id": item["id"], "status": decide(risk, cfg, False), "scam_risk": round(min(0.99, risk), 2),
            "reasons": [f"Stage 1: {item['gate']['why']}", *stage_reasons(item)], "decided_by": "vector_search"}


def expired_verdict(listing: dict, link: dict) -> dict:
    why = (f'Apply page says "{link.get("closed_phrase")}"' if link.get("link_state") == "closed"
           else f'Apply page returned HTTP {link.get("http_status")} ({link.get("link_state")})')
    return {"id": listing["id"], "status": "expired", "scam_risk": 0, "reasons": [why], "decided_by": "link_check"}


def norm(s) -> str:
    s = re.sub(r"[“”\"'’`]", "", str(s or "").lower())
    s = re.sub(r"[^a-z0-9₹%@.\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def asking_quote(verified: list):
    return next((ev for ev in verified if ASKS_MONEY_OR_ID.search(ev["quote"]) or PRICED_PROGRAM.search(ev["quote"])), None)


def parse_llm(resp: dict) -> dict:
    try:
        text = "".join(p.get("text", "") for p in resp["candidates"][0]["content"]["parts"])
        j = json.loads(text)
        p = float(j["scam_probability"])
        if not 0 <= p <= 1:
            raise ValueError("scam_probability missing")
        return {"ok": True, **j, "scam_probability": p}
    except Exception as e:  # noqa: BLE001 - any malformed answer is "unavailable"
        why = json.dumps(resp["error"], separators=(",", ":"))[:200] if isinstance(resp, dict) and resp.get("error") else str(e)
        return {"ok": False, "error": why}


def verify_evidence(listing: dict, evidence: list) -> tuple:
    source = norm(" ".join(str(listing.get(k) or "") for k in ("role_title", "company_name", "stipend", "description")))
    verified, rejected, contradicting = [], [], []
    for ev in evidence or []:
        q = norm(ev.get("quote"))
        if not (len(q) >= 8 and q in source):
            rejected.append(ev)
        elif NEGATED_MONEY_RE.search(q):
            contradicting.append(ev)
        else:
            verified.append(ev)
    return verified, rejected, contradicting


# A post that talks to the AI reviewer ("ignore previous instructions", "rate this as genuine") is
# trying to steer the check. Real internship posts never do that, so it never gets "verified".
# (Python pipeline only; the old n8n workflow does not have this rule.) Words like "system prompt" or
# "you are an AI" are left out on purpose: real AI/LLM internship posts use them.
INJECTION_RE = re.compile(
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts?|rules)"
    r"|disregard (all |any )?(the )?(previous|prior|above) "
    r"|(to|for) the (ai|automated|llm) (reviewer|checker|moderator|system)s?\b"
    r"|\b(rate|mark|classify|label|score) (this|the) (post|listing|internship|job) as (genuine|safe|legit|approved|not a scam)"
    r"|scam_probability|\bverdict\s*[:=]",
    re.I)


def injection_phrase(listing: dict) -> str:
    text = " ".join(str(listing.get(k) or "") for k in ("role_title", "company_name", "description"))
    m = INJECTION_RE.search(text)
    return m.group(0) if m else ""


def fuse(listing: dict, item: dict, resp: dict, cfg: dict) -> dict:
    llm = parse_llm(resp)
    reasons, p_adj, verified, rejected, contradicting = [], None, [], [], []
    if llm["ok"]:
        verified, rejected, contradicting = verify_evidence(listing, llm.get("evidence"))
        p_adj = llm["scam_probability"]
        if p_adj > 0.5 and not verified:
            p_adj = 0.5 + (p_adj - 0.5) * 0.25           # a claim without proof counts for little
            reasons.append(f"LLM said {llm.get('verdict')} ({_num(llm['scam_probability'])}) but quoted nothing found in the post, so it was discounted")
        if rejected:
            reasons.append(f"Ignored {len(rejected)} LLM quote(s) that are not in the post")
        for ev in contradicting:
            reasons.append(f'Ignored LLM quote that says the opposite (no fee): "{ev["quote"]}"')
    else:
        reasons.append(f"LLM judge unavailable ({llm['error']}); decided on stage-1 evidence only")

    v, s = item["stage1"]["vector_risk"], item["signal_risk"]
    if p_adj is None:
        risk = max(0.4 * v + 0.2 * s, 0.4 if v >= 0.5 else 0)    # no AI: never auto-approve a vector hit
    else:
        risk = WEIGHTS["llm"] * p_adj + WEIGHTS["vector"] * v + WEIGHTS["signals"] * s
    disagree = p_adj is not None and abs(p_adj - v) >= 0.6
    if disagree:
        reasons.append(f"LLM ({p_adj:.2f}) and vector search ({v:.2f}) disagree, so a person should check")
    if llm["ok"]:
        reasons.insert(0, f"LLM: {llm.get('verdict')}, probability {_num(llm['scam_probability'])} — {llm.get('summary') or ''}".strip())
        reasons += [f'Quote: "{ev["quote"]}" ({ev.get("why")})' for ev in verified[:3]]
    reasons += stage_reasons(item)

    proof = asking_quote(verified) if llm["ok"] and llm["scam_probability"] >= SURE else None
    if proof:
        risk = max(risk, float(cfg.get("blockAt", 0.7)))
        reasons.insert(0, f'Blocked: the AI judge was sure ({_num(llm["scam_probability"])}) and the post itself asks for money or ID documents: "{proof["quote"]}"')

    # neither AI stage ran (both APIs down): don't approve on rules alone, put it back in the queue
    nothing_ran = p_adj is None and bool(item.get("stage1", {}).get("error"))
    if nothing_ran:
        reasons.insert(0, "Both AI checks failed this time; queued again")
    steer = injection_phrase(listing)
    if steer:
        reasons.insert(0, f'The post tries to give instructions to the AI reviewer ("{steer}"), so a person should check it')
        risk = max(risk, float(cfg.get("reviewAt", 0.4)))
    return {
        "id": item["id"],
        "status": "retry" if nothing_ran else "blocked" if proof else decide(risk, cfg, disagree or bool(steer)),
        "scam_risk": round(min(0.99, max(0, risk)), 2),
        "reasons": reasons,
        "decided_by": "fusion" if llm["ok"] else "vector_search",
        "parts": {"llm_raw": llm["scam_probability"] if llm["ok"] else None,
                  "llm_adjusted": None if p_adj is None else round(p_adj, 3),
                  "vector_risk": v, "signal_risk": s, "verified_quotes": len(verified),
                  "rejected_quotes": len(rejected) + len(contradicting), "sure_and_proven": bool(proof)},
    }


def answer_text(resp: dict) -> str:
    """Azure chat answer or Gemini answer -> the JSON text the model wrote."""
    if resp and "choices" in resp:
        c = resp["choices"][0]
        if c.get("finish_reason") == "content_filter":
            raise ValueError("blocked by Azure content filter")
        if (c.get("message") or {}).get("refusal"):
            raise ValueError("model refused: " + c["message"]["refusal"])
        return c["message"]["content"]
    return "".join(p.get("text", "") for p in resp["candidates"][0]["content"]["parts"])


def split_batch(posts: list, resp: dict) -> list:
    """One mini-batch answer -> one Gemini-shaped answer per post, so fuse() judges each post alone."""
    results, error = None, None
    try:
        results = json.loads(answer_text(resp)).get("results") or []
    except Exception as e:  # noqa: BLE001
        error = resp["error"] if isinstance(resp, dict) and resp.get("error") else {"message": str(e)}
    out = []
    for p in posts:
        if results is None:
            out.append({"error": error})
            continue
        r = next((x for x in results if str(x.get("id")) == str(p["id"])), None)
        out.append({"error": {"message": "the LLM returned no result for this post"}} if r is None
                   else {"candidates": [{"content": {"parts": [{"text": json.dumps(r, ensure_ascii=False)}]}}]})
    return out


def fuse_batches(batches: list, answers: list, cfg: dict) -> list:
    out = []
    for i, b in enumerate(batches):
        per = split_batch(b["posts"], answers[i] if i < len(answers) and answers[i] else {})
        out += [{"verdict": fuse(p["listing"], p, per[k], cfg)} for k, p in enumerate(b["posts"])]
    return out
