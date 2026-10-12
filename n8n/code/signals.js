// Stage 0 — "Link + contact signals" (n8n Code node, runs once for each listing)
// Deterministic checks on the apply link (where it redirects) and on contact details in the
// post, then cuts the post into short chunks (embedded later in shared mini-batches).
// No AI here: every signal is a rule a human can read and argue with.

const SHORTENERS = ["bit.ly", "tinyurl.com", "t.co", "cutt.ly", "rb.gy", "shorturl.at", "is.gd", "goo.gl",
  "tiny.cc", "rebrand.ly", "shorturl.com", "s.id"];
const FORM_SITES = ["forms.gle", "docs.google.com/forms", "forms.office.com", "typeform.com", "jotform.com", "tally.so"];
const CHAT_SITES = ["wa.me", "api.whatsapp.com", "chat.whatsapp.com", "t.me", "telegram.me"];
const UPI_RE = /\b[\w.\-]{2,}@(okaxis|okhdfcbank|okicici|oksbi|ybl|ibl|axl|paytm|upi|apl|fbl|ptyes|ptsbi|ikwik|jupiteraxis)\b/i;
const FREE_MAIL_RE = /\b[\w.+-]+@(gmail|yahoo|outlook|hotmail|rediffmail)\.com\b/i;
const PHONE_RE = /(?:\+91[\s-]?)?\b[6-9]\d{9}\b/;
const WHATSAPP_RE = /\bwhats\s?app\b/i;
const TELEGRAM_RE = /\btelegram\b/i;

function hostOf(url) {
  try { return new URL(url).hostname.toLowerCase().replace(/^www\./, ""); } catch (e) { return ""; }
}

function matchesSite(url, sites) {
  const u = String(url || "").toLowerCase().replace(/^https?:\/\/(www\.)?/, "");
  return sites.find(s => u === s || u.startsWith(s + "/") || u.startsWith(s + "?") || hostOf("https://" + u) === s) || null;
}

function linkSignals(listing, link) {
  const out = [];
  const urls = [listing.apply_link, ...(link.chain || []), link.final_url].filter(Boolean);
  for (const [sites, code, label, weight] of [
    [CHAT_SITES, "chat_link", "Apply link opens WhatsApp/Telegram instead of an application page", 0.35],
    [SHORTENERS, "short_link", "Apply link goes through a link shortener, hiding where it leads", 0.25],
    [FORM_SITES, "form_link", "Applications are collected on a generic form, not the portal or company site", 0.2],
  ]) {
    const hit = urls.map(u => matchesSite(u, sites)).find(Boolean);
    if (hit) out.push({ code, label: `${label} (${hit})`, weight });
  }
  const start = hostOf(listing.apply_link), end = link.final_domain || hostOf(link.final_url);
  if (start && end && start !== end && !end.endsWith("." + start) && !start.endsWith("." + end)) {
    out.push({ code: "redirect", label: `Link redirects from ${start} to ${end}`, weight: 0.1 });
  }
  if (link.link_state === "bad_certificate") {
    out.push({ code: "bad_cert", label: "Apply page has a broken security certificate", weight: 0.15 });
  }
  return out;
}

function textSignals(listing) {
  const text = `${listing.role_title || ""} ${listing.description || ""}`;
  const out = [];
  const upi = text.match(UPI_RE);
  if (upi) out.push({ code: "upi_id", label: `Post contains a UPI payment ID (${upi[0]})`, weight: 0.5 });
  const mail = text.match(FREE_MAIL_RE);
  if (mail) out.push({ code: "free_mail", label: `Recruiter uses a free email address (${mail[0]})`, weight: 0.15 });
  if (WHATSAPP_RE.test(text)) out.push({ code: "whatsapp", label: "Post asks candidates to use WhatsApp", weight: 0.15 });
  if (TELEGRAM_RE.test(text)) out.push({ code: "telegram", label: "Post mentions Telegram", weight: 0.2 });
  if (PHONE_RE.test(text)) out.push({ code: "phone", label: "Personal phone number in the post", weight: 0.1 });
  const flags = String(listing.trust_flags || "").split(";").map(f => f.trim()).filter(Boolean);
  if (flags.length) {
    out.push({ code: "scraper_flags", label: `Scraper warnings: ${flags.join("; ")}`, weight: Math.min(0.3, 0.07 * flags.length) });
  }
  return out;
}

// Combines independent signals: 1 - (1-w1)(1-w2)...
function combine(signals) {
  return Math.min(0.95, 1 - signals.reduce((p, s) => p * (1 - s.weight), 1));
}

function chunkText(listing, maxChunks = 12) {
  const head = `${listing.role_title || ""} at ${listing.company_name || ""}. Stipend: ${listing.stipend || "not stated"}.`;
  const body = String(listing.description || "").replace(/\s+/g, " ").trim();
  const sentences = body.split(/(?<=[.!?।])\s+|\s*[•●▪]\s*|\s+-\s+(?=[A-Z])/).map(s => s.trim()).filter(Boolean);
  const chunks = [head];
  let carry = "";
  for (const s of sentences) {
    const words = (carry ? carry + " " + s : s).split(" ");
    carry = "";
    if (words.length < 5) { carry = words.join(" "); continue; }
    if (words.length <= 45) { chunks.push(words.join(" ")); continue; }
    for (let i = 0; i < words.length; i += 25) {        // long sentence: 35-word windows, 10 overlap
      chunks.push(words.slice(i, i + 35).join(" "));
      if (i + 35 >= words.length) break;
    }
  }
  if (carry) chunks.push(carry);
  return chunks.slice(0, maxChunks);
}

function embedRequest(chunks, bank) {
  const model = `models/${bank.model}`;
  return {
    requests: chunks.map(text => {
      const item = { model, content: { parts: [{ text }] } };
      if (bank.request_style === "config") item.embedContentConfig = { taskType: bank.task_type, outputDimensionality: bank.dims };
      if (bank.request_style === "legacy") { item.taskType = bank.task_type; item.outputDimensionality = bank.dims; }
      return item;
    }),
  };
}

function analyse(listing, link, bank) {
  const signals = [...linkSignals(listing, link || {}), ...textSignals(listing)];
  const chunks = chunkText(listing);
  return {
    id: listing.id,
    link: { state: (link || {}).link_state || "unknown", http_status: (link || {}).http_status || null,
            final_domain: (link || {}).final_domain || "", chain: (link || {}).chain || [] },
    signals,
    signal_risk: Number(combine(signals).toFixed(3)),
    chunks,
    listing,   // carried along so later nodes don't depend on item pairing across mini-batches
  };
}

// ==== n8n glue (below this line runs only inside n8n) ====
const listing = $('Fetch pending listings').item.json;
const bank = $('Fetch pattern bank').first().json;
return { json: analyse(listing, $json, bank) };
