import argparse
import csv
import re
from pathlib import Path

from loguru import logger
from output_handler import sync_listings, update_run_history
from filters import internship_rejection_reason, stipend_rejection_reason
from genuine import check_listing

# Import scrapers
from sites.internshala import scrape_internshala
from sites.unstop import scrape_unstop
from sites.naukri import scrape_naukri
from sites.government import scrape_government
from sites.misc_india import scrape_cutshort
from sites.apna import scrape_apna
from sites.foundit import scrape_foundit
from sites.shine import scrape_shine
from sites.international import scrape_international
from sites.rss_feeds import scrape_linkedin as scrape_remotive, scrape_indeed as scrape_weworkremotely
from sites.linkedin import scrape_linkedin  # NEW: direct LinkedIn Jobs page scraper
from sites.bigtech import scrape_bigtech
from sites.niche import scrape_niche_boards, scrape_aggregators
from sites.universities import scrape_universities
from sites.search_engine import scrape_search_engine

# Sites whose scrapers were rebuilt and checked against the live site (see SELECTOR_TRACKER.md)
UPGRADED_SOURCES = ["internshala", "unstop", "naukri", "linkedin", "shine", "foundit", "apna", "government"]

ALL_SCRAPERS = {
    "internshala": scrape_internshala,
    "unstop": scrape_unstop,
    "naukri": scrape_naukri,
    "shine": scrape_shine,
    "foundit": scrape_foundit,
    "apna": scrape_apna,
    "cutshort": scrape_cutshort,
    "linkedin": scrape_linkedin,
    "bigtech": scrape_bigtech,
    "remotive": scrape_remotive,
    "weworkremotely": scrape_weworkremotely,
    "international": scrape_international,
    "niche": scrape_niche_boards,
    "aggregators": scrape_aggregators,
    "search": scrape_search_engine,
    "government": scrape_government,
    "universities": scrape_universities,
}

logger.add("scraper_errors.log", rotation="1 MB", level="ERROR")
# Human-readable logs for the UI
logger.add("scraper_run.log", rotation="5 MB", level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {message}")

# Pay hidden by the site but the post itself says it is unpaid (seen on Shine, Oct 2026)
UNPAID_RE = r"\b(unpaid|non[- ]?paid|without (a )?stipend|no stipend)\b"


def _region(location: str) -> str:
    """'Amreli, Gujarat, India' -> 'gujarat'; 'San Francisco, CA' -> 'ca'."""
    parts = [p.strip().lower() for p in str(location).split(",") if p.strip()]
    if len(parts) >= 3:
        return parts[-2]
    return parts[-1] if parts else ""


def mark_repeated_posts(raw_listings: list):
    """
    Same company + same title posted in 3+ places. Big companies do this across
    major cities (DoorDash: SF, Sunnyvale, NYC, Seattle), so it is only flagged when
    the places are all in one state (Sparks To Ideas: 4 small towns in Gujarat, while
    the work is in Ahmedabad) or a copy of the post is known to be aggregated or
    from a staffing firm.
    """
    groups = {}
    for item in raw_listings:
        key = (str(item.get("company_name", "")).strip().lower(), str(item.get("role_title", "")).strip().lower())
        groups.setdefault(key, []).append(item)
    for items in groups.values():
        places = {str(i.get("location", "")).strip().lower() for i in items}
        if len(places) < 3:
            continue
        regions = {_region(pl) for pl in places}
        evidence = any(i.get("aggregated") or "staffing" in str(i.get("industries", "")).lower() for i in items)
        if len(regions) == 1 or evidence:
            where = f"towns of {_region(next(iter(places))).title()}" if len(regions) == 1 else "locations"
            for i in items:
                i["repeat_note"] = f"Same post repeated in {len(places)} {where}"


# An "internship" that needs this many years of experience is a job (Naukri, Oct 2026: "4-to-9 years")
MAX_MIN_EXPERIENCE = 3


def evaluate(source_name: str, raw_listings: list):
    """
    Runs every filter on every listing.
    Returns a list of (item, kept: bool, reason: str).
    """
    mark_repeated_posts(raw_listings)

    results = []
    for item in raw_listings:
        skills = item.get("required_skills", "")
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]

        reason = internship_rejection_reason(item["role_title"], skill_list, source_name,
                                             bool(item.get("labelled_internship")))
        min_exp = item.get("min_experience")
        if reason is None and isinstance(min_exp, (int, float)) and min_exp >= MAX_MIN_EXPERIENCE:
            reason = f"Asks for {int(min_exp)}+ years of experience"
        if reason is None:
            is_india = item.get("stipend_currency") == "INR" or item.get("location_type") == "India"
            reason = stipend_rejection_reason(item["stipend"], item["stipend_numeric"], is_india)
        if reason is None:
            said = re.search(UNPAID_RE, f"{item.get('role_title', '')} {item.get('description', '')}", re.I)
            if said and not re.search(r"\bnot\s+(an?\s+)?$", f"{item.get('role_title', '')} {item.get('description', '')}"[:said.start()][-12:], re.I):
                reason = f"Unpaid (the post says \"{said.group(0)}\")"
        if reason is None:
            reason, flags = check_listing(item)
            if HIDDEN_COMPANY_RE.match(str(item.get("company_name", "")).strip()):
                flags.append("Company name hidden")
            item["trust_flags"] = "; ".join(flags)
        results.append((item, reason is None, reason or ""))
    return collapse_copies(results)


