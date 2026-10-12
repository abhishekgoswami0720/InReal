// Stage 1 verdict — "Blocked at stage 1" (n8n Code node, runs once for each listing)
// Reached only when the vector search found a near-copy of a high-severity scam phrase
// (or payment wording plus a UPI ID). The LLM is not asked: the evidence is already explicit.

function stage1Verdict(item, cfg) {
  const risk = Math.max(Number(cfg.blockAt ?? 0.7), 0.6 + 0.4 * item.stage1.vector_risk, item.signal_risk);
  return {
    id: item.id,
    status: decide(risk, cfg, false),
    scam_risk: Number(Math.min(0.99, risk).toFixed(2)),
    reasons: [`Stage 1: ${item.gate.why}`, ...stageReasons(item)],
    decided_by: "vector_search",
  };
}

// ==== n8n glue (below this line runs only inside n8n) ====
return { json: { verdict: stage1Verdict($json, $('Config').first().json) } };
