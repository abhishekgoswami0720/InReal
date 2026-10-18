"""
Dynamic University & Research Lab Internship Discoverer
───────────────────────────────────────────────────────
Uses DuckDuckGo (via the `ddgs` package) with targeted search queries to
dynamically discover current AI/ML internships at universities, government
labs, and AI research institutes worldwide. No hardcoded list — refreshes
every time the scraper runs.
"""

import hashlib
from datetime import datetime
from urllib.parse import urlparse

try:
    from ddgs import DDGS  # new package name
except ImportError:
    from duckduckgo_search import DDGS  # fallback to legacy

from loguru import logger
from filters import calculate_match_score, is_valid_internship
from scraper_utils import human_delay

YEAR = datetime.now().year

# ─────────────────────────────────────────────────────────────────────────────
# SEARCH QUERY BANK
# Each tuple: (query_string, category_label, org_type, role_type, loc, loc_type)
# Queries are intentionally short & simple — DDG rejects overly long dorks.
# ─────────────────────────────────────────────────────────────────────────────
QUERIES = [
    # ── GLOBAL OPEN SEARCH ───────────────────────────────────────────────────
    (f"AI ML deep learning research internship {YEAR} university stipend",
     "Global University", "Institution", "Research", "Global", "International"),

    (f"machine learning summer internship {YEAR} fellowship apply university",
     "Global University", "Institution", "Research", "Global", "International"),

    (f"artificial intelligence research intern {YEAR} PhD graduate international",
     "Global AI Research", "Institution", "Research", "Global", "International"),

    # ── INDIA ────────────────────────────────────────────────────────────────
    (f"IIT IISc IIIT research internship AI machine learning {YEAR} india apply",
     "Indian University", "Institution", "Research", "India", "India"),

    (f"data science ML internship India {YEAR} stipend DRDO ISRO TIFR apply",
     "Indian R&D Lab", "Government", "Research", "India", "India"),

    # ── EUROPE ───────────────────────────────────────────────────────────────
    (f"Aalto KTH Chalmers ETH EPFL TU Munich AI research internship {YEAR}",
     "European University", "Institution", "Research", "Europe", "International"),

    (f"DAAD Max Planck Inria AI ML research internship Europe {YEAR} summer",
     "European Research Institute", "Institution", "Research", "Europe", "International"),

    (f"Oxford Cambridge UCL Imperial Edinburgh AI ML research intern {YEAR}",
     "UK University", "Institution", "Research", "United Kingdom", "International"),

    (f"machine learning fellowship Europe {YEAR} funded visiting researcher",
     "European Fellowship", "Institution", "Research", "Europe", "International"),

    # ── NORDIC ───────────────────────────────────────────────────────────────
    (f"Aalto University AI internship {YEAR} open position research assistant",
     "Nordic (Aalto/Finland)", "Institution", "Research", "Finland", "International"),

    (f"KTH DTU NTNU Uppsala AI ML internship {YEAR} apply research",
     "Nordic University", "Institution", "Research", "Nordic Europe", "International"),

    # ── CHINA ────────────────────────────────────────────────────────────────
    (f"Tsinghua Peking NUS AI machine learning research internship {YEAR}",
     "Asia University (China/SG)", "Institution", "Research", "China / Singapore", "International"),

    (f"ByteDance Alibaba Baidu Huawei AI ML research intern {YEAR} apply",
     "China Industry AI Lab", "Company", "Research", "China", "International"),

    (f"Zhejiang Fudan USTC SJTU AI ML research internship visiting student {YEAR}",
     "China University", "Institution", "Research", "China", "International"),

    # ── USA ──────────────────────────────────────────────────────────────────
    (f"MIT Stanford CMU Berkeley AI ML summer research {YEAR} UROP REU internship",
     "US University (Top)", "Institution", "Research", "USA", "International"),

    (f"DeepMind OpenAI Anthropic Google Meta AI research intern {YEAR} apply",
     "Global AI Lab (US)", "Company", "Research", "USA / Remote", "International"),

    (f"NSF REU machine learning artificial intelligence {YEAR} summer program",
     "US National Science Foundation (REU)", "Government", "Research", "USA", "International"),

    (f"Oak Ridge Argonne PNNL Sandia AI machine learning internship {YEAR} SULI",
     "US National Lab", "Government", "Research", "USA", "International"),

    (f"Allen Institute NVIDIA FAIR Apple IBM AI research intern {YEAR}",
     "US Industry AI Lab", "Company", "Research", "USA", "International"),

    # ── CANADA ───────────────────────────────────────────────────────────────
    (f"Mitacs Globalink Vector Institute Mila AI ML research internship {YEAR}",
     "Canadian Program", "Institution", "Research", "Canada", "International"),

    # ── JAPAN / KOREA / SOUTHEAST ASIA ──────────────────────────────────────
    (f"RIKEN Kaist NII Samsung NAVER LG AI research internship {YEAR} apply",
     "East Asia Lab/University", "Institution", "Research", "East Asia", "International"),

    (f"Singapore NTU NUS A-STAR Alibaba AI ML internship {YEAR} international students",
     "Singapore / SE Asia", "Institution", "Research", "Singapore", "International"),

    # ── AUSTRALIA ────────────────────────────────────────────────────────────
    (f"CSIRO Data61 ANU Melbourne AI ML research internship {YEAR} apply",
     "Australia University/Lab", "Institution", "Research", "Australia", "International"),

    # ── ATS BOARDS (LEVER / GREENHOUSE) ─────────────────────────────────────
    (f"site:boards.greenhouse.io machine learning intern {YEAR}",
     "ATS Board (Greenhouse)", "Company", "Applied", "Global", "International"),

    (f"site:jobs.lever.co AI machine learning research intern {YEAR}",
     "ATS Board (Lever)", "Company", "Applied", "Global", "International"),

    # ── STARTUP / YC BOARDS ──────────────────────────────────────────────────
    (f"site:wellfound.com machine learning intern {YEAR}",
     "Startup Board (Wellfound)", "Company", "Applied", "Remote", "Remote"),

    (f"site:jobs.ycombinator.com AI ML intern {YEAR}",
     "YC Job Board", "Company", "Applied", "USA / Remote", "Remote"),

    # ── MISC / BROAD ─────────────────────────────────────────────────────────
    (f"machine learning internship China Japan Korea Europe India {YEAR} international apply open",
     "Global Broad Search", "Institution", "Research", "Global", "International"),

    (f"computer vision NLP generative AI research internship {YEAR} stipend funded apply",
     "Global Research (CV/NLP)", "Institution", "Research", "Global", "International"),

    (f"CERN ESA European Space Agency AI ML internship trainee {YEAR} apply",
     "European Science Agency", "Government", "Research", "Europe", "International"),

    # ── MIDDLE EAST ──────────────────────────────────────────────────────────
    (f"KAUST MBZUAI Mohamed bin Zayed AI research internship {YEAR} apply",
     "Middle East AI Lab", "Institution", "Research", "UAE / Saudi Arabia", "International"),

    (f"Technion Hebrew University AI ML research internship {YEAR} Israel",
     "Israel University", "Institution", "Research", "Israel", "International"),

    # ── LATIN AMERICA ────────────────────────────────────────────────────────
    (f"USP UNICAMP Brazilian AI ML research internship {YEAR} apply scholarship",
     "Latin America University", "Institution", "Research", "Brazil", "International"),

    # ── EASTERN EUROPE ────────────────────────────────────────────────────────
    (f"Prague Warsaw Zurich AI research internship {YEAR} funded apply",
     "Eastern Europe University", "Institution", "Research", "Eastern Europe", "International"),

    # ── AFRICA ───────────────────────────────────────────────────────────────
    (f"UCT Wits AIMS African AI ML research internship {YEAR} apply",
     "Africa University", "Institution", "Research", "Africa", "International"),

    # ── SPECIFIC AI DOMAINS ──────────────────────────────────────────────────
    (f"robotics AI machine learning internship {YEAR} university lab summer",
     "Robotics AI Internship", "Institution", "Research", "Global", "International"),

    (f"bioinformatics computational biology AI ML internship {YEAR} PhD application",
     "Bio/ML Internship", "Institution", "Research", "Global", "International"),

    (f"speech recognition audio AI research internship {YEAR} lab apply",
     "Speech AI Lab", "Institution", "Research", "Global", "International"),

    (f"reinforcement learning RL research intern {YEAR} lab university funded apply",
     "RL Research Intern", "Institution", "Research", "Global", "International"),

    (f"generative AI LLM large language model research internship {YEAR} apply",
     "LLM/GenAI Research", "Company", "Research", "Global", "International"),

    # ── MICROSOFT RESEARCH GLOBAL ─────────────────────────────────────────────
    (f"Microsoft Research internship {YEAR} AI machine learning summer apply",
     "Microsoft Research Global", "Company", "Research", "Global", "International"),

    # ── SEMICONDUCTOR / HARDWARE AI ───────────────────────────────────────────
    (f"NVIDIA AMD Intel Qualcomm AI ML hardware research internship {YEAR} apply",
     "Hardware AI Lab", "Company", "Applied", "USA / Global", "International"),

    # ── OPEN SOURCE / HUGGING FACE ───────────────────────────────────────────
    (f"Hugging Face Mozilla Mozilla.ai AI open source research internship {YEAR}",
     "Open Source AI Lab", "Institution", "Applied", "Remote", "Remote"),

    # ── GLOBAL FELLOWSHIP PORTALS ─────────────────────────────────────────────
    (f"\"fully funded\" AI machine learning internship fellowship {YEAR} international",
     "Fully Funded Fellowship", "Institution", "Research", "Global", "International"),

    (f"\"stipend\" \"research intern\" AI MS PhD {YEAR} open application",
     "Funded Research Internship", "Institution", "Research", "Global", "International"),

    # ── NICHE JOB BOARDS ──────────────────────────────────────────────────────
    (f"site:smartrecruiters.com machine learning AI intern {YEAR}",
     "ATS Board (SmartRecruiters)", "Company", "Applied", "Global", "International"),

    (f"site:ashbyhq.com machine learning AI research intern {YEAR}",
     "ATS Board (Ashby)", "Company", "Applied", "Global", "International"),

    (f"site:workday.com machine learning AI intern {YEAR}",
     "ATS Board (Workday)", "Company", "Applied", "Global", "International"),

    (f"site:icims.com machine learning AI internship {YEAR}",
     "ATS Board (iCIMS)", "Company", "Applied", "Global", "International"),

    # ── SPECIFIC PROGRAM NAMES ────────────────────────────────────────────────
    (f"\"summer research program\" OR \"UROP\" OR \"REU\" OR \"SURF\" AI machine learning {YEAR} apply",
     "Named Research Programs", "Institution", "Research", "Global", "International"),

    (f"\"visiting researcher\" OR \"research assistant\" AI ML {YEAR} stipend university",
     "Visiting Researcher Roles", "Institution", "Research", "Global", "International"),

    # ── INDIA — SPECIFIC FELLOWSHIPS ─────────────────────────────────────────
    (f"PMRF PM research fellowship AI machine learning {YEAR} India apply",
     "India Government Fellowship", "Government", "Research", "India", "India"),

    (f"SERB Prime Minister research fellow AI ML India {YEAR} apply",
     "India SERB Fellowship", "Government", "Research", "India", "India"),

    # ── NEW ZEALAND / PACIFIC ─────────────────────────────────────────────────
    (f"University Auckland Otago Victoria AI ML research internship {YEAR} apply",
     "New Zealand University", "Institution", "Research", "New Zealand", "International"),
]


