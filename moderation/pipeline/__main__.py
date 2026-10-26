"""Runs the scam check by hand on whatever is waiting, then prints what it decided.

    python -m moderation.pipeline              # until nothing waits
    python -m moderation.pipeline --one        # one round of up to 10
"""
import argparse

from moderation.pipeline.runner import check_waiting


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--one", action="store_true", help="only one round")
    args = ap.parse_args()
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
