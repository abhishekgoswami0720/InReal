"""
Fields of study a student can pick at sign-up, and how each one is searched and recognised.

A scrape run is for ONE field (the dashboard sends it with the run). The scrapers ask this
module for their search words, and filters.py asks it whether a title belongs to the field.
"ai_ml" keeps the original, carefully tuned AI/ML behaviour unchanged.

    search : phrases typed into each site's search box (2-4, most useful first)
    words  : a title or skill containing any of these belongs to the field
"""
import re
import threading

DEFAULT = "ai_ml"

FIELDS = {
    "ai_ml": {
        "label": "AI / Machine Learning",
        "search": ["machine learning", "artificial intelligence", "data science", "deep learning"],
        "words": [],   # filters.py uses its own AI/ML rules for this field
    },
    "software": {
        "label": "Software & Web Development",
        "search": ["software development", "web development", "full stack development", "android development"],
        # titles that say "development" but are not software (SimplyHired/Careerjet test, 18 Oct 2026:
        # "Business Development Executive (Internship)", "Sales Development Representative Intern",
        # "Intern - Learning & Development", "Graphic Designer Intern" were kept as software)
        "not_in_title": ["business development", "sales", "marketing", "learning & development",
                         "learning and development", "graphic", "designer", "content writer", "hr ",
                         "human resource", "recruit", "telecaller", "customer support"],
        "words": ["software", "developer", "development", "web", "frontend", "front end", "backend", "back end",
                  "full stack", "fullstack", "android", "ios", "flutter", "react", "angular", "node", "javascript",
                  "java", "python", "php", ".net", "programming", "sde", "devops", "cloud", "app"],
    },
    "data": {
        "label": "Data Analytics",
        "search": ["data analytics", "data analyst", "business analytics"],
        "words": ["data", "analyst", "analytics", "power bi", "tableau", "sql", "excel", "business intelligence"],
    },
    "medical": {
        "label": "Medicine & Healthcare",
        "search": ["medical", "healthcare", "hospital", "clinical research"],
        "words": ["medical", "medicine", "healthcare", "health care", "health", "hospital", "clinical", "clinic",
                  "mbbs", "doctor", "nursing", "nurse", "physiotherapy", "physiotherapist", "patient", "dental",
                  "pathology", "radiology", "public health", "medical coding", "paramedic", "nutrition", "dietitian"],
    },
    "pharma_bio": {
        "label": "Pharma & Biotech",
        "search": ["pharmacy", "biotechnology", "pharmaceutical", "microbiology"],
        "words": ["pharma", "pharmacy", "pharmacist", "pharmaceutical", "biotech", "biotechnology", "microbiology",
                  "biology", "life science", "life sciences", "drug", "regulatory affairs", "quality control",
                  "laboratory", "lab", "bioinformatics", "genetics", "chemistry"],
    },
    "core_eng": {
        "label": "Mechanical, Electrical & Civil",
        "search": ["mechanical engineering", "electrical engineering", "civil engineering", "electronics"],
        "words": ["mechanical", "electrical", "civil", "electronics", "embedded", "automobile", "automotive",
                  "autocad", "solidworks", "catia", "manufacturing", "production", "vlsi", "structural",
                  "construction", "site engineer", "hvac", "robotics", "plc"],
    },
    "finance": {
        "label": "Finance & Accounting",
        "search": ["finance", "accounting", "investment banking", "chartered accountant"],
        "words": ["finance", "financial", "accounting", "accountant", "accounts", "audit", "tax", "taxation",
                  "banking", "investment", "equity", "stock", "ca articleship", "chartered accountant", "gst",
                  "tally", "fintech", "credit"],
    },
    "marketing": {
        "label": "Marketing & Sales",
        "search": ["digital marketing", "marketing", "sales", "social media marketing"],
        "words": ["marketing", "sales", "seo", "sem", "social media", "brand", "branding", "business development",
                  "advertising", "growth", "e-commerce", "ecommerce", "market research", "public relations", "pr"],
    },
    "design": {
        "label": "Design & Video",
        "search": ["graphic design", "ui ux design", "video editing"],
        "words": ["design", "designer", "ui", "ux", "graphic", "video", "animation", "animator", "figma",
                  "photoshop", "illustrator", "motion", "editing", "editor", "3d", "interior", "fashion"],
    },
    "content": {
        "label": "Content & Media",
        "search": ["content writing", "journalism", "copywriting"],
        "words": ["content", "writing", "writer", "copywriting", "copywriter", "journalism", "journalist",
                  "editor", "blog", "media", "reporter", "communication", "communications"],
    },
    "hr_ops": {
        "label": "HR & Operations",
        "search": ["human resources", "hr", "operations"],
        "words": ["hr", "human resource", "human resources", "recruitment", "recruiter", "talent acquisition",
                  "operations", "management", "administration", "admin", "supply chain", "logistics"],
    },
    "law": {
        "label": "Law",
        "search": ["legal", "law"],
        "words": ["legal", "law", "lawyer", "advocate", "litigation", "compliance", "corporate law", "paralegal",
                  "intellectual property"],
    },
}

_run_field = {"value": DEFAULT}   # one scrape run at a time; its threads all read this


def normalise(field) -> str:
    field = str(field or "").strip().lower()
    return field if field in FIELDS else DEFAULT


def set_current(field):
    """Called once at the start of a scrape run, before the site threads start."""
    _run_field["value"] = normalise(field)


def current() -> str:
    return _run_field["value"]


def label(field=None) -> str:
    return FIELDS[normalise(field or current())]["label"]


def search_terms(field=None) -> list:
    return list(FIELDS[normalise(field or current())]["search"])


def matches(title_and_skills: str, field=None) -> bool:
    """Does this text (lower case) belong to the field? Not used for ai_ml (see filters.py)."""
    words = FIELDS[normalise(field or current())]["words"]
    text = " " + re.sub(r"[-_/,|()]+", " ", title_and_skills.lower()) + " "
    return any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text) for w in words)


def excluded_title(title: str, field=None) -> bool:
    """True when the title names work that is clearly not this field (see 'not_in_title')."""
    words = FIELDS[normalise(field or current())].get("not_in_title", [])
    t = " " + re.sub(r"[-_/,|()]+", " ", (title or "").lower()) + " "
    return any(w in t for w in words)


def slug(term: str) -> str:
    """'clinical research' -> 'clinical-research' (for sites whose search lives in the URL)."""
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")


def public_list() -> list:
    """For the sign-up form: [{key, label}]"""
    return [{"key": k, "label": v["label"]} for k, v in FIELDS.items()]
