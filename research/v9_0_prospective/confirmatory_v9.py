#!/usr/bin/env python3
"""My locked 260-item prospective confirmatory entrypoint; dry-run unless --execute."""
from __future__ import annotations

import argparse
from pathlib import Path

import pilot_b_v9

NUM_ITEMS = 260
BUDGET_CAP_USD = 1.25
LOCAL_SLOTS = ("qwen_7b", "gemma_9b", "llama_8b", "mistral_7b")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("openrouter", "local-hf"), default="openrouter",
                        help="OpenRouter API or local Hugging Face 4-bit GPU inference")
    parser.add_argument("--slot", choices=LOCAL_SLOTS, default=None,
                        help="local-hf model family to run; one slot per durable checkpoint")
    parser.add_argument("--items", type=Path, default=None,
                        help="verified items_pool_v1.json; all 260 items are selected")
    parser.add_argument("--rates", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--resume-from", type=Path, default=None,
                        help="verified prior confirmatory result JSON or local-HF slot checkpoint")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--num-items", type=int, choices=(NUM_ITEMS,), default=NUM_ITEMS)
    parser.add_argument("--budget-usd", type=float, default=BUDGET_CAP_USD)
    parser.add_argument("--execute", action="store_true",
                        help="run the selected backend after preflight")
    args = parser.parse_args(argv)

    if args.backend == "local-hf":
        if args.budget_usd != BUDGET_CAP_USD:
            parser.error("--budget-usd only applies to OpenRouter; local-hf reports USD 0.00 model API spend")
        if args.resume_from is not None and args.slot is None:
            parser.error("--resume-from with local-hf requires --slot")
        if args.execute and args.slot is None:
            parser.error("--execute --backend local-hf requires --slot; run one model family per session")
        from local_hf_confirmatory_v9 import main as local_hf_main

        forwarded: list[str] = []
        for flag, value in (("--items", args.items), ("--output", args.output),
                            ("--resume-from", args.resume_from), ("--slot", args.slot)):
            if value is not None:
                forwarded.extend((flag, str(value)))
        if args.execute:
            forwarded.append("--execute")
        return local_hf_main(forwarded)

    if args.slot is not None:
        parser.error("--slot is supported only with --backend local-hf")
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
