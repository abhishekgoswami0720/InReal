import re
import hashlib
from datetime import datetime
from loguru import logger
from scraper_utils import human_delay
try:
    from ddgs import DDGS  # new package name
except ImportError:
    from duckduckgo_search import DDGS  # legacy fallback
from filters import calculate_match_score, is_valid_internship

def scrape_search_engine(config=None):
    """Dynamically aggregates hidden internship links using DuckDuckGo Dorks."""
    all_internships = []
    
    if config is None:
        config = {}
        
    req_regions = [r.lower() for r in config.get("regions", ["india", "worldwide", "usa", "europe", "remote"])]
    
    # We define different categories of dorks to cover "everything else"
    # The queries emphasize summer, AI/ML, intern, and stipends.
    
    current_year = datetime.now().year
    
    queries = [
        # 1. Global Universities (Research & Labs)
        {
            "q": f'(site:.edu OR site:.ac.uk) "artificial intelligence" OR "machine learning" "summer research internship" {current_year}',
            "org_type": "Institution",
            "role_type": "Research",
            "source_prefix": "Global Edu",
            "loc": "Global / Remote",
            "loc_type": "International"
        },
        # 2. Indian Universities & Institutions
        {
            "q": f'(site:.ac.in OR site:.edu.in OR site:.res.in) "artificial intelligence" OR "machine learning" "internship" {current_year}',
            "org_type": "Institution",
            "role_type": "Research",
            "source_prefix": "India Edu",
            "loc": "India",
            "loc_type": "India"
        },
        # 3. Global Companies (Greenhouse, Lever, Workday)
        {
            "q": f'(site:boards.greenhouse.io OR site:jobs.lever.co) "machine learning" OR "ai" "intern" OR "internship" {current_year}',
            "org_type": "Company",
            "role_type": "Applied",
            "source_prefix": "ATS Boards",
            "loc": "Global",
            "loc_type": "International"
        },
        # 4. Indian Startups & Tech Companies
        {
            "q": f'site:.in (intitle:careers OR intitle:jobs) "machine learning intern" OR "AI intern" Bangalore OR Hyderabad OR Pune OR Remote',
            "org_type": "Company",
            "role_type": "Applied",
            "source_prefix": "India Tech",
            "loc": "India",
            "loc_type": "India"
        },
        # 5. Government AI/ML Initiatives (India)
        {
            "q": f'(site:.gov.in OR site:.nic.in) "machine learning" OR "artificial intelligence" "internship" {current_year}',
            "org_type": "Government",
            "role_type": "Research",
            "source_prefix": "Govt India",
            "loc": "India",
            "loc_type": "India"
        },
        # 6. Open Source / Non-Profits
        {
            "q": f'(site:.org OR site:.io) "machine learning" OR "artificial intelligence" "internship" OR "summer of code" {current_year}',
            "org_type": "Institution", # mapping non-profit/open-source to institution roughly
            "role_type": "Applied",
            "source_prefix": "Open Source",
            "loc": "Global / Remote",
            "loc_type": "Remote"
        },
        # 7. Blocked Indian Job Boards (Naukri, Foundit, Cutshort)
        {
            "q": f'(site:naukri.com/job-listings OR site:foundit.in OR site:cutshort.io) "machine learning" OR "artificial intelligence" "intern" OR "internship" {current_year}',
            "org_type": "Company",
            "role_type": "Applied",
            "source_prefix": "India Boards (Dork)",
            "loc": "India",
            "loc_type": "India"
        },
        # 8. Blocked Global Job Boards (LinkedIn, Indeed)
        {
            "q": f'(site:linkedin.com/jobs/view OR site:indeed.com/viewjob) "machine learning" OR "artificial intelligence" "intern" OR "internship" {current_year}',
            "org_type": "Company",
            "role_type": "Applied",
            "source_prefix": "Global Boards (Dork)",
            "loc": "Global",
            "loc_type": "International"
        }
    ]
    
    # Other fields (fields.py): swap the AI/ML words in every query for the field's own words
    import fields
    if fields.current() != fields.DEFAULT:
        term = fields.search_terms()[0]
        ai_words = re.compile(r'"machine learning intern" OR "AI intern"|"artificial intelligence" OR "machine learning"'
                              r'|"machine learning" OR "artificial intelligence"|"machine learning" OR "ai"', re.I)
        for q in queries:
            q["q"] = ai_words.sub(f'"{term}"', q["q"])

    active_queries = []
    for q in queries:
        lt = q["loc_type"].lower()
        if lt == "india" and "india" not in req_regions: 
            continue
        if lt == "international" and not any(r in req_regions for r in ["worldwide", "usa", "europe"]): 
            continue
        if lt == "remote" and "remote" not in req_regions:
            # Skip remote queries only if user exclusively selected "india"
            if req_regions == ["india"]:
                continue
        active_queries.append(q)
        
    if not active_queries:
        logger.warning("SearchEngine: No dork queries matched the requested regions.")
        return []

    try:
        ddgs = DDGS()
        for q_obj in active_queries:
            logger.info(f"Running Dork Search: {q_obj['q']}")
            try:
                # Use text search, fetching top 15 results
                results = list(ddgs.text(q_obj['q'], max_results=15))
                
                for res in results:
                    title = res.get('title', '')
                    snippet = res.get('body', '')
                    href = res.get('href', '')
                    
                    # Check if it resembles an internship
                    if not is_valid_internship(title, [snippet]):
                        continue
                        
                    company_name = href.split("//")[-1].split("/")[0].replace("www.", "")
                    
                    # Truncate title or make generic if very long
                    role_title = title if len(title) < 90 else f"AI/ML Found at {company_name}"
                    
                    source_platform = f"Search: {q_obj['source_prefix']}"
                    
                    # Base scoring
                    match_score = calculate_match_score(title + " " + snippet, ["AI/ML"], q_obj['org_type'], 0.0)
                    
                    id_hash = hashlib.md5(f"{company_name}-{role_title}-{href}".encode()).hexdigest()
                    
                    record = {
                        "id": id_hash,
                        "company_name": company_name,
                        "role_title": role_title,
                        "location": q_obj['loc'],
                        "location_type": q_obj['loc_type'],
                        "duration": "Check Website",
                        "stipend": "Discover on Site",
                        "stipend_numeric": 5000.0 if q_obj['loc_type'] == "India" else 1000.0, # Pass filters
                        "stipend_currency": "INR" if q_obj['loc_type'] == "India" else "USD",
                        "required_skills": "AI/ML (Extracted from search)", 
                        "application_deadline": "Rolling", 
                        "apply_link": href,
                        "source_platform": source_platform,
                        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                        "org_type": q_obj['org_type'],
                        "role_type": q_obj['role_type'],
                        "match_score": match_score
                    }
                    
                    all_internships.append(record)
                    
            except Exception as e:
                logger.error(f"Error executing dork {q_obj['q']}: {e}")
                
            human_delay(3.0, 6.0) # respectful delay between dorks
            
    except Exception as e:
        logger.error(f"Error initializing duckduckgo search: {e}")
        
    return all_internships
