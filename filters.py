import re
import dateparser
from datetime import datetime

INCLUDE_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "nlp", "natural language processing",
    "computer vision", "data science", "generative ai", "gen ai", "genai",
    "llm", "large language model", "reinforcement learning",
    "mlops", "ai research", "ai engineer", "ml engineer", "ai/ml", "ai ml",
    "ai agent", "agentic", "ai developer", "ai development",
    "transformer", "diffusion model", "multimodal", "robotics ai",
    "speech recognition", "recommendation system", "ai intern",
    # Skill tags that only show up on real ML work
    "pytorch", "tensorflow", "keras", "scikit-learn", "opencv",
    "hugging face", "langchain",
]

# Skill tags that, on their own, point to real ML work. "Artificial intelligence"
# and "Generative AI Tools" are left out on purpose: on Internshala, marketing,
# video-editing and HR roles carry those tags too.
CORE_ML_SKILLS = [
    "machine learning", "deep learning", "neural network", "natural language processing",
    "nlp", "computer vision", "data science", "reinforcement learning", "llm",
    "pytorch", "tensorflow", "keras", "scikit-learn", "opencv", "hugging face", "langchain",
]
# A title with a bare "AI" counts only next to one of these words
# ("AI Research Intern" yes; "AI Video Editor", "AI Web Development" no).
AI_TECH_WORDS = [
    "engineer", "engineering", "scientist",
    "model", "models", "agent", "agents", "vision",
]

# Checked against the TITLE only. Skills like "Leadership" or
# "Project Management" must not knock out a real internship.
TITLE_EXCLUDE = [
    "senior", "lead", "manager", "director", "expert",
    "full time", "full-time", "job posting", "job opening",
    "5+ years", "10 years",
    "phd", "ph.d", "mtech", "m.tech", "master's", "masters degree",
]

# Checked against title AND skills (user only knows English/Hindi)
LANGUAGE_EXCLUDE = ["japanese", "german", "french", "mandarin", "spanish", "korean"]


def _has_word(text: str, word: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text) is not None


def internship_rejection_reason(title: str, skills: list, source: str = ""):
    """
    Returns None if the listing is an AI/ML internship we want,
    otherwise a short reason it was rejected.
    """
    title_lower = title.lower()
    skills_lower = [s.lower() for s in skills]
    text_to_check = title_lower + " " + " ".join(skills_lower)

    # Must contain 'intern' unless the platform only lists internships
    # Portals that only list internships (the AICTE government portal too), so titles needn't say "intern"
    is_internship_platform = source in ["internshala", "unstop", "government"]
    if "intern" not in title_lower and not is_internship_platform:
        return "Not labelled as an internship"

    for exc in TITLE_EXCLUDE:
        if _has_word(title_lower, exc):
            return f"Title has '{exc}'"
    for lang in LANGUAGE_EXCLUDE:
        if _has_word(text_to_check, lang):
            return f"Needs {lang.title()}"

    # Reject listings that name a past year
    now = datetime.now()
    target_year = now.year + (1 if now.month > 5 else 0)
    for i in range(1, 10):
        past_year = str(target_year - i)
        if past_year in title_lower and past_year != str(now.year):
            return f"Mentions old year {past_year}"

    if is_ai_ml_title(title_lower):
        return None
    # No AI/ML in the title: the skills must show at least two real ML skills
    core = [s for s in skills_lower if any(k in s for k in CORE_ML_SKILLS)]
    if len(core) >= 2:
        return None
    return "Not an AI/ML role"


def is_ai_ml_title(title_lower: str) -> bool:
    if any(inc in title_lower for inc in INCLUDE_KEYWORDS):
        return True
    if _has_word(title_lower, "ml"):
        return True
    return _has_word(title_lower, "ai") and any(_has_word(title_lower, w) for w in AI_TECH_WORDS)


def is_valid_internship(title: str, skills: list, source: str = "") -> bool:
    return internship_rejection_reason(title, skills, source) is None


def stipend_rejection_reason(stipend_str: str, numeric_val: float, is_india: bool):
    """
    Returns None if the stipend is acceptable, otherwise a reason.
    - Unpaid is rejected.
    - Indian internships need at least 5000 INR/month.
    - "Not mentioned" / "Competitive stipend" is kept (amount unknown).
    """
    if stipend_str is None or stipend_str.strip() == "":
        return None
    stipend_lower = stipend_str.lower()
    if "unpaid" in stipend_lower:
        return "Unpaid"
    if numeric_val is None or numeric_val == 0:
        return None  # amount not stated; don't drop a real listing for that
    if is_india and numeric_val < 5000:
        return f"Stipend below ₹5,000/month ({stipend_str.strip()})"
    return None


def is_valid_stipend(stipend_str: str, numeric_val: float, is_india: bool) -> bool:
    return stipend_rejection_reason(stipend_str, numeric_val, is_india) is None


def parse_summer_dates(date_string: str) -> bool:
    """
    NLP constraint: Internship MUST start on/after May 20. End date is flexible.
    If explicitly says Summer, it passes.
    """
    ALLOW_TERMS = ["", "not mentioned", "rolling", "immediately", "asap", "flexible", "ongoing", "open", "continuous", "anytime"]
    if not date_string or str(date_string).strip().lower() in ALLOW_TERMS:
        return True # Default allow if unspecified

    date_lower = str(date_string).lower()

    # Explicit summer keywords
    if "summer" in date_lower or "may" in date_lower or "june" in date_lower:
        return True

    # NLP Parse
    # Attempt to extract early dates.
    # Example: "Starts Jan 2026" should fail.
    try:
        parsed_date = dateparser.parse(date_lower, settings={'PREFER_DATES_FROM': 'future'})
        if parsed_date:
            # Dynamically set target year based on current date
            now = datetime.now()
            target_year = now.year + (1 if now.month > 5 else 0)

            start_threshold = datetime(target_year, 5, 20)
            end_threshold = datetime(target_year, 8, 31)

            # If it explicitly lists a year other than target_year, reject it
            if parsed_date.year != target_year and (str(target_year) not in date_lower):
                # Only strictly reject if it explicitly contains another 4-digit year (e.g., 2024, 2025, 2027)
                year_match = re.search(r'\b(20\d{2})\b', date_lower)
                if year_match and year_match.group(1) != str(target_year):
                    return False

            # If starting before May 20 or after Aug 31 of target_year
            if parsed_date.year == target_year:
                if parsed_date < start_threshold or parsed_date > end_threshold:
                    return False

        return True
    except Exception:
        # If parsing fails entirely, we don't block it to avoid safe drops
        return True

def calculate_match_score(title: str, skills: list, org_type: str, stipend: float) -> int:
    """
    Out of 100.
    Base 50.
    +20 for Core keywords (AI, ML, Computer Vision)
    +15 for Academic/Research Org
    +15 for high stipend
    """
    score = 50
    title_lower = title.lower()
    skills_lower = [s.lower() for s in skills]
    text_to_check = title_lower + " " + " ".join(skills_lower)

    core_keywords = ["research", "deep learning", "computer vision", "generative ai", "nlp", "scientist"]
    for word in core_keywords:
        if word in text_to_check:
            score += 20
            break

    if org_type in ["Institution", "Government"]:
        score += 15

    if stipend > 40000: # High stipend reward
        score += 15

    return min(100, score)
