"""Stage 2: the AI judge (gpt-4o on Azure, or Gemini).

One request per mini-batch of posts: rules, one worked example, then the posts with their stage-0/1
findings as leads to check. The answer follows a fixed JSON schema with one result per post id,
and every quote must be copied word for word, because fuse.py throws away any quote it can't find
in that post. The prompt is pinned by tests/test_pipeline.py (any change to it shows up there).
"""
import json
import os
import re
import time

import requests

from moderation.env import load_env

BATCH = 5
CATEGORIES = ['upfront_fee',
 'task_scam',
 'data_harvest',
 'off_platform_contact',
 'too_good_to_be_true',
 'pressure',
 'training_sale',
 'mlm',
 'none']

SYSTEM = ('You review internship posts for an Indian student job board and estimate how likely each one is a scam.\n'
 'Judge ONLY from the post text given. Do not assume facts about the company that are not in the text.\n'
 'Scam signs: asking the candidate for any payment (registration, training, kit, certificate, deposit, '
 "'refundable' money);\n"
 'paid online tasks (likes, reviews, Telegram tasks); asking for Aadhaar/PAN/bank details/OTP before '
 'selection;\n'
 "moving candidates to WhatsApp/Telegram/personal Gmail; 'no interview, everyone selected'; pay far above "
 'normal for no skills;\n'
 'deadline pressure to pay; a paid course or certificate sold as an internship; pay that depends on '
 'recruiting others.\n'
 'Not scam signs on their own: small or unknown company, short description, low stipend, remote work, a '
 'recruiter posting.\n'
 'A post that says it does NOT charge fees is a good sign, not a bad one.\n'
 "You get several posts, each starting with 'POST <id>'. Judge each one on its own and return exactly one "
 'result per post id.\n'
 'Every evidence quote must be copied EXACTLY from that same post (5 to 25 words). If there is no evidence, '
 'return an empty list.\n'
 'scam_probability: 0.0 = clearly genuine, 0.5 = cannot tell, 1.0 = clearly a scam. Be calibrated: most '
 'posts on job boards are genuine.\n'
 "The 'automated findings' come from keyword and similarity checks and can be wrong. Confirm or reject them "
 'from the text.')

EXAMPLE_POST = ('POST ex1\n'
 'Title: Data Science Intern\n'
 'Company: Brightpath Analytics\n'
 'Stipend: 25,000/month\n'
 'Text: Work on real projects in Python and ML. Selected candidates must pay a refundable security deposit '
 'of Rs 1,500 for the internship kit. Contact HR on WhatsApp 98xxxxxx10 to get your offer letter today, only '
 '5 seats left.\n'
 'Automated findings: upfront_fee (similarity 0.86) | Post asks candidates to use WhatsApp')

EXAMPLE_ANSWER = {'results': [{'id': 'ex1',
              'scam_probability': 0.93,
              'verdict': 'scam',
              'categories': ['upfront_fee', 'off_platform_contact', 'pressure'],
              'evidence': [{'quote': 'Selected candidates must pay a refundable security deposit of Rs 1,500',
                            'why': 'Genuine internships never charge a deposit.'},
                           {'quote': 'Contact HR on WhatsApp',
                            'why': 'Moves hiring off the platform to an unverifiable chat.'},
                           {'quote': 'only 5 seats left', 'why': 'Pressure to act before checking.'}],
              'genuine_signs': ['Mentions Python and ML project work'],
              'summary': 'Asks for a refundable deposit and pushes candidates to WhatsApp with seat '
                         'pressure: classic deposit scam.'}]}

SCHEMA = {'type': 'OBJECT',
 'properties': {'results': {'type': 'ARRAY',
                            'items': {'type': 'OBJECT',
                                      'properties': {'id': {'type': 'STRING'},
                                                     'scam_probability': {'type': 'NUMBER'},
                                                     'verdict': {'type': 'STRING',
                                                                 'enum': ['genuine', 'suspicious', 'scam']},
                                                     'categories': {'type': 'ARRAY',
                                                                    'items': {'type': 'STRING',
                                                                              'enum': ['upfront_fee',
                                                                                       'task_scam',
                                                                                       'data_harvest',
                                                                                       'off_platform_contact',
                                                                                       'too_good_to_be_true',
                                                                                       'pressure',
                                                                                       'training_sale',
                                                                                       'mlm',
                                                                                       'none']}},
                                                     'evidence': {'type': 'ARRAY',
                                                                  'items': {'type': 'OBJECT',
                                                                            'properties': {'quote': {'type': 'STRING'},
                                                                                           'why': {'type': 'STRING'}},
                                                                            'required': ['quote', 'why']}},
                                                     'genuine_signs': {'type': 'ARRAY',
                                                                       'items': {'type': 'STRING'}},
                                                     'summary': {'type': 'STRING'}},
                                      'required': ['id',
                                                   'scam_probability',
                                                   'verdict',
                                                   'categories',
                                                   'evidence',
                                                   'summary']}}},
 'required': ['results']}

# The judge reads the first HEAD characters of a post. Further down, only lines about money,
# contact or documents are added (up to TAIL characters), so a fee hidden at the end of a long
# post is still seen without doubling the tokens of every call.
HEAD, TAIL = 1800, 900
RISKY_LINE = re.compile(r'(₹|\\brs\\.?\\s?\\d|\\binr\\b|fee|fees|pay|payment|paid|deposit|refund|charge|purchase|buy|kit|registration|register|enrol|enroll|course|training|certificate|whatsapp|telegram|gmail|yahoo|aadhaar|aadhar|\\bpan\\b|bank|otp|upi|wallet|commission|incentive|recruit|refer|seat|slot|limited|urgent|immediately)', re.IGNORECASE | re.ASCII)