AI_TERMS = [
    "machine learning", "artificial intelligence", "deep learning", "nlp",
    "computer vision", "data science", "neural network", "ai intern", "ml intern",
    "generative ai", "llm", "reinforcement learning", "research intern",
]

INTERNSHIP_TERMS = [
    "intern", "fellowship", "trainee", "urop", "reu", "visiting researcher",
    "summer program", "research assistant", "research program", "student researcher",
]


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "").replace("jobs.", "")
    except Exception:
        return url[:40]


def scrape_universities():
    """
    Dynamically discovers AI/ML research internships at universities,
    government labs, and AI research institutes worldwide using DuckDuckGo.
    """
    all_internships = []
    seen_ids: set = set()

    try:
        ddgs = DDGS()

        queries = QUERIES
        import fields
        if fields.current() != fields.DEFAULT:   # the bank above is AI/ML only; other fields get their own
            queries = []
            for term in fields.search_terms()[:2]:
                queries += [
                    (f"{term} research internship {YEAR} university apply", "Global University",
                     "Institution", "Research", "Global", "International"),
                    (f"{term} internship {YEAR} IIT IISc NIT AIIMS apply", "Indian University",
                     "Institution", "Research", "India", "India"),
                ]
        for i, (query, category, def_org, def_role, location, loc_type) in enumerate(queries):
            logger.info(f"[Universities] Query {i+1}/{len(queries)}: {category}")
            try:
                results = list(ddgs.text(query, max_results=15))
                found_this = 0

                for res in results:
                    title = res.get("title", "").strip()
                    snippet = res.get("body", "").strip()
                    href = res.get("href", "").strip()

                    if not href or not title:
                        continue

                    full_text = f"{title} {snippet}".lower()

                    # Must relate to AI/ML
                    if not any(k in full_text for k in AI_TERMS):
                        continue

                    # Must relate to internship/fellowship
                    if not any(k in full_text for k in INTERNSHIP_TERMS):
                        continue

                    # Deduplicate by URL hash
                    uid = hashlib.md5(href.encode()).hexdigest()
                    if uid in seen_ids:
                        continue
                    seen_ids.add(uid)

                    domain = _domain(href)
                    role_title = title if len(title) < 100 else f"AI/ML Opportunity at {domain}"

                    # Boost org/role type for clearly academic domains
                    dom_lower = href.lower()
                    if any(x in dom_lower for x in [".edu", ".ac.", ".res.", "lab", "institute",
                                                      "university", "deepmind", "mila", "allenai",
                                                      "vectorinstitute", "bair", "inria", "riken"]):
                        org_type, role_type = "Institution", "Research"
                    elif any(x in dom_lower for x in [".gov", "ornl", "anl", "pnnl", "sandia", "energy.gov"]):
                        org_type, role_type = "Government", "Research"
                    else:
                        org_type, role_type = def_org, def_role

                    currency = "INR" if loc_type == "India" else "USD"
                    stipend_num = 60000.0 if loc_type == "India" else 1500.0

                    match_score = calculate_match_score(
                        f"{title} {snippet}", ["Research", "AI", "ML"], org_type, stipend_num
                    )

                    record = {
                        "id": uid,
                        "company_name": domain,
                        "role_title": role_title,
                        "location": location,
                        "location_type": loc_type,
                        "duration": "Check Program Page",
                        "stipend": "Funded / Stipend (Check Website)",
                        "stipend_numeric": stipend_num,
                        "stipend_currency": currency,
                        "required_skills": "AI/ML, Research",
                        "application_deadline": "Check Program Page",
                        "apply_link": href,
                        "source_platform": f"Uni Search: {category}",
                        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                        "org_type": org_type,
                        "role_type": role_type,
                        "match_score": match_score,
                    }
                    all_internships.append(record)
                    found_this += 1

                logger.info(
                    f"[Universities] {category}: +{found_this} "
                    f"(total: {len(all_internships)})"
                )

            except Exception as e:
                logger.error(f"[Universities] Error on '{category}': {e}")

            human_delay(3.0, 5.0)

    except Exception as e:
        logger.error(f"[Universities] Critical error: {e}")

    logger.info(
        f"[Universities] Discovered {len(all_internships)} unique global "
        f"research internship/fellowship listings."
    )
    return all_internships
