// Stage 2a — "Pack judge mini-batches" (n8n Code node, runs once for ALL listings)
// Builds one LLM request per mini-batch of posts: rules, one worked example (one-shot), then
// up to BATCH posts with their stage-0/1 findings as leads to verify. The answer is a fixed
// JSON schema with one result per post id, and every quote must be copied word for word,
// because the next node throws away any quote it can't find in THAT post.
// 300 posts = ~38 calls instead of 300.

const BATCH = 8;

const CATEGORIES = ["upfront_fee", "task_scam", "data_harvest", "off_platform_contact",
  "too_good_to_be_true", "pressure", "training_sale", "mlm", "none"];

const SYSTEM = [
  "You review internship posts for an Indian student job board and estimate how likely each one is a scam.",
  "Judge ONLY from the post text given. Do not assume facts about the company that are not in the text.",
  "Scam signs: asking the candidate for any payment (registration, training, kit, certificate, deposit, 'refundable' money);",
  "paid online tasks (likes, reviews, Telegram tasks); asking for Aadhaar/PAN/bank details/OTP before selection;",
  "moving candidates to WhatsApp/Telegram/personal Gmail; 'no interview, everyone selected'; pay far above normal for no skills;",
  "deadline pressure to pay; a paid course or certificate sold as an internship; pay that depends on recruiting others.",
  "Not scam signs on their own: small or unknown company, short description, low stipend, remote work, a recruiter posting.",
  "A post that says it does NOT charge fees is a good sign, not a bad one.",
  "You get several posts, each starting with 'POST <id>'. Judge each one on its own and return exactly one result per post id.",
  "Every evidence quote must be copied EXACTLY from that same post (5 to 25 words). If there is no evidence, return an empty list.",
  "scam_probability: 0.0 = clearly genuine, 0.5 = cannot tell, 1.0 = clearly a scam. Be calibrated: most posts on job boards are genuine.",
  "The 'automated findings' come from keyword and similarity checks and can be wrong. Confirm or reject them from the text.",
].join("\n");

const EXAMPLE_POST = [
  "POST ex1",
  "Title: Data Science Intern",
  "Company: Brightpath Analytics",
  "Stipend: 25,000/month",
  "Text: Work on real projects in Python and ML. Selected candidates must pay a refundable security deposit of Rs 1,500 " +
    "for the internship kit. Contact HR on WhatsApp 98xxxxxx10 to get your offer letter today, only 5 seats left.",
  "Automated findings: upfront_fee (similarity 0.86) | Post asks candidates to use WhatsApp",
].join("\n");

const EXAMPLE_RESULT = {
  id: "ex1",
  scam_probability: 0.93,
  verdict: "scam",
  categories: ["upfront_fee", "off_platform_contact", "pressure"],
  evidence: [
    { quote: "Selected candidates must pay a refundable security deposit of Rs 1,500", why: "Genuine internships never charge a deposit." },
    { quote: "Contact HR on WhatsApp", why: "Moves hiring off the platform to an unverifiable chat." },
    { quote: "only 5 seats left", why: "Pressure to act before checking." },
  ],
  genuine_signs: ["Mentions Python and ML project work"],
  summary: "Asks for a refundable deposit and pushes candidates to WhatsApp with seat pressure: classic deposit scam.",
};
const EXAMPLE_ANSWER = { results: [EXAMPLE_RESULT] };

const RESULT_SCHEMA = {
  type: "OBJECT",
  properties: {
    id: { type: "STRING" },
    scam_probability: { type: "NUMBER" },
    verdict: { type: "STRING", enum: ["genuine", "suspicious", "scam"] },
    categories: { type: "ARRAY", items: { type: "STRING", enum: CATEGORIES } },
    evidence: {
      type: "ARRAY",
      items: { type: "OBJECT", properties: { quote: { type: "STRING" }, why: { type: "STRING" } }, required: ["quote", "why"] },
    },
    genuine_signs: { type: "ARRAY", items: { type: "STRING" } },
    summary: { type: "STRING" },
  },
  required: ["id", "scam_probability", "verdict", "categories", "evidence", "summary"],
};
const SCHEMA = { type: "OBJECT", properties: { results: { type: "ARRAY", items: RESULT_SCHEMA } }, required: ["results"] };

function findingsLine(item) {
  const parts = (item.stage1.categories || []).map(c => `${c.category} (similarity ${c.similarity}): "${c.chunk}"`);
  for (const s of item.signals || []) parts.push(s.label);
  return parts.length ? parts.join(" | ") : "none";
}

function postBlock(item) {
  const listing = item.listing;
  return [
    `POST ${item.id}`,
    `Title: ${listing.role_title}`,
    `Company: ${listing.company_name}`,
    `Stipend: ${listing.stipend || "not stated"}`,
    `Source: ${listing.source_platform}`,
    `Text: ${String(listing.description || "(no description was available)").slice(0, 2500)}`,
    `Automated findings: ${findingsLine(item)}`,
  ].join("\n");
}

function buildRequest(items) {
  return {
    systemInstruction: { parts: [{ text: SYSTEM }] },
    contents: [
      { role: "user", parts: [{ text: EXAMPLE_POST }] },
      { role: "model", parts: [{ text: JSON.stringify(EXAMPLE_ANSWER) }] },
      { role: "user", parts: [{ text: items.map(postBlock).join("\n\n---\n\n") }] },
    ],
    generationConfig: { temperature: 0, responseMimeType: "application/json", responseSchema: SCHEMA },
  };
}

function packJudge(items) {
  const out = [];
  for (let i = 0; i < items.length; i += BATCH) {
    const group = items.slice(i, i + BATCH);
    out.push({ posts: group, judgeRequest: buildRequest(group) });
  }
  return out;
}

// ==== n8n glue (below this line runs only inside n8n) ====
return packJudge($input.all().map(i => i.json)).map(json => ({ json }));
