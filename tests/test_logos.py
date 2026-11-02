"""Company logos (logos.py, sites/_common): only the source site's logo, kept as a checked local copy."""
import io
import pathlib

import pytest
from bs4 import BeautifulSoup
from PIL import Image

import logos
from sites import _common, internshala, rss_feeds, unstop


def _png(w=300, h=200, fmt="PNG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(out, fmt)
    return out.getvalue()


class _Resp:
    def __init__(self, body, kind="image/png", status=200):
        self.body, self.status_code, self.headers = body, status, {"Content-Type": kind}

    def iter_content(self, n):
        for i in range(0, len(self.body), n):
            yield self.body[i:i + n]

    def close(self):
        pass


@pytest.fixture
def logo_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(logos, "LOGO_DIR", tmp_path)
    return tmp_path


# ---------- finding the logo in what a site sent ----------

def test_logo_url_keeps_only_real_image_links():
    assert _common.logo_url("//cdn.x.com/a.png") == "https://cdn.x.com/a.png"
    assert _common.logo_url("/logo/a.png", "https://internshala.com") == "https://internshala.com/logo/a.png"
    assert _common.logo_url({"url": "https://x.com/a.png"}) == "https://x.com/a.png"
    for junk in ("data:image/png;base64,AAAA", "javascript:alert(1)", "logo.png", "",
                 "https://static.licdn.com/aero-v1/sc/h/ghost-company.svg", "https://x.com/no-logo.png",
                 'https://x.com/a.png" onerror="x'):
        assert _common.logo_url(junk) == "", junk


def test_logo_in_card_finds_the_company_logo_not_other_pictures():
    html = """<div class="card"><img src="https://x.com/banner.jpg" alt="Office">
      <img class="artdeco-entity-image" src="data:image/gif;base64,R0" data-delayed-url="https://media.licdn.com/acme.png" alt="Acme"></div>"""
    assert _common.logo_in_card(BeautifulSoup(html, "lxml")) == "https://media.licdn.com/acme.png"
    by_alt = '<div><img src="/up/9.png" alt="Acme Labs"></div>'
    assert _common.logo_in_card(BeautifulSoup(by_alt, "lxml"), "Acme Labs", "https://apna.co") == "https://apna.co/up/9.png"
    assert _common.logo_in_card(BeautifulSoup('<div><img src="https://x.com/p.jpg" alt="team"></div>', "lxml")) == ""


def test_logo_in_json_looks_under_logo_keys():
    assert _common.logo_in_json({"organisation": {"name": "A", "logoUrl": "https://cdn.u/a.png"}}) == "https://cdn.u/a.png"
    assert _common.logo_in_json({"companyLogoUrl": None, "company": {"logo": {"url": "https://f.co/l.png"}}}) == "https://f.co/l.png"
    assert _common.logo_in_json({"title": "x", "image": "https://x.com/a.png"}) == ""


def test_scrapers_pass_the_logo_on():
    jobs = [{"id": 2, "title": "Software Engineering Intern", "job_type": "internship", "company_name": "B",
             "url": "https://remotive.com/remote-jobs/x-2", "company_logo": "https://remotive.com/job/2/logo"}]
    import fields
    fields.set_current("software")
    try:
        assert rss_feeds.parse_remotive(jobs)[0]["company_logo"] == "https://remotive.com/job/2/logo"
    finally:
        fields.set_current(fields.DEFAULT)
    rec = unstop.parse_api_record({"id": 7, "title": "AI Intern", "status": "LIVE",
                                   "organisation": {"name": "Acme", "logoUrl": "https://d8it4huxumps7.cloudfront.net/a.png"}})
    assert rec["company_logo"] == "https://d8it4huxumps7.cloudfront.net/a.png"
    html = (pathlib.Path(__file__).parent / "fixtures" / "internshala_list.html").read_text(encoding="utf-8")
    recs, _ = internshala.parse_list_page(html)
    assert recs and all("company_logo" in r for r in recs)


# ---------- which logo a post gets ----------

def test_only_the_sites_logo_never_a_lookup_by_name():
    assert logos.source_logo({"company_name": "Google", "source_platform": "Internshala"}) == ""   # a "Google" post elsewhere
    assert logos.source_logo({"company_name": "Google", "source_platform": "Internshala",
                              "company_logo": "https://x/l.png"}) == "https://x/l.png"
    assert "domain=microsoft.com" in logos.source_logo({"company_name": "Microsoft", "source_platform": "Microsoft Careers"})


# ---------- the local copy ----------

def test_download_saves_a_small_webp_copy(logo_dir):
    url = "https://cdn.example.com/acme.png"
    assert logos.cached(url) == ""
    assert logos.download(url, get=lambda u, **k: (_Resp(_png()), [u]))
    path = logos.cached(url)
    assert path.startswith("/static/logos/") and path.endswith(".webp")
    img = Image.open(logo_dir / path.rsplit("/", 1)[1])
    assert img.format == "WEBP" and max(img.size) == 128


@pytest.mark.parametrize("resp", [
    _Resp(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml"),
    _Resp(b"<html>login</html>", "text/html"),
    _Resp(b"not a picture at all", "image/png"),
    _Resp(_png(), "image/png", status=404),
    _Resp(b"x" * (logos.MAX_BYTES + 10), "image/png"),
])
def test_download_refuses_what_is_not_a_logo(logo_dir, resp):
    with pytest.raises(Exception):
        logos.download("https://cdn.example.com/bad.png", get=lambda u, **k: (resp, [u]))
    assert logos.cached("https://cdn.example.com/bad.png") == ""


def test_download_goes_through_the_ssrf_guard(logo_dir):
    from moderation.safe_http import BlockedAddress
    with pytest.raises(BlockedAddress):
        logos.download("http://127.0.0.1:5000/api/clear")


def test_api_sends_only_the_local_copy(logo_dir, tmp_path, monkeypatch):
    import app as app_mod
    import output_handler as oh
    url = "https://cdn.example.com/acme.png"
    logos.download(url, get=lambda u, **k: (_Resp(_png()), [u]))
    rows = [{"id": "a", "company_name": "Acme", "company_logo": url, "source_platform": "Internshala"},
            {"id": "b", "company_name": "Beta", "company_logo": "https://cdn.example.com/missing.png"}]
    monkeypatch.setattr(oh, "read_all_rows", lambda: [dict(r) for r in rows])
    monkeypatch.setattr(app_mod, "DATA_FILE", tmp_path)   # any existing path
    data = app_mod.app.test_client().get("/api/internships").get_json()
    by_id = {r["id"]: r for r in data}
    assert by_id["a"]["logo"] == logos.cached(url) and by_id["b"]["logo"] == ""
    assert all("company_logo" not in r for r in data)        # the other site's link never reaches the page


def test_aicte_logo_links_point_to_the_public_site_and_skip_the_portals_own_logo():
    from sites.government import _logo
    assert _logo({"logo": "http://localhost:3090/api/v1/media/logo/CORPORATE68.png"}) == \
        "https://internship.aicte-india.org/api/v1/media/logo/CORPORATE68.png"
    assert _logo({"logo": "https://internship.aicte-india.org/images/new_logo/logo_internship_new.jpg"}) == ""


def test_download_unpacks_what_safe_get_returns(logo_dir, monkeypatch):
    import moderation.safe_http as sh
    monkeypatch.setattr(sh, "safe_get", lambda url, **k: (_Resp(_png()), [url]))
    assert logos.download("https://cdn.example.com/real.png")   # 2 Nov: the tuple broke every download


def test_aicte_posts_saved_before_the_fix_get_the_public_link():
    row = {"source_platform": "AICTE Internship Portal (Govt of India)",
           "company_logo": "http://localhost:3090/api/v1/media/logo/CORPORATE68.png"}
    assert logos.source_logo(row) == "https://internship.aicte-india.org/api/v1/media/logo/CORPORATE68.png"
    row["company_logo"] = "https://internship.aicte-india.org/images/new_logo/logo_internship_new.jpg"
    assert logos.source_logo(row) == ""


def test_a_big_but_real_logo_is_kept(logo_dir):
    url = "https://internship.aicte-india.org/api/v1/media/logo/big.png"   # 2420 x 2420, as AICTE sent
    assert logos.download(url, get=lambda u, **k: (_Resp(_png(2420, 2420)), [u]))
    assert logos.cached(url)
