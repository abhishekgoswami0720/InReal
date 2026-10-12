// Stage 1 — "Vector search vs scam patterns" (n8n Code node, runs once for ALL listings:
// unpacks the mini-batch embedding answers back to their posts)
// Each chunk of the post is compared by cosine similarity with every phrase in the pattern
// bank (moderation/scam_patterns.json). A chunk only counts as a hit when it is
//   (a) about as close to a scam phrase as two phrasings of the same trick are to each other, and
//   (b) clearly closer to that scam phrase than to the nearest HONEST phrase.
// (b) is what keeps "There is no registration fee" from matching "Pay the registration fee".
// Thresholds come from the bank itself (build_index.py calibration) and can be overridden in Config.

const SEVERITY_WEIGHT = { high: 0.9, medium: 0.6, low: 0.3 };

function unit(values, dims) {
  const v = values.slice(0, dims);
  const n = Math.sqrt(v.reduce((s, x) => s + x * x, 0)) || 1;
  return v.map(x => x / n);
}

function dot(a, b) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}

function search(chunks, embeddings, bank, cfg) {
  const cal = { ...bank.calibration, ...Object.fromEntries(Object.entries(cfg || {}).filter(([, v]) => v !== "" && v != null)) };
  const hitFloor = Number(cal.hit_floor), strongFloor = Number(cal.strong_floor), margin = Number(cal.margin);
  const scam = bank.items.filter(it => it.kind === "scam");
  const honest = bank.items.filter(it => it.kind === "genuine");

  const perChunk = chunks.map((text, i) => {
    const v = unit(embeddings[i].values, bank.dims);
    let best = null, bestHonest = null;
    for (const it of scam) { const s = dot(v, it.vector); if (!best || s > best.sim) best = { sim: s, item: it }; }
    for (const it of honest) { const s = dot(v, it.vector); if (!bestHonest || s > bestHonest.sim) bestHonest = { sim: s, item: it }; }
    const m = best.sim - (bestHonest ? bestHonest.sim : 0);
    return {
      chunk: text, sim: best.sim, margin: m, pattern: best.item, honest: bestHonest ? bestHonest.item.text : "",
      hit: best.sim >= hitFloor && m >= margin,
      strong: best.sim >= strongFloor && m >= 2 * margin,
    };
  });

  // Strongest hit per category
  const byCategory = {};
  for (const c of perChunk.filter(c => c.hit)) {
    const cat = c.pattern.category;
    if (!byCategory[cat] || c.sim > byCategory[cat].sim) byCategory[cat] = c;
  }
  const categories = Object.values(byCategory).map(c => ({
    category: c.pattern.category,
    label: c.pattern.label,
    severity: c.pattern.severity,
    strong: c.strong,
    strength: Number(((SEVERITY_WEIGHT[c.pattern.severity] || 0.3) * (c.strong ? 1 : 0.6)).toFixed(3)),
    similarity: Number(c.sim.toFixed(3)),
    margin: Number(c.margin.toFixed(3)),
    chunk: c.chunk,
    matched_pattern: c.pattern.text,
  })).sort((a, b) => b.strength - a.strength);

  const vectorRisk = 1 - categories.reduce((p, c) => p * (1 - c.strength), 1);
  const nearest = perChunk.slice().sort((a, b) => b.sim - a.sim).slice(0, 3)
    .map(c => ({ chunk: c.chunk, pattern: c.pattern.text, similarity: Number(c.sim.toFixed(3)), margin: Number(c.margin.toFixed(3)) }));
  return {
    thresholds: { hit_floor: hitFloor, strong_floor: strongFloor, margin },
    chunks_checked: chunks.length,
    categories,
    vector_risk: Number(vectorRisk.toFixed(3)),
    nearest,     // shown even without a hit, so a reviewer can see how close the post came
  };
}

// Stage-1 gate: block without asking the LLM only on strong, high-severity evidence
function gate(stage1, signals) {
  const strongHigh = stage1.categories.filter(c => c.severity === "high" && c.strong);
  const upi = signals.find(s => s.code === "upi_id");
  const feeHit = stage1.categories.find(c => c.category === "upfront_fee");
  if (strongHigh.length) return { decision: "block", why: `Near-copy of a known scam: ${strongHigh.map(c => c.label).join(", ")}` };
  if (upi && feeHit) return { decision: "block", why: "Payment wording together with a UPI payment ID" };
  return { decision: "judge", why: "No conclusive match; sent to the LLM judge" };
}

function unpack(posts, batches, answers, bank, cfg) {
  const out = [];
  batches.forEach((b, bi) => {
    const ans = answers[bi] || {};
    // Gemini answers {embeddings:[{values}]}, Azure OpenAI answers {data:[{embedding, index}]}
    const embs = ans.embeddings || (ans.data || []).slice().sort((a, b) => a.index - b.index).map(d => ({ values: d.embedding }));
    for (const m of b.members) {
      const post = posts[m.idx];
      const mine = embs.slice(m.start, m.start + m.n);
      if (mine.length !== m.n) {
        // Embedding call failed: skip the vector stage, the LLM judge still runs and the reason says so
        const stage1 = { error: `Embedding failed (${ans.error ? JSON.stringify(ans.error).slice(0, 200) : "no vectors"})`,
                         categories: [], vector_risk: 0, nearest: [], chunks_checked: 0 };
        out.push({ ...post, stage1, gate: { decision: "judge", why: stage1.error } });
        continue;
      }
      const stage1 = search(post.chunks, mine, bank, { hit_floor: cfg.hitFloor, strong_floor: cfg.strongFloor, margin: cfg.margin });
      out.push({ ...post, stage1, gate: gate(stage1, post.signals) });
    }
  });
  return out;
}

// ==== n8n glue (below this line runs only inside n8n) ====
const posts = $('Link + contact signals').all().map(i => i.json);
const batches = $('Pack embedding mini-batches').all().map(i => i.json);
const answers = $input.all().map(i => i.json);
return unpack(posts, batches, answers, $('Fetch pattern bank').first().json, $('Config').first().json).map(json => ({ json }));
