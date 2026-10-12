"""
Genuineness checks for scraped listings.

check_listing(item) returns (drop_reason, flags):
  drop_reason  None if the listing can be shown, otherwise why it was removed.
  flags        softer warnings, kept in the "trust_flags" column.

A listing is dropped only for things a real, selective internship never does:
asking the candidate for money, or "hiring" tens of thousands of people.
Everything else is a flag, because big real companies (Times Internet,
Titan, Orient Electric) can look odd on a single number.

The money patterns come from InReal's offer-letter checks, narrowed for job
descriptions: "Fixed pay: ₹ 6,000" or "we pay ₹ 10,000" is the employer paying,
and "no registration fee" is a good sign, so neither may trigger a drop.
"""
import re
from datetime import datetime

FEE_RES = [
    r"\b(registration|training|security|joining|processing|onboarding|certificat\w*|verification"
    r"|application|enrol+ment|kit|laptop|id\s*card|documentation|interview|confirmation|refundable)"
    r"\s*(fee|fees|charges?|deposit|amount)\b",
    r"\b(refundable|security|caution)\s+(money|deposit)\b",
    r"(₹|\brs\.?|\binr)\s?\d[\d,]*(\.\d+)?\s*(/-)?[^.\n]{0,30}?\b(fee|fees|deposit|charges?)\b",
    r"\bpay\w*\b[^.\n]{0,40}?\bto\s+(confirm|book|reserve|secure|block)\b",
    r"\b(fees?|shulk|paise)\b[^.\n]{0,30}?\b(jama|bhej\w*|karni|karna|kare)\b",
]
NEGATION_RE = r"\b(no|not|never|zero|without|free|nil)\b"
TASK_RE = (
    r"\bprepaid\s+tasks?\b|\bper\s+(like|task|review)\b|\blike\s+and\s+earn\b"
    r"|\bmerchant\s+tasks?\b|\btelegram\s+tasks?\b"
)

# Pay that only comes from sales or "performance" (seen on Unstop, Oct 2026)
COMMISSION_RE = (
    r"\bcommission\b|\bearnings?\s+depend|\bperformance[- ]based\s+(pay|earnings?|stipend|income)\b"
    r"|\bno\s+fixed\s+(stipend|salary|pay)\b"
)

# Training institutes selling a "programme" as an internship (seen on Shine and LinkedIn, Oct 2026)
TRAINING_RE = (
    r"\bjob placement\b|\bplacement\s+(assistance|support|guarantee|guaranteed)\b|\b100\s*%\s*placement\b"
    r"|\bjob guarantee\b|\bcareer[- ]oriented program(me)?\b|\bcertification program(me)?\b"
    r"|\btraining program(me)?\s+(with|and)\b|\bcourse fee\b"
    r"|\btraining\s*(&|and|\+|cum|with)\s*internship\b|\binternship\s*(&|and|\+|cum)\s*training\b"
    r"|\bguaranteed\s+certificat\w*"
    # "1 Year Fully Online Remote Internship with Employment Opportunity (Based on Successful Completion)" (AICTE, Oct 2026)
    r"|\b(job|employment|placement)\s+opportunit\w*\s*\(?\s*(based\s+on|after|on|upon)\s+(the\s+)?(successful\s+)?completion"
)
# Titles that read like a course, not a job (AICTE portal, Oct 2026: "Machine Learning with Python",
# "Master Artificial Intelligence", "Data Science with Python Including Ai")
TRAINING_TITLE_RE = r"^\s*(master|learn|become)\b|\bwith python\b|\bcourse\b|\bbootcamp\b|\bcertification\b"
# Employers whose name says they sell courses (Naukri, Oct 2026: "Fireblaze AI School" posting an "AI Intern")
TRAINING_COMPANY_RE = r"\b(school|academy|coaching|classes|bootcamp|edu?\s?tech|skill development|training)\b"
MANY_TOWNS = 6
MASS_OPENINGS = 50   # e.g. "Fullstack Developer Training and Internship", 70 openings (AICTE, Oct 2026)

# A selective internship does not "hire" this many people.
MASS_HIRE_TOTAL = 10_000
MASS_HIRE_PER_POST = 20


