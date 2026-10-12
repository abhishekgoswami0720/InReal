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


## Speed: overlapping runs and mini-batches (12 Oct)

- The scraper calls the webhook after **each site** is saved, not after the whole run, so n8n checks
  Internshala while Naukri is still being scraped.
- Each run **claims** up to 120 listings (`pending?claim=1` marks them "checking"), so two runs that overlap
  never check the same listing. A claim that is not finished in 15 minutes is released.
- Embeddings: chunks of many posts go into one `batchEmbedContents` call (≤90 texts). LLM judge: 8 posts per
  call, one result per post id, then split and verified post by post.
- Dashboard shows **Verified only** by default and reloads as verdicts arrive; the header shows how many are
  being checked or waiting.
- Measured with a fake Gemini: 106 listings, two overlapping runs, all judged in 25 s. With the real free tier
  the waits between calls (2 s embed, 4 s judge) dominate: about 1.5 minutes per 100 listings (was ~9).


## Embeddings on Azure OpenAI (12 Oct, Gemini free tier kept returning 429)

1. In `.env`: `EMBED_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_EMBED_DEPLOYMENT`, `AZURE_OPENAI_KEY`
   (see `.env.example`). The endpoint can be the bare resource URL or the full URL the portal shows.
2. `python -m moderation.build_index` — rebuilds the phrase vectors with Azure (vectors from two different models
   can't be compared, so this is required after switching). The index stores the Azure URL, never the key.
3. In n8n, node **Embed chunks** → credential **Header Auth** named `Embedding API key`: Name `api-key`, Value = the Azure key.
   The LLM judge keeps its own `Gemini API key` credential.
4. Start n8n with `N8N_CONCURRENCY_PRODUCTION_LIMIT=1` so webhook runs queue one after another instead of
   hitting the APIs together (PowerShell: `$env:N8N_CONCURRENCY_PRODUCTION_LIMIT="1"; npx n8n`).
   Nothing is lost: listings a run didn't claim are taken by the next one.

`text-embedding-3-small` deployment limits seen on the portal: 150,000 tokens and 900 requests per minute, so the
embed node now waits only 0.3 s between calls (one call carries up to 90 sentences).


## LLM judge on Azure OpenAI gpt-4o (12 Oct)

- **Config** node: `judgeProvider` = `azure`, `azureJudgeUrl` = the gpt-4o chat-completions URL from the portal.
  Set `judgeProvider` to `gemini` to go back (then give the judge node the Gemini credential).
- Both Azure nodes (**Embed chunks**, **LLM judge (8 posts per call)**) use one Header Auth credential
  `Azure OpenAI key` (Name `api-key`).
- The judge sends the same rules + one worked example + 8 posts, and asks for a strict JSON schema
  (`response_format: json_schema, strict: true`). Content-filter blocks and refusals become "LLM judge unavailable".
- gpt-4o deployment limits: 50,000 tokens and 300 requests per minute; one 8-post call is ~6–7k tokens, so calls
  are 8 s apart (≈60 posts a minute). Post text sent to the judge is capped at 1,800 characters.
- If both AI checks fail for a post (APIs down / out of quota) it is **not** approved on rules alone; it goes back
  to the queue for the next run.
- Live check of both deployments from the laptop: `python -m moderation.check_azure`.
- Tested in n8n 2.42.6 with fake Azure servers: 106 listings, 2 runs queued one after another, 31 s.
