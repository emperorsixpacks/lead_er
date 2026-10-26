"""CLI to run pipeline stages manually (or from cron).

Usage:
  python scripts/run_pipeline.py discover
  python scripts/run_pipeline.py enrich <lead_id>
  python scripts/run_pipeline.py verify <lead_id>
  python scripts/run_pipeline.py personalize <lead_id>
  python scripts/run_pipeline.py send <lead_id>
  python scripts/run_pipeline.py run --limit 50
"""
import argparse
import asyncio

from app import pipeline


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the lead_er pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("discover")
    usda = sub.add_parser("usda")
    usda.add_argument("--limit", type=int, default=None)
    for c in ("enrich", "verify", "personalize", "send"):
        p = sub.add_parser(c)
        p.add_argument("lead_id")

    run = sub.add_parser("run")
    run.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()

    if args.cmd == "discover":
        print(await pipeline.discover())
    elif args.cmd == "usda":
        print(await pipeline.discover_usda(args.limit))
    elif args.cmd == "enrich":
        print(await pipeline.enrich_lead(args.lead_id))
    elif args.cmd == "verify":
        print(await pipeline.verify_lead(args.lead_id))
    elif args.cmd == "personalize":
        print(await pipeline.personalize_lead(args.lead_id))
    elif args.cmd == "send":
        print(await pipeline.send_lead(args.lead_id))
    elif args.cmd == "run":
        print(await pipeline.run_pipeline(args.limit))


if __name__ == "__main__":
    asyncio.run(main())
