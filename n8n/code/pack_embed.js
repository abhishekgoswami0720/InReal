// "Pack embedding mini-batches" (n8n Code node, runs once for ALL listings)
// Instead of one Gemini call per post, the chunks of many posts go into one
// batchEmbedContents call (up to MAX_TEXTS texts). 300 posts = ~40 calls instead of 300.
// Each batch remembers which post owns which slice of the answer.

const MAX_TEXTS = 90;

function embedItem(text, bank) {
  const item = { model: `models/${bank.model}`, content: { parts: [{ text }] } };
  if (bank.request_style === "config") item.embedContentConfig = { taskType: bank.task_type, outputDimensionality: bank.dims };
  if (bank.request_style === "legacy") { item.taskType = bank.task_type; item.outputDimensionality = bank.dims; }
  return item;
}

function packEmbeds(posts, bank) {
  const batches = [];
  let cur = null;
  posts.forEach((p, idx) => {
    if (!cur || cur.texts + p.chunks.length > MAX_TEXTS) {
      cur = { members: [], texts: 0, requests: [] };
      batches.push(cur);
    }
    cur.members.push({ idx, start: cur.texts, n: p.chunks.length });
    for (const c of p.chunks) cur.requests.push(embedItem(c, bank));
    cur.texts += p.chunks.length;
  });
  return batches.map(b => ({ members: b.members, embedRequest: { requests: b.requests } }));
}

// ==== n8n glue (below this line runs only inside n8n) ====
const bank = $('Fetch pattern bank').first().json;
return packEmbeds($input.all().map(i => i.json), bank).map(json => ({ json }));
