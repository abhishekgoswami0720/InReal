from playwright.sync_api import sync_playwright
import time
import random
from bs4 import BeautifulSoup
import hashlib
from datetime import datetime
from loguru import logger
import urllib.parse
import re
from filters import calculate_match_score
from playwright_stealth import Stealth
from scraper_utils import human_delay, get_playwright_stealth_args
from tenacity import retry, wait_exponential, stop_after_attempt

def parse_job_card(html, selectors, source_name, url_base=""):
    """Generic parser for simple job cards."""
    soup = BeautifulSoup(html, "lxml")
    listings = soup.find_all(selectors["card_tag"], class_=re.compile(selectors["card_class"], re.I))
    
    results = []
    for listing in listings:
        try:
            # Title
            title_elem = listing.find(selectors["title_tag"], class_=re.compile(selectors["title_class"] if selectors.get("title_class") else ""))
            if not title_elem: continue
            role_title = title_elem.text.strip()
            
            # Link
            link_elem = listing.find("a") if title_elem.name != "a" else title_elem
            apply_link = link_elem["href"] if link_elem and "href" in link_elem.attrs else ""
            if apply_link and apply_link.startswith("/"):
                apply_link = url_base + apply_link
                
            # Company
            comp_elem = listing.find(selectors["comp_tag"], class_=re.compile(selectors.get("comp_class", "")))
            company_name = comp_elem.text.strip() if comp_elem else "Unknown Company"
            
            # Location
            loc_elem = listing.find(selectors["loc_tag"], class_=re.compile(selectors.get("loc_class", "")))
            location = loc_elem.text.strip() if loc_elem else "India"
            location_type = "Remote" if "Remote" in location or "Work From Home" in location else "India"
            
            org_type = "Company"
            role_type = "Research" if "research" in role_title.lower() else "Applied"
            match_score = calculate_match_score(role_title, ["AI/ML"], org_type, 0.0)
            
            id_hash = hashlib.md5(f"{company_name}-{role_title}-{source_name}".encode()).hexdigest()
            
            results.append({
                "id": id_hash,
                "company_name": company_name,
                "role_title": role_title,
                "location": location,
                "location_type": location_type,
                "duration": "",
                "stipend": "",
                "stipend_numeric": 0.0,
                "stipend_currency": "INR",
                "required_skills": "AI/ML", 
                "application_deadline": "", 
                "apply_link": apply_link,
                "source_platform": source_name,
                "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                "org_type": org_type,
                "role_type": role_type,
                "match_score": match_score
            })
        except Exception as e:
            continue
            
    return results

# scrape_shine moved to sites/shine.py (Shine changed its page structure, Oct 2026)

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def scrape_foundit():
    results = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=get_playwright_stealth_args())
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            url = "https://www.foundit.in/srp/results?query=ai+ml+internship"
            page.goto(url, timeout=30000)
            human_delay(3.0, 6.0)
            
            selectors = {
                "card_tag": "div", "card_class": "job-tuple",
                "title_tag": "h3", "title_class": "",
                "comp_tag": "span", "comp_class": "company-name",
                "loc_tag": "div", "loc_class": "details"
            }
            results = parse_job_card(page.content(), selectors, "Foundit", "https://www.foundit.in")
            browser.close()
        except Exception as e:
            logger.error(f"Foundit error: {e}")
            raise e
    return results

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def scrape_apna():
    results = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=get_playwright_stealth_args())
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            url = "https://apna.co/jobs?category=internship&q=ai+ml"
            page.goto(url, timeout=30000)
            human_delay(4.0, 7.0)
            
            html = page.content()
            soup = BeautifulSoup(html, "lxml")
            
            # Apna has overlapping divs with data-testid='job-card' so we grab unique links
            cards = []
            for a in soup.find_all("a"):
                href = a.get("href", "")
                if href and "/job/" in href:
                    if a.find(attrs={"data-testid": "job-title"}):
                        cards.append(a)
                        
            for listing in cards:
                try:
                    title_elem = listing.find(attrs={"data-testid": "job-title"})
                    if not title_elem: continue
                    role_title = title_elem.text.strip()
                    
                    comp_elem = listing.find(attrs={"data-testid": "company-title"})
                    company_name = comp_elem.text.strip() if comp_elem else "Unknown Company"
                    
                    loc_elem = listing.find(attrs={"data-testid": "job-location"})
                    location = loc_elem.text.strip() if loc_elem else "India"
                    location_type = "Remote" if "Remote" in location or "Work From Home" in location else "India"
                    
                    sal_elem = listing.find(attrs={"data-testid": "job-salary"})
                    stipend = sal_elem.text.strip() if sal_elem else ""
                    
                    apply_link = "https://apna.co" + listing["href"] if "href" in listing.attrs else ""
                    
                    org_type = "Company"
                    role_type = "Research" if "research" in role_title.lower() else "Applied"
                    match_score = calculate_match_score(role_title, ["AI/ML"], org_type, 0.0)
                    
                    id_hash = hashlib.md5(f"{company_name}-{role_title}-Apna".encode()).hexdigest()
                    
                    results.append({
                        "id": id_hash,
                        "company_name": company_name,
                        "role_title": role_title,
                        "location": location,
                        "location_type": location_type,
                        "duration": "",
                        "stipend": stipend,
                        "stipend_numeric": 0.0,
                        "stipend_currency": "INR",
                        "required_skills": "AI/ML", 
                        "application_deadline": "", 
                        "apply_link": apply_link,
                        "source_platform": "Apna",
                        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                        "org_type": org_type,
                        "role_type": role_type,
                        "match_score": match_score
                    })
                except Exception as e:
                    continue
            browser.close()
        except Exception as e:
            logger.error(f"Apna error: {e}")
            raise e
    return results

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def scrape_cutshort():
    results = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=get_playwright_stealth_args())
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            url = "https://cutshort.io/jobs/ai-ml?type=internship"
            page.goto(url, timeout=30000)
            human_delay(3.0, 5.0)
            
            selectors = {
                "card_tag": "div", "card_class": "job-card",
                "title_tag": "div", "title_class": "title",
                "comp_tag": "div", "comp_class": "company",
                "loc_tag": "div", "loc_class": "location"
            }
            results = parse_job_card(page.content(), selectors, "Cutshort", "https://cutshort.io")
            browser.close()
        except Exception as e:
            logger.error(f"Cutshort error: {e}")
            raise e
    return results
