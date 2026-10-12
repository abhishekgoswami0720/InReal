// Stage 2b — "Verify evidence + fuse scores" (n8n Code node, runs once for ALL mini-batches:
// splits each batch answer back into one verdict per post)
// The LLM's answer is treated as one witness, not the judge:
//   1. every quote it gives is searched for in the real post; quotes that aren't there are thrown out
//   2. a high scam probability with no surviving quote is pulled back towards 0.5 ("can't tell")
//   3. the LLM, the vector search and the link/contact rules are combined with fixed weights,
//      so the LLM alone can push a post to "review" but never to "blocked"
//   4. if the LLM and the vector search strongly disagree, a human looks at it

const WEIGHTS = { llm: 0.6, vector: 0.25, signals: 0.15 };

function norm(s) {
  return String(s || "").toLowerCase().replace(/[“”"'’`]/g, "").replace(/[^a-z0-9₹%@.\s]/g, " ").replace(/\s+/g, " ").trim();
}

function parseLlm(resp) {
  try {
    const parts = resp.candidates[0].content.parts;
    const text = parts.map(p => p.text || "").join("");
    const j = JSON.parse(text);
    const p = Number(j.scam_probability);
    if (!(p >= 0 && p <= 1)) throw new Error("scam_probability missing");
    return { ok: true, ...j, scam_probability: p };
  } catch (e) {
    const why = resp && resp.error ? JSON.stringify(resp.error).slice(0, 200) : String(e.message || e);
    return { ok: false, error: why };
  }
}

// A quote like "We do not charge any fee" is in the post, but it argues AGAINST a scam
const NEGATED_MONEY_RE = /\b(no|not|never|zero|without|free of|nil|dont|doesnt|wont)\b[^.]{0,40}\b(fee|fees|charge|charges|payment|pay|deposit|money)\b/i;

function verifyEvidence(listing, evidence) {
  const source = norm([listing.role_title, listing.company_name, listing.stipend, listing.description].join(" "));
  const verified = [], rejected = [], contradicting = [];
  for (const ev of evidence || []) {
    const q = norm(ev.quote);
    if (!(q.length >= 8 && source.includes(q))) rejected.push(ev);
    else if (NEGATED_MONEY_RE.test(q)) contradicting.push(ev);
    else verified.push(ev);
  }
  return { verified, rejected, contradicting };
}

function fuse(listing, item, resp, cfg) {
  const llm = parseLlm(resp);
  const reasons = [];
  let pAdj = null, verified = [], rejected = [], contradicting = [];

  if (llm.ok) {
    ({ verified, rejected, contradicting } = verifyEvidence(listing, llm.evidence));
    pAdj = llm.scam_probability;
    if (pAdj > 0.5 && verified.length === 0) {
      pAdj = 0.5 + (pAdj - 0.5) * 0.25;          // a claim without proof counts for little
      reasons.push(`LLM said ${llm.verdict} (${llm.scam_probability}) but quoted nothing found in the post, so it was discounted`);
    }
    if (rejected.length) reasons.push(`Ignored ${rejected.length} LLM quote(s) that are not in the post`);
    for (const ev of contradicting) reasons.push(`Ignored LLM quote that says the opposite (no fee): "${ev.quote}"`);
  } else {
    reasons.push(`LLM judge unavailable (${llm.error}); decided on stage-1 evidence only`);
  }

  const v = item.stage1.vector_risk, s = item.signal_risk;
  let risk;
  if (pAdj === null) {
    risk = Math.max(0.4 * v + 0.2 * s, v >= 0.5 ? 0.4 : 0);   // no LLM: never auto-approve a vector hit
  } else {
    risk = WEIGHTS.llm * pAdj + WEIGHTS.vector * v + WEIGHTS.signals * s;
  }
  const disagree = pAdj !== null && Math.abs(pAdj - v) >= 0.6;
  if (disagree) reasons.push(`LLM (${pAdj.toFixed(2)}) and vector search (${v.toFixed(2)}) disagree, so a person should check`);

  if (llm.ok) {
    reasons.unshift(`LLM: ${llm.verdict}, probability ${llm.scam_probability} — ${llm.summary || ""}`.trim());
    for (const ev of verified.slice(0, 3)) reasons.push(`Quote: "${ev.quote}" (${ev.why})`);
  }
  reasons.push(...stageReasons(item));

  return {
    id: item.id,
    status: decide(risk, cfg, disagree),
    scam_risk: Number(Math.min(0.99, Math.max(0, risk)).toFixed(2)),
    reasons,
    decided_by: llm.ok ? "fusion" : "vector_search",
    parts: { llm_raw: llm.ok ? llm.scam_probability : null, llm_adjusted: pAdj === null ? null : Number(pAdj.toFixed(3)),
             vector_risk: v, signal_risk: s, verified_quotes: verified.length, rejected_quotes: rejected.length + contradicting.length },
  };
}

// One mini-batch answer -> one Gemini-shaped answer per post, so fuse() judges each post alone
function splitBatch(posts, resp) {
  let results = null, error = null;
  try {
    const text = resp.candidates[0].content.parts.map(p => p.text || "").join("");
    results = JSON.parse(text).results || [];
  } catch (e) {
    error = resp && resp.error ? resp.error : { message: String(e.message || e) };
  }
  return posts.map(p => {
    if (!results) return { error };
    const r = results.find(x => String(x.id) === String(p.id));
    if (!r) return { error: { message: "the LLM returned no result for this post" } };
    return { candidates: [{ content: { parts: [{ text: JSON.stringify(r) }] } }] };
  });
}

function fuseBatches(batches, answers, cfg) {
  const out = [];
  batches.forEach((b, i) => {
    const per = splitBatch(b.posts, answers[i] || {});
    b.posts.forEach((p, k) => out.push({ verdict: fuse(p.listing, p, per[k], cfg) }));
  });
  return out;
}

// ==== n8n glue (below this line runs only inside n8n) ====
const batches = $('Pack judge mini-batches').all().map(i => i.json);
const answers = $input.all().map(i => i.json);
return fuseBatches(batches, answers, $('Config').first().json).map(json => ({ json }));
