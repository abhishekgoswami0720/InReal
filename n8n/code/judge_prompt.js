// Stage 2a — "Build one-shot judge request" (n8n Code node, runs once for each listing)
// Builds ONE request for the LLM: rules, one worked example (one-shot), then the listing with
// the stage-0/1 findings as leads to verify. The answer must follow a fixed JSON schema and
// quote the post word for word, because the next node throws away any quote it can't find.

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
  "Every evidence quote must be copied EXACTLY from the post (5 to 25 words). If there is no evidence, return an empty list.",
  "scam_probability: 0.0 = clearly genuine, 0.5 = cannot tell, 1.0 = clearly a scam. Be calibrated: most posts on job boards are genuine.",
  "The 'automated findings' come from keyword and similarity checks and can be wrong. Confirm or reject them from the text.",
].join("\n");

const EXAMPLE_POST = [
  "Title: Data Science Intern",
  "Company: Brightpath Analytics",
  "Stipend: 25,000/month",
  "Text: Work on real projects in Python and ML. Selected candidates must pay a refundable security deposit of Rs 1,500 " +
    "for the internship kit. Contact HR on WhatsApp 98xxxxxx10 to get your offer letter today, only 5 seats left.",
  "Automated findings: upfront_fee (similarity 0.86) | Post asks candidates to use WhatsApp",
].join("\n");

const EXAMPLE_ANSWER = {
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

const SCHEMA = {
  type: "OBJECT",
  properties: {
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
  required: ["scam_probability", "verdict", "categories", "evidence", "summary"],
};

function findingsLine(item) {
  const parts = (item.stage1.categories || []).map(c => `${c.category} (similarity ${c.similarity}): "${c.chunk}"`);
  for (const s of item.signals || []) parts.push(s.label);
  return parts.length ? parts.join(" | ") : "none";
}

function buildRequest(listing, item) {
  const post = [
    `Title: ${listing.role_title}`,
    `Company: ${listing.company_name}`,
    `Stipend: ${listing.stipend || "not stated"}`,
    `Source: ${listing.source_platform}`,
    `Text: ${String(listing.description || "(no description was available)").slice(0, 3000)}`,
    `Automated findings: ${findingsLine(item)}`,
  ].join("\n");
  return {
    systemInstruction: { parts: [{ text: SYSTEM }] },
    contents: [
      { role: "user", parts: [{ text: EXAMPLE_POST }] },
      { role: "model", parts: [{ text: JSON.stringify(EXAMPLE_ANSWER) }] },
      { role: "user", parts: [{ text: post }] },
    ],
    generationConfig: { temperature: 0, responseMimeType: "application/json", responseSchema: SCHEMA },
  };
}

// ==== n8n glue (below this line runs only inside n8n) ====
const listing = $('Fetch pending listings').item.json;
return { json: { ...$json, judgeRequest: buildRequest(listing, $json) } };
