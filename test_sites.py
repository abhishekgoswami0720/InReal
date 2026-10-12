"""
Tests every site once, one after another, WITHOUT saving anything to internships.csv.

    python test_sites.py                      # the 8 dashboard sites
    python test_sites.py naukri foundit       # only these
    python test_sites.py --all                # every scraper in scraper.py

Each site runs as its own `python scraper.py --dry-run --source <site>`, so one crash can't stop the
rest. Results:
    test_output/<site>.csv          every listing with KEPT / DROPPED and the reason
    test_output/_logs/<site>.log    the full terminal output of that site
    test_output/_summary.txt        one line per site (also printed at the end)
Naukri and Foundit open a visible Chrome: if a check page appears, solve it there.
"""
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "test_output"
LOGS = OUT / "_logs"
TIMEOUT_S = 8 * 60


def sites_to_test(argv):
    from scraper import ALL_SCRAPERS, UPGRADED_SOURCES
    if "--all" in argv:
        return list(ALL_SCRAPERS)
    picked = [a.lower() for a in argv if not a.startswith("-")]
    unknown = [s for s in picked if s not in ALL_SCRAPERS]
    if unknown:
        sys.exit(f"Unknown site(s): {unknown}. Choose from: {', '.join(ALL_SCRAPERS)}")
    return picked or list(UPGRADED_SOURCES)


def run_site(site):
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"{site}.log"
    t = time.time()
    try:
        proc = subprocess.run([sys.executable, "scraper.py", "--dry-run", "--source", site], cwd=ROOT,
                              capture_output=True, text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"}, encoding="utf-8", errors="replace", timeout=TIMEOUT_S)
        text, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        text = (e.stdout or "") + (e.stderr or "") if isinstance(e.stdout, str) else ""
        text += f"\nTIMEOUT after {TIMEOUT_S}s"
        code = "timeout"
    secs = time.time() - t
    log.write_text(text, encoding="utf-8")

    m = re.search(r"TEST: (\d+) scraped -> (\d+) kept, (\d+) dropped", text)
    warnings = len(re.findall(r"\| WARNING ", text))
    if m:
        scraped, kept, dropped = map(int, m.groups())
        status = "OK" if kept else ("EMPTY" if scraped == 0 else "ALL DROPPED")
        detail = f"{scraped} scraped, {kept} kept, {dropped} dropped"
    else:
        status = "TIMEOUT" if code == "timeout" else "FAILED"
        errs = [l for l in text.splitlines() if re.search(r"Error|Exception|Failed|ERROR", l)]
        detail = (errs[-1].strip() if errs else f"exit code {code}, no result line")[:160]
    if warnings:
        detail += f"  ({warnings} warnings in log)"
    return f"{site:<14} {status:<12} {secs:6.0f}s  {detail}"


def main():
    sites = sites_to_test(sys.argv[1:])
    OUT.mkdir(exist_ok=True)
    lines = [f"Site test {datetime.now():%Y-%m-%d %H:%M}  (dry run, nothing saved)"]
    print(lines[0])
    for i, site in enumerate(sites, 1):
        print(f"[{i}/{len(sites)}] {site} ...", flush=True)
        line = run_site(site)
        print("   " + line, flush=True)
        lines.append(line)
        (OUT / "_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")   # saved after each site
    print("\n" + "\n".join(lines))
    print(f"\nDetails: {OUT / '_summary.txt'}, test_output/<site>.csv, test_output/_logs/<site>.log")


if __name__ == "__main__":
    main()
