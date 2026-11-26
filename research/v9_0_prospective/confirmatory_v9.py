#!/usr/bin/env python3
"""My locked 260-item prospective confirmatory entrypoint; dry-run unless --execute."""
from __future__ import annotations

import argparse
from pathlib import Path

import pilot_b_v9

NUM_ITEMS = 260
BUDGET_CAP_USD = 1.25


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, default=None,
                        help="verified items_pool_v1.json; all 260 items are selected")
    parser.add_argument("--rates", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--resume-from", type=Path, default=None,
                        help="verified prior confirmatory result JSON")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--num-items", type=int, choices=(NUM_ITEMS,), default=NUM_ITEMS)
    parser.add_argument("--budget-usd", type=float, default=BUDGET_CAP_USD)
    parser.add_argument("--execute", action="store_true",
                        help="send requests after pool, rate, and key preflight")
    args = parser.parse_args(argv)
    if args.budget_usd <= 0 or args.budget_usd > BUDGET_CAP_USD:
        parser.error("--budget-usd must be positive and no more than 1.25")
    forwarded = ["--num-items", str(NUM_ITEMS), "--budget-usd", str(args.budget_usd),
                 "--timeout", str(args.timeout)]
    for flag, value in (("--items", args.items), ("--rates", args.rates), ("--output", args.output),
                        ("--resume-from", args.resume_from)):
        if value is not None:
            forwarded.extend((flag, str(value)))
    if args.execute:
        forwarded.append("--execute")
    return pilot_b_v9.main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