def findings_line(item: dict) -> str:
    parts = [f'{c["category"]} (similarity {_num(c["similarity"])}): "{c["chunk"]}"' for c in item["stage1"].get("categories") or []]
    parts += [s["label"] for s in item.get("signals") or []]
    return " | ".join(parts) if parts else "none"


def _num(x) -> str:
    """Numbers written the way JavaScript writes them (0.86, 1, not 1.0)."""
    f = float(x)
    return str(int(f)) if f == int(f) else repr(f)


def post_text(description) -> str:
    text = str(description or "")
    if len(text) <= HEAD:
        return text or "(no description was available)"
    later, used = [], 0
    for line in re.split(r"\n|(?<=[.!?])\s+", text[HEAD:]):
        line = line.strip()
        if line and RISKY_LINE.search(line) and used + len(line) <= TAIL:
            later.append(line)
            used += len(line)
    return text[:HEAD] + " [...]" + ("\nLater in the post (lines about money, contact or documents):\n" + "\n".join(later) if later else "")


# A post is written by whoever posted it. Several posts go to the AI in one message, so a post whose
# text starts a line with "POST <id>" or "Automated findings:" could pretend to be another post or
# fake our findings. Such lines get a "» " in front; one-line fields lose their line breaks.
FORGED_LINE = re.compile(r"(^|\n)[ \t]*(?=POST[ \t]|-{3}|(?:Title|Company|Stipend|Source|Text|Automated findings):)", re.I)


def fence(text) -> str:
    return FORGED_LINE.sub(lambda m: m.group(1) + "» ", str(text))


def one_line(value) -> str:
    return re.sub(r"[\r\n]+", " ", str(value))


def post_block(item: dict) -> str:
    listing = item["listing"]
    return "\n".join([
        f"POST {item['id']}",
        f"Title: {one_line(listing.get('role_title'))}",
        f"Company: {one_line(listing.get('company_name'))}",
        f"Stipend: {one_line(listing.get('stipend') or 'not stated')}",
        f"Source: {one_line(listing.get('source_platform'))}",
        f"Text: {fence(post_text(listing.get('description')))}",
        f"Automated findings: {findings_line(item)}",
    ])


def json_schema(t: dict) -> dict:
    """Gemini's OpenAPI-style schema -> strict JSON Schema for Azure OpenAI."""
    if t["type"] == "OBJECT":
        props = {k: json_schema(v) for k, v in t["properties"].items()}
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    if t["type"] == "ARRAY":
        return {"type": "array", "items": json_schema(t["items"])}
    out = {"type": t["type"].lower()}
    if "enum" in t:
        out["enum"] = t["enum"]
    return out


def _js_json(x) -> str:
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))


def build_request(items: list, provider: str = "azure") -> dict:
    posts = "\n\n---\n\n".join(post_block(i) for i in items)
    if provider == "azure":
        return {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": EXAMPLE_POST},
                {"role": "assistant", "content": _js_json(EXAMPLE_ANSWER)},
                {"role": "user", "content": posts},
            ],
            "temperature": 0,
            "max_tokens": 4000,
            "response_format": {"type": "json_schema", "json_schema": {"name": "scam_verdicts", "strict": True, "schema": json_schema(SCHEMA)}},
        }
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [
            {"role": "user", "parts": [{"text": EXAMPLE_POST}]},
            {"role": "model", "parts": [{"text": _js_json(EXAMPLE_ANSWER)}]},
            {"role": "user", "parts": [{"text": posts}]},
        ],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }


def pack(items: list, provider: str = "azure", size: int = BATCH) -> list:
    return [{"posts": items[i:i + size], "judgeRequest": build_request(items[i:i + size], provider)}
            for i in range(0, len(items), size)]


def provider() -> str:
    load_env()
    return "gemini" if os.environ.get("JUDGE_PROVIDER", "azure").strip().lower() == "gemini" else "azure"


def call(request: dict, timeout: float = 60.0) -> dict:
    """Sends one judge request; returns the API's answer or {"error": ...} (never raises)."""
    load_env()
    env = os.environ.get
    try:
        if provider() == "azure":
            url = (env("AZURE_OPENAI_JUDGE_URL") or "").strip()
            key = (env("AZURE_OPENAI_JUDGE_KEY") or env("AZURE_OPENAI_KEY") or "").strip()
            if not url or not key:
                return {"error": {"message": "AZURE_OPENAI_GPT4O_ENDPOINT / _KEY missing in .env"}}
            headers = {"api-key": key}
        else:
            base = (env("GEMINI_API_BASE") or "https://generativelanguage.googleapis.com").rstrip("/")
            url = f"{base}/v1beta/models/{env('JUDGE_MODEL') or 'gemini-3.5-flash-lite'}:generateContent"
            headers = {"x-goog-api-key": (env("GEMINI_API_KEY") or "").strip()}
        for attempt in range(3):
            r = requests.post(url, json=request, headers=headers, timeout=timeout)
            if r.status_code == 429 and attempt < 2:      # token limit: wait as Azure asks, then again
                time.sleep(min(20.0, float(r.headers.get("retry-after") or 4 * (attempt + 1))))
                continue
            break
        if r.status_code != 200:
            return {"error": {"code": r.status_code, "message": r.text[:200]}}
        return r.json()
    except requests.RequestException as e:
        return {"error": {"message": type(e).__name__}}
