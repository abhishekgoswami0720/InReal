"""Runs the scam check by hand.

    python -m moderation.pipeline --sample     # 3 made-up posts, nothing saved: is everything connected? how fast?
    python -m moderation.pipeline              # the posts waiting in the list, until nothing waits
    python -m moderation.pipeline --one        # one round of up to 10
"""
import argparse
import time

SAMPLES = [
    {"id": "sample_scam", "role_title": "Python Developer Intern", "company_name": "SkillRise Career Academy",
     "stipend": "₹25,000/month", "source_platform": "Sample", "apply_link": "https://example.com/apply", "trust_flags": "",
     "location": "Remote", "description": "Work from home Python internship. Certificate guaranteed. Pay a one-time registration "
     "fee of Rs 999 to confirm your seat. Contact HR on WhatsApp 9876543210 only. Limited seats, apply today."},
    {"id": "sample_real", "role_title": "Backend Intern", "company_name": "Razorpay", "stipend": "₹30,000/month",
     "source_platform": "Sample", "apply_link": "https://razorpay.com/jobs/", "trust_flags": "", "location": "Bengaluru",
     "description": "You will build and test payment APIs in Go and Python with the platform team, write unit tests, and take "
     "part in code reviews. Selection is through two technical interviews. We do not charge any fee at any stage."},
    {"id": "sample_unclear", "role_title": "Marketing Intern", "company_name": "Nexvia Technologies", "stipend": "Unpaid",
     "source_platform": "Sample", "apply_link": "https://forms.gle/abc123", "trust_flags": "", "location": "Remote",
     "description": "Help our team with social media posts and campus outreach. Training will be provided. Send your resume "
     "on Telegram to get selected quickly. Top performers get a certificate."},
]


def sample(with_agent: bool):
    from moderation.pipeline.config import settings
    from moderation.pipeline.runner import judge_posts
    cfg = settings()
    t = time.time()
    # the sample links are made up, so the link check is skipped here (a dead link would end the check
    # at "expired" before the AI ever sees the post); the real check opens every link
    from moderation.pipeline.rules import host_of
    fake_link = lambda url: {"link_state": "ok", "final_url": url, "final_domain": host_of(url), "chain": [url]}  # noqa: E731
    verdicts = judge_posts([dict(s) for s in SAMPLES], cfg, resolve=fake_link)
    print(f"\n3 sample posts checked in {time.time() - t:.1f}s (nothing saved)\n")
    for v in verdicts:
        print(f"  {v['id']:<15} {v['status']:<9} risk {v['scam_risk']}")
        for r in v["reasons"][:3]:
            print(f"      - {r[:140]}")
    if any(v["status"] == "retry" for v in verdicts):
        print("\n  'retry' = the AI could not be reached. Check the Azure values in .env: python -m moderation.check_azure")
    if not with_agent:
        return
    try:
        import langchain_openai  # noqa: F401
        import langgraph  # noqa: F401
    except ImportError:
        print("\nThe agent needs two more packages. Run:  pip install -r requirements.txt")
        return
    from moderation.pipeline.agent import second_look
    row = dict(SAMPLES[2], moderation_status="review", scam_risk="0.45",
               moderation_reasons=next(" | ".join(v["reasons"]) for v in verdicts if v["id"] == "sample_unclear"))
    print("\nSecond look by the agent at 'sample_unclear' (web search, ~20-40 s)...")
    t = time.time()
    out = second_look(row, cfg=cfg)
    print(f"  -> {out['status']} in {time.time() - t:.1f}s\n  {out['note']}")
    for ev in out.get("rejected") or []:
        print(f"  quote not found in {ev.get('source')}: \"{str(ev.get('quote'))[:120]}\"")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", action="store_true", help="3 made-up posts, nothing saved")
    ap.add_argument("--no-agent", action="store_true", help="with --sample: skip the agent's second look")
    ap.add_argument("--one", action="store_true", help="only one round")
    args = ap.parse_args()
    if args.sample:
        return sample(not args.no_agent)
    from moderation.pipeline.runner import check_waiting
    total = 0
    while True:
        res = check_waiting()
        print(res)
        total += res.get("checked", 0)
        if args.one or not res.get("checked"):
            break
    print(f"{total} checked. 'Needs a look' posts get a second look in the background only while the app runs.")


if __name__ == "__main__":
    main()