def money_asked(text: str):
    """Returns the matching snippet if the text asks the candidate to pay."""
    for pattern in FEE_RES:
        for m in re.finditer(pattern, text, re.I):
            before = text[max(0, m.start() - 25):m.start()]
            if re.search(NEGATION_RE, before + " " + m.group(0)[:12], re.I):
                continue  # "no registration fee", "free of charges"
            return m.group(0).strip()
    return None


def _months(duration: str):
    """'6 Months' -> 6, '2 Weeks' -> 0.5. None if unknown."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(month|week|day)", (duration or "").lower())
    if not m:
        return None
    n = float(m.group(1))
    return {"month": n, "week": n / 4.33, "day": n / 30}[m.group(2)]


def _num(v):
    """Numbers can arrive as '' or '191' when a listing is re-read from CSV."""
    try:
        return None if v in (None, "") else int(float(v))
    except (TypeError, ValueError):
        return None


def check_listing(item: dict):
    text = " ".join(str(item.get(k, "")) for k in ("role_title", "description", "stipend"))

    snippet = money_asked(text)
    if snippet:
        return f"Asks the candidate to pay: \"{snippet}\"", []
    if re.search(TASK_RE, text, re.I):
        return "Task-for-money pattern (like/review tasks)", []

    hired = _num(item.get("employer_hired"))
    posted = _num(item.get("employer_posted"))
    if hired is not None and (
        hired >= MASS_HIRE_TOTAL or (posted and hired / posted >= MASS_HIRE_PER_POST)
    ):
        return (f"Mass programme, not a selective internship "
                f"({hired:,} people 'hired' from {posted or '?'} posts)"), []

    flags = []
    months = _months(item.get("duration", ""))
    if months is not None and months < 1:
        flags.append(f"Very short ({item.get('duration')})")

    since = item.get("employer_since")
    if since and hired in (None, 0):
        try:
            age_days = (datetime.now() - datetime.strptime(since, "%B %Y")).days
            if age_days < 90:
                flags.append(f"New employer on the site (since {since}), no hires yet")
        except ValueError:
            pass

    if posted and posted >= 200 and (hired or 0) / posted < 0.05:
        flags.append(f"Posts a lot, hires few ({posted} posts, {hired or 0} hired)")

    if item.get("stipend_hidden_by_site"):
        pass  # e.g. LinkedIn never shows pay on its cards; not the employer's fault
    elif item.get("stipend_numeric") in (None, 0) and "unpaid" not in str(item.get("stipend", "")).lower():
        flags.append("Stipend amount not stated")

    towns = [t for t in str(item.get("location", "")).split(",") if t.strip()]
    if len(towns) >= MANY_TOWNS:
        flags.append(f"One post listed for {len(towns)} towns")

    if re.search(TRAINING_RE, text, re.I) or re.search(TRAINING_TITLE_RE, str(item.get("role_title", "")), re.I):
        flags.append("Sounds like a training programme sold as an internship")
    elif (item.get("org_type") not in ("Government", "Institution")
          and re.search(TRAINING_COMPANY_RE, str(item.get("company_name", "")), re.I)):
        flags.append("Employer's name sounds like a training institute, so make sure it isn't selling a course")

    min_exp = _num(item.get("min_experience"))
    if min_exp:
        flags.append(f"Asks for {min_exp}+ year{'s' if min_exp > 1 else ''} of experience, unusual for an internship")

    if item.get("portal_verified") is False:
        flags.append("Employer not verified by the portal")

    openings = _num(item.get("openings"))
    if openings and openings >= MASS_OPENINGS:
        flags.append(f"{openings} openings for one internship")

    if re.search(r"\bwww\.|https?://|\b(?!asp\b|vb\b)[a-z0-9-]{3,}\.(com|in|org|co|io)\b", str(item.get("role_title", "")), re.I):
        flags.append("Advertises another website in the title")

    if item.get("third_party"):
        flags.append("Posted by a recruiter or consultant, not the company itself")

    if item.get("repeat_note"):  # set by scraper.mark_repeated_posts
        flags.append(item["repeat_note"])

    if item.get("aggregated"):
        flags.append("Copied by the portal from another site, so confirm on the company's own page")

    if re.search(COMMISSION_RE, text, re.I):
        flags.append("Pay depends on commission or performance")

    # trust_flags is stored as one ";"-separated string, so a ";" inside a flag splits it in two
    return None, [f.replace(";", ",") for f in flags]
