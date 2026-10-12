// Shared by the three "verdict" Code nodes (the builder pastes it on top of each).
// Final status from the fused risk: blocked >= blockAt, review >= reviewAt, else approved.

function decide(risk, cfg, forceReview) {
  const blockAt = Number(cfg.blockAt ?? 0.7), reviewAt = Number(cfg.reviewAt ?? 0.4);
  let status = risk >= blockAt ? "blocked" : risk >= reviewAt ? "review" : "approved";
  if (forceReview && status === "approved") status = "review";
  return status;
}

function stageReasons(item) {
  const r = [];
  for (const c of (item.stage1 && item.stage1.categories) || []) {
    r.push(`Vector match, ${c.label} (similarity ${c.similarity}${c.strong ? ", near-copy" : ""}): "${c.chunk.slice(0, 160)}"`);
  }
  for (const s of item.signals || []) r.push(s.label);
  if (item.stage1 && item.stage1.error) r.push(item.stage1.error);
  return r;
}
