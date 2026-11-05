"""Company logos on the cards (1 Nov 2026).

Where a logo comes from: only the logo the source site shows with the post (Internshala, Unstop,
LinkedIn, ...), found by the scrapers (sites/_common.logo_in_card / logo_in_json) and stored in the
`company_logo` column. It is never looked up by company name: a fake "Google internship" must not
get Google's real logo. The one exception is the big-tech career sites, where the post comes from
the company's own site, so its own icon is safe (OWN_SITES).

How it is shown: the laptop downloads each logo once, in the background, through safe_http (no
private addresses), checks it is a real picture, shrinks it to 128 px and saves a WebP copy in
static/logos/. The page loads that copy from InReal itself, so the viewer's browser never contacts
the other site (no IP leak, no expiring LinkedIn links). Until the copy exists, or when there is no
logo, the card shows the company's initials.
"""
import hashlib
import io
import queue
import threading
from pathlib import Path

from loguru import logger

LOGO_DIR = Path(__file__).parent / "static" / "logos"
WEB_PATH = "/static/logos/"
SIZE = 128
MAX_BYTES = 600_000         # a logo bigger than this is not a logo
MAX_PIXELS = 4096 * 4096    # refuses "decompression bombs" before decoding (2 Nov: 4 MP refused a real 2420 px AICTE logo)
TIMEOUT_S = 8

# Posts from a company's own career site: that company's icon (source_platform -> its domain)
OWN_SITES = {
    "Microsoft Careers": "microsoft.com", "Google Careers": "google.com", "Apple Jobs": "apple.com",
    "Meta Careers": "meta.com", "Amazon Jobs": "amazon.jobs", "NVIDIA Careers": "nvidia.com",
    "Intel Careers": "intel.com", "Adobe Careers": "adobe.com", "Salesforce Careers": "salesforce.com",
}
ICON_SERVICE = "https://www.google.com/s2/favicons?sz=128&domain={}"

_queue: "queue.Queue[str]" = queue.Queue(maxsize=2000)
_failed: set = set()
_lock = threading.Lock()
_worker = {"thread": None}


def source_logo(row: dict) -> str:
    """The logo link for one post: what its site showed, or its own career site's icon."""
    url = str(row.get("company_logo") or "").strip()
    if url and "AICTE" in str(row.get("source_platform") or ""):
        from sites.government import fix_logo_url
        url = fix_logo_url(url)   # posts saved before 2 Nov kept the API's internal address
    if url:
        return url
    domain = OWN_SITES.get(str(row.get("source_platform") or ""))
    return ICON_SERVICE.format(domain) if domain else ""


def _name(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20] + ".webp"


def cached(url: str) -> str:
    """'/static/logos/<file>.webp' when the copy exists, else ''."""
    if not url:
        return ""
    name = _name(url)
    return WEB_PATH + name if (LOGO_DIR / name).exists() else ""


def shrink(data: bytes) -> bytes:
    """A real picture -> 128 px WebP. Raises ValueError for anything else (SVG, HTML, broken files).
    Re-encoding also means no file from another site is ever served as it came."""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    if img.format not in ("PNG", "JPEG", "WEBP", "GIF", "ICO", "BMP", "AVIF"):   # AVIF: Apna's CDN (5 Nov)
        raise ValueError(f"not a picture ({img.format})")
    w, h = img.size
    if w * h > MAX_PIXELS or w < 8 or h < 8:
        raise ValueError(f"odd size {w}x{h}")
    if img.format == "ICO":   # several sizes inside: take the biggest
        img.size = max(img.ico.sizes())
    img = img.convert("RGBA")
    img.thumbnail((SIZE, SIZE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "WEBP", quality=88, method=4)
    return out.getvalue()


# Some image servers refuse a request that doesn't look like their own site's page asking (2 Nov:
# Foundit's media.monsterindia.com answered 403, Apna's gumlet.io reset the connection).
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
REFERERS = {"monsterindia.com": "https://www.foundit.in/", "gumlet.io": "https://apna.co/",
            "apna.co": "https://apna.co/", "licdn.com": "https://www.linkedin.com/",
            "naukimg.com": "https://www.naukri.com/", "internshala.com": "https://internshala.com/"}


def request_headers(url: str) -> dict:
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    # no image/avif: servers that honour Accept then send WebP or PNG, which every Pillow can read
    headers = {"Accept": "image/webp,image/png,image/jpeg,image/*;q=0.8", "User-Agent": UA}
    for suffix, ref in REFERERS.items():
        if host == suffix or host.endswith("." + suffix):
            headers["Referer"] = ref
    return headers


def download(url: str, get=None) -> bool:
    """Fetches one logo and saves the copy. True when the copy exists afterwards."""
    if cached(url):
        return True
    if get is None:
        from moderation.safe_http import safe_get as get
    got = get(url, timeout=TIMEOUT_S, headers=request_headers(url))
    resp = got[0] if isinstance(got, tuple) else got   # safe_get returns (response, redirect chain)
    try:
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        kind = resp.headers.get("Content-Type", "").lower()
        if kind and not (kind.startswith("image/") or "octet-stream" in kind) or "svg" in kind:
            raise ValueError(f"not a picture ({kind})")
        data = b""
        for chunk in resp.iter_content(32_768):
            data += chunk
            if len(data) > MAX_BYTES:
                raise ValueError("too big")
    finally:
        resp.close()
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    target = LOGO_DIR / _name(url)
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(shrink(data))
    tmp.replace(target)
    return True


def _loop():
    while True:
        url = _queue.get()
        try:
            download(url)
        except Exception as e:  # noqa: BLE001 - a logo that can't be had leaves the initials
            with _lock:
                _failed.add(url)
            logger.debug(f"Logo skipped ({type(e).__name__}: {str(e)[:80]}): {url[:120]}")


def prefetch(rows) -> int:
    """Queues the logos of these posts for download (one background thread). Returns how many."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        logger.warning("Company logos are off: run  pip install -r requirements.txt  (needs pillow)")
        return 0
    urls = []
    for row in rows:
        url = source_logo(row)
        with _lock:
            skip = not url or url in _failed or url in urls
        if not skip and not cached(url):
            urls.append(url)
    if not urls:
        return 0
    t = _worker["thread"]
    if not (t and t.is_alive()):
        t = threading.Thread(target=_loop, daemon=True, name="logos")
        t.start()
        _worker["thread"] = t
    for url in urls:
        try:
            _queue.put_nowait(url)
        except queue.Full:
            break
    return len(urls)
