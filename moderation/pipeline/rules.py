"""Stage 0: rules on the apply link and on contact details in the
post, then the post cut into short chunks for the vector search. No AI: every signal is a rule
a person can read and argue with."""
import re
from urllib.parse import urlparse

A = re.ASCII | re.IGNORECASE   # JavaScript's /i regexes treat \w and \b as ASCII

SHORTENERS = ["bit.ly", "tinyurl.com", "t.co", "cutt.ly", "rb.gy", "shorturl.at", "is.gd", "goo.gl",
              "tiny.cc", "rebrand.ly", "shorturl.com", "s.id"]
FORM_SITES = ["forms.gle", "docs.google.com/forms", "forms.office.com", "typeform.com", "jotform.com", "tally.so"]
CHAT_SITES = ["wa.me", "api.whatsapp.com", "chat.whatsapp.com", "t.me", "telegram.me"]
UPI_RE = re.compile(r"\b[\w.\-]{2,}@(okaxis|okhdfcbank|okicici|oksbi|ybl|ibl|axl|paytm|upi|apl|fbl|ptyes|ptsbi|ikwik|jupiteraxis)\b", A)
FREE_MAIL_RE = re.compile(r"\b[\w.+-]+@(gmail|yahoo|outlook|hotmail|rediffmail)\.com\b", A)
PHONE_RE = re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b", re.ASCII)
WHATSAPP_RE = re.compile(r"\bwhats\s?app\b", A)
TELEGRAM_RE = re.compile(r"\btelegram\b", A)


def host_of(url) -> str:
    try:
        h = (urlparse(str(url)).hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def matches_site(url, sites):
    u = re.sub(r"^https?://(www\.)?", "", str(url or "").lower())
    for s in sites:
        if u == s or u.startswith(s + "/") or u.startswith(s + "?") or host_of("https://" + u) == s:
            return s
    return None


def link_signals(listing: dict, link: dict) -> list:
    out = []
    urls = [u for u in [listing.get("apply_link"), *(link.get("chain") or []), link.get("final_url")] if u]
    for sites, code, label, weight in [
        (CHAT_SITES, "chat_link", "Apply link opens WhatsApp/Telegram instead of an application page", 0.35),
        (SHORTENERS, "short_link", "Apply link goes through a link shortener, hiding where it leads", 0.25),
        (FORM_SITES, "form_link", "Applications are collected on a generic form, not the portal or company site", 0.2),
    ]:
        hit = next((h for h in (matches_site(u, sites) for u in urls) if h), None)
        if hit:
            out.append({"code": code, "label": f"{label} ({hit})", "weight": weight})
    start, end = host_of(listing.get("apply_link")), link.get("final_domain") or host_of(link.get("final_url"))
    if start and end and start != end and not end.endswith("." + start) and not start.endswith("." + end):
        out.append({"code": "redirect", "label": f"Link redirects from {start} to {end}", "weight": 0.1})
    if link.get("link_state") == "bad_certificate":
        out.append({"code": "bad_cert", "label": "Apply page has a broken security certificate", "weight": 0.15})
    return out


def text_signals(listing: dict) -> list:
    text = f"{listing.get('role_title') or ''} {listing.get('description') or ''}"
    out = []
    upi = UPI_RE.search(text)
    if upi:
        out.append({"code": "upi_id", "label": f"Post contains a UPI payment ID ({upi.group(0)})", "weight": 0.5})
    mail = FREE_MAIL_RE.search(text)
    if mail:
        out.append({"code": "free_mail", "label": f"Recruiter uses a free email address ({mail.group(0)})", "weight": 0.15})
    if WHATSAPP_RE.search(text):
        out.append({"code": "whatsapp", "label": "Post asks candidates to use WhatsApp", "weight": 0.15})
    if TELEGRAM_RE.search(text):
        out.append({"code": "telegram", "label": "Post mentions Telegram", "weight": 0.2})
    if PHONE_RE.search(text):
        out.append({"code": "phone", "label": "Personal phone number in the post", "weight": 0.1})
    flags = [f.strip() for f in str(listing.get("trust_flags") or "").split(";") if f.strip()]
    if flags:
        out.append({"code": "scraper_flags", "label": f"Scraper warnings: {'; '.join(flags)}",
                    "weight": min(0.3, 0.07 * len(flags))})
    return out


def combine(signals: list) -> float:
    """Independent signals: 1 - (1-w1)(1-w2)..."""
    p = 1.0
    for s in signals:
        p *= 1 - s["weight"]
    return min(0.95, 1 - p)


SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+|\s*[•●▪]\s*|\s+-\s+(?=[A-Z])")


def chunk_text(listing: dict, max_chunks: int = 12) -> list:
    head = f"{listing.get('role_title') or ''} at {listing.get('company_name') or ''}. Stipend: {listing.get('stipend') or 'not stated'}."
    body = re.sub(r"\s+", " ", str(listing.get("description") or "")).strip()
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(body) if s and s.strip()]
    chunks, carry = [head], ""
    for s in sentences:
        words = (carry + " " + s if carry else s).split(" ")
        carry = ""
        if len(words) < 5:
            carry = " ".join(words)
            continue
        if len(words) <= 45:
            chunks.append(" ".join(words))
            continue
        i = 0
        while i < len(words):            # long sentence: 35-word windows, 10 overlap
            chunks.append(" ".join(words[i:i + 35]))
            if i + 35 >= len(words):
                break
            i += 25
    if carry:
        chunks.append(carry)
    return chunks[:max_chunks]


def analyse(listing: dict, link: dict | None) -> dict:
    link = link or {}
    signals = link_signals(listing, link) + text_signals(listing)
    return {
        "id": listing.get("id"),
        "link": {"state": link.get("link_state") or "unknown", "http_status": link.get("http_status"),
                 "final_domain": link.get("final_domain") or "", "chain": link.get("chain") or []},
        "signals": signals,
        "signal_risk": round(combine(signals), 3),
        "chunks": chunk_text(listing),
        "listing": listing,
    }