# Company names portals print when the employer hides it ("**********", "Confidential")
HIDDEN_COMPANY_RE = re.compile(r"^(\*+|confidential|hidden|undisclosed|not disclosed)$", re.I)
COPY_LIMIT = 3      # 3+ copies are shown once
COPY_WARNING = 6    # 6+ copies also get a warning
_TITLE_NOISE = {"internship", "internships", "intern", "interns", "at", "an", "in", "the", "for", "and", "of", "with"}


def _company_key(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    n = re.sub(r"\b(private|pvt|limited|ltd|llp|inc|technologies|technology|solutions)\b", " ", n)
    return " ".join(n.split())


def _title_key(title: str) -> str:
    """First two meaningful words: 'DATA SCIENCE -ML INTERNSHIP AT PUNE' -> 'data science'."""
    words = [w for w in re.findall(r"[a-z]+", str(title).lower()) if w not in _TITLE_NOISE]
    return " ".join(words[:2])


def collapse_copies(results):
    """
    One company posting the same internship many times (Foundit, 12 Oct 2026: Maxgen
    posted "DATA SCIENCE INTERNSHIP AT PUNE/AHMEDABAD" about 40 times with different
    town lists) floods the list. Keep the first copy, drop the rest, and give the kept
    one every warning found on any copy plus a count.
    """
    groups = {}
    for idx, (item, kept, _) in enumerate(results):
        if kept:
            key = (_company_key(item.get("company_name", "")), _title_key(item.get("role_title", "")))
            groups.setdefault(key, []).append(idx)
    for idxs in groups.values():
        if len(idxs) < COPY_LIMIT:
            continue
        first = results[idxs[0]][0]
        flags = []
        for i in idxs:
            for f in str(results[i][0].get("trust_flags", "")).split(";"):
                if f.strip() and f.strip() not in flags:
                    flags.append(f.strip())
        if len(idxs) >= COPY_WARNING:   # big firms post one role in a few cities; dozens is a flood
            flags.append(f"Same company posted {len(idxs)} copies of this internship")
        first["trust_flags"] = "; ".join(flags)
        first["location"] = f"{first.get('location', '')} (+{len(idxs) - 1} more)"
        for i in idxs[1:]:
            item = results[i][0]
            results[i] = (item, False, f"Copy of another post by the same company ({len(idxs)} copies)")
    return results


def process_and_save(source_name: str, raw_listings: list):
    results = evaluate(source_name, raw_listings)
    valid_listings = [item for item, kept, _ in results if kept]
    dropped_ids = [item["id"] for item, kept, _ in results if not kept and item.get("id")]

    res = sync_listings(valid_listings, dropped_ids)
    if not valid_listings:
        logger.info(f"[{source_name}] Searched through {len(raw_listings)} listings, but none matched our criteria.")
    extra = []
    if res["updated"]:
        extra.append(f"refreshed {res['updated']} already saved")
    if res["removed"]:
        extra.append(f"removed {res['removed']} that no longer pass the checks")
    logger.info(f"[{source_name}] Analyzed {len(raw_listings)} listings, found {len(valid_listings)} matches, "
                f"and saved {res['added']} brand new ones!" + (f" ({', '.join(extra)})" if extra else ""))
    return res["added"]


TEST_COLUMNS = ["status", "reason", "trust_flags", "role_title", "company_name", "stipend",
                "duration", "location", "posted", "employer_since", "employer_posted",
                "employer_hired", "openings", "required_skills", "apply_link"]


def report_dry_run(source_name: str, raw_listings: list):
    """Prints what would be kept or dropped and why, and writes test_output/<source>.csv."""
    results = evaluate(source_name, raw_listings)
    kept = [r for r in results if r[1]]
    dropped = [r for r in results if not r[1]]

    out_dir = Path(__file__).parent / "test_output"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{source_name}.csv"
    with open(out_file, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=TEST_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for item, ok, reason in sorted(results, key=lambda r: not r[1]):
            w.writerow({**item, "status": "KEPT" if ok else "DROPPED", "reason": reason})

    reasons = {}
    for _, _, reason in dropped:
        key = reason.split("(")[0].split(":")[0].strip()
        reasons[key] = reasons.get(key, 0) + 1

    print()
    print("=" * 70)
    print(f" {source_name.upper()} TEST: {len(raw_listings)} scraped -> {len(kept)} kept, {len(dropped)} dropped")
    print("=" * 70)
    for key, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  dropped {n:>4}  {key}")
    print("-" * 70)
    for item, _, _ in kept[:15]:
        flags = f"  [!] {item.get('trust_flags')}" if item.get("trust_flags") else ""
        print(f"  {item['role_title'][:32]:<32} | {item['company_name'][:22]:<22} | {item['stipend'][:22]}{flags}")
    if len(kept) > 15:
        print(f"  ... and {len(kept) - 15} more")
    for item, _, reason in dropped:
        if not reason.startswith(("Not an AI/ML", "Unpaid", "Stipend below", "Not labelled", "Title has")):
            print(f"  DROPPED {item['role_title'][:28]:<28} | {item['company_name'][:20]:<20} | {reason[:70]}")
    print("-" * 70)
    print(f"  Full list with reasons: {out_file}")
    print("=" * 70)


def run_scrapers(dry_run=False, config=None, specific_source=None):
    total_added = 0
    failed_sources = []
    
    # Default to everything if no config passed
    if config is None:
        config = {
            "regions": ["india", "worldwide", "usa", "europe", "remote"],
            "topics": ["ml", "ai", "nlp", "cv", "ds", "research", "llm/genai"],
            "paid_only": False,
            "sources": UPGRADED_SOURCES
        }
    
    logger.info(f"🚀 Starting selective scraper with config: {config}")
    
    # Clear old popup alerts from a previous run
    from pathlib import Path
    alert_file = Path(__file__).parent / "scraper_alerts.json"
    if alert_file.exists():
        try:
            alert_file.unlink()
        except OSError:
            pass
    
    req_regions = set([r.lower() for r in config.get("regions", [])])
    req_sources = set([s.lower() for s in config.get("sources", [])])
    
    scrapers_to_run = {}

    # Each dashboard checkbox is now one site (its --source name). The old group
    # names still work so old saved settings don't break, but "naukri" means only
    # Naukri now; it used to also start Shine, Foundit, Apna and Cutshort.
    legacy_groups = {
        "remotive": ["remotive", "weworkremotely", "international", "niche", "aggregators", "search"],
    }
    for name in [s.lower() for s in config.get("sources", [])]:
        for source in legacy_groups.get(name, [name]):
            if source in ALL_SCRAPERS:
                scrapers_to_run[source] = ALL_SCRAPERS[source]
            else:
                logger.warning(f"Unknown source in dashboard settings: {source}")

    if specific_source:
        wanted = [x.strip().lower() for x in specific_source.split(",") if x.strip()]
        unknown = [x for x in wanted if x not in ALL_SCRAPERS]
        if unknown:
            logger.error(f"Unknown source(s): {unknown}. Choose from: {', '.join(ALL_SCRAPERS)}")
            return 0
        scrapers_to_run = {name: ALL_SCRAPERS[name] for name in wanted}

    if not scrapers_to_run:
        logger.warning("No scrapers matched the provided configuration filters!")
        return 0

    for source_name, scraper_func in scrapers_to_run.items():
        try:
            logger.info(f"🚀 Starting to check {source_name} for new opportunities...")
            if source_name in ["linkedin", "search"]:
                listings = scraper_func(config=config)
            else:
                listings = scraper_func()
            if not dry_run:
                added = process_and_save(source_name, listings)
                total_added += added
            else:
                report_dry_run(source_name, listings)
        except Exception as e:
            logger.exception(f"Failed {source_name}: {e}")
            failed_sources.append(source_name)
            
    if not dry_run:
        update_run_history(total_added, failed_sources)
        
    logger.info("========================================")
    logger.info("✅ All scraping tasks completed!")
    logger.info(f"Sources checked: {len(scrapers_to_run) - len(failed_sources)} successful, {len(failed_sources)} failed.")
    if not dry_run:
        logger.info(f"🎉 Total new internships added today: {total_added}")
    logger.info("========================================")
    return total_added

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated AI/ML Internship Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Run scrapers without saving to CSV")
    parser.add_argument("--source", type=str,
                        help="Run only these sources, comma separated, e.g. internshala or internshala,unstop")
    args = parser.parse_args()
    
    run_scrapers(dry_run=args.dry_run, specific_source=args.source)
