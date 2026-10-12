# Scam moderation pipeline (n8n)

Every new listing the scraper saves is checked by an n8n workflow before you trust it.
The verdict shows on its dashboard card: **passed**, **needs a human look**, **likely scam**
(hidden by default), or **link closed**.

```
scraper saves listings ──► Flask app (internships.csv)
                               │  webhook after each scrape, or every 30 min
                               ▼
n8n ─ Config ─ Fetch pattern bank ─ Fetch pending listings
        │
        ├─ Resolve apply link ......... Flask follows redirects, reads status / "applications closed"
        │      └─ dead or closed? ───► Expired listing ─────────────────────────────┐
        ├─ Link + contact signals ..... rules: shortener, WhatsApp/Telegram link, Google Form,
        │                               UPI ID, free-mail recruiter, phone number, scraper warnings
        ├─ Embed chunks (Gemini) ...... every sentence of the post → vector
        ├─ Vector search .............. cosine vs ~50 scam phrases AND ~15 honest phrases
        │      └─ near-copy of a high-risk scam? ─► Blocked at stage 1 ─────────────┤
        ├─ Build one-shot judge request  one worked example + the post + stage-0/1 leads
        ├─ LLM judge (one call) ....... fixed JSON schema: probability, categories, exact quotes
        └─ Verify evidence + fuse ..... quotes checked against the real post, scores combined ──┤
                                                                                     Save verdict
```

## Why this is not "a wrapper around an LLM"

| Step | What it decides on its own |
|---|---|
| Link check | Dead (404/410) or "no longer accepting applications" → expired, no AI involved |
| Rules | Shorteners, chat links, forms, UPI IDs, free-mail, phone numbers: each has a fixed weight |
| Vector search | Blocks near-copies of fee / task / ID-theft scams **without calling the LLM**. A sentence only counts when it is closer to a scam phrase than to the nearest honest phrase, so "we do **not** charge any fee" does not match "pay the registration fee" |
| LLM judge | One call per post. Must quote the post word for word |
| Verify + fuse | Throws away quotes that are not in the post, and quotes that say the opposite ("no fee"). A high probability with no surviving quote is pulled back to ~0.5. Final risk = 0.6 × LLM + 0.25 × vector + 0.15 × rules, so **the LLM alone can only reach "needs a human look", never "blocked"**. If the LLM and the vector search disagree by 0.6 or more, a person decides |

## Setup on the laptop (one time)

1. **Pull and add your key**
   ```
   git pull
   copy .env.example .env
   ```
   Put your Gemini key in `.env` (`GEMINI_API_KEY=...`). Never commit `.env`.

2. **Build the scam-phrase index** (needs the key, ~10 seconds)
   ```
   python -m moderation.build_index
   ```
   It prints the thresholds it measured, e.g. `hit_floor`, `strong_floor`, `margin`.

3. **Start n8n.** n8n 2.x needs **Node.js 24 or newer** (`node -v`).
   ```
   npx n8n
   ```
   Or with Docker: `docker run -it --rm -p 5678:5678 docker.n8n.io/n8nio/n8n`. With Docker, change
   `flaskBase` in the **Config** node to `http://host.docker.internal:5000`.

4. Open http://localhost:5678, create the local owner account, then
   **Create workflow → ⋯ → Import from file → `n8n/inreal_moderation.json`**.

5. **Gemini credential.** Open the node **Embed chunks (Gemini)** → Credential → *Create new* →
   type **Header Auth**: Name `x-goog-api-key`, Value = your Gemini key. Save it as `Gemini API key`.
   Select the same credential in **LLM judge (Gemini, one call)**.

6. Start the app (`python app.py`), then in n8n click **Execute workflow**. Up to 40 pending listings
   are checked per run; refresh the dashboard to see the verdicts.

7. **Automatic runs:** click **Publish** (older n8n: the *Active* switch). From then on the workflow runs
   every 30 minutes, and after every scrape started from the dashboard, because `.env` has
   `INREAL_N8N_WEBHOOK=http://localhost:5678/webhook/inreal-moderate`. Restart `python app.py` after editing `.env`.

## Tuning

All knobs are in the **Config** node:

| Field | Default | Meaning |
|---|---|---|
| `judgeModel` | `gemini-3.5-flash-lite` | Any Gemini model that supports JSON output |
| `batchLimit` | 40 | Listings per run (the judge waits 4 s between calls to stay inside free-tier limits) |
| `blockAt` / `reviewAt` | 0.7 / 0.4 | Risk needed for "likely scam" / "needs a human look" |
| `hitFloor`, `strongFloor`, `margin` | empty | Empty = use the thresholds `build_index` measured. Raise them if honest posts get vector hits |

**New scam seen?** Add its wording to `moderation/scam_patterns.json` (and, if needed, the honest
version to `genuine`), then run `python -m moderation.build_index` again. No n8n change is needed.

**Changing a Code node:** edit the file in `n8n/code/`, run `python n8n/build_workflow.py`, and import
the workflow again. The same files are tested by `tests/test_moderation.py`.

## Known limits

- The thresholds are measured on the phrase bank, not on labelled real posts. Check the first runs and
  adjust `margin` if needed.
- Rows saved before 12 Oct 07:45 have no description stored, so they are judged on title, company and
  stipend only. The next scrape of that site fills the description and the post is checked again.
- Naukri, Foundit and LinkedIn refuse scripts (`portal_blocks_bots`). That is **not** treated as a scam
  signal; only the scraped text is judged for those.
- The apply page itself is only used for redirects and "closed" wording. Its text is not judged, because
  portal pages carry their own adverts (Internshala advertises paid trainings on every page).

## Tested

`pytest` runs the moderation API, the link check and every Code node's logic (Node.js needed for the
last part). The whole workflow was also imported into n8n 2.42.6 and run end to end against a fake
Gemini server: 40 listings, the fee post and the Telegram task post were blocked at stage 1, a made-up
LLM quote was discounted, and the webhook trigger from the app worked.
