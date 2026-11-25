#!/usr/bin/env python3
"""Prospective Pilot B v9; fail-closed pool verification and $0.25 estimate cap.

This is a dry-run unless --execute is supplied. The frozen item-pool hash and
schema are checked before API environment variables are read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_ping_check_v9 import (
    CANDIDATES,
    ENV_BY_PROVIDER,
    KEYLIKE_RE,
    _payload,
    execute_request,
    normalize_response,
)

EXPECTED_ITEMS_POOL_SHA256 = (
    "128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3"
)
DEFAULT_BUDGET_USD = 0.25
MAX_BUDGET_USD = 0.25
MAX_TOKENS = {
    "phase0_harvest": 128,
    "utility_perturb": 128,
    "utility_style_scrub": 128,
    "phase1_digit_evaluation": 16,
    "domain2_digit_evaluation": 16,
}


class SpendGuard:
    """Reserve a conservative per-call estimated cost before sending."""

    def __init__(self, cap_usd: float) -> None:
        self.cap_usd = cap_usd
        self.reserved_usd = 0.0

    @staticmethod
    def prompt_upper_bound(messages: list[dict[str, str]]) -> int:
        # UTF-8 byte count plus provider framing headroom; no tokenizer is loaded.
        return sum(len(msg["content"].encode("utf-8")) for msg in messages) + 64 * len(messages)

    def reserve(
        self,
        messages: list[dict[str, str]],
        output_limit: int,
        input_rate: float,
        output_rate: float,
    ) -> tuple[int, float] | None:
        input_upper = self.prompt_upper_bound(messages)
        output_upper = output_limit * 2
        amount = (input_upper * input_rate + output_upper * output_rate) / 1_000_000
        if self.reserved_usd + amount > self.cap_usd:
            return None
        self.reserved_usd += amount
        return input_upper, amount

    def settle(
        self,
        reservation: float,
        input_tokens: int | None,
        output_tokens: int | None,
        input_rate: float,
        output_rate: float,
    ) -> float:
        if input_tokens is None or output_tokens is None:
            return reservation
        observed = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
        if observed > reservation:
            self.reserved_usd += observed - reservation
        return observed


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_items(path: Path) -> tuple[str, list[dict[str, Any]]]:
    if not path.is_file():
        raise ValueError(
            f"BLOCKED: items_pool_v1.json missing at {path}; no API keys read or calls sent"
        )
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_ITEMS_POOL_SHA256:
        raise ValueError("BLOCKED: frozen items_pool_v1.json SHA-256 mismatch")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("BLOCKED: matching pool bytes are not valid UTF-8 JSON") from None
    fields = {"item_id", "category", "prompt_text"}
    valid = (
        isinstance(data, list)
        and len(data) == 260
        and all(isinstance(item, dict) and set(item) == fields for item in data)
        and len({str(item["item_id"]) for item in data}) == 260
        and all(isinstance(item["prompt_text"], str) and item["prompt_text"].strip() for item in data)
    )
    if not valid:
        raise ValueError("BLOCKED: pool hash matched but required 260-item schema did not")
    return actual, data[:5]


def load_rate_card(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("BLOCKED: model_rates_v9.json is missing or invalid") from None
    if document.get("currency") != "USD" or not isinstance(document.get("models"), dict):
        raise ValueError("BLOCKED: rate-card schema is invalid")
    rates: dict[str, dict[str, Any]] = {}
    for spec in CANDIDATES:
        row = document["models"].get(spec["provider"])
        if not isinstance(row, dict) or row.get("model_id") != spec["model_id"]:
            raise ValueError(f"BLOCKED: no matching rate for {spec['provider']}")
        try:
            in_rate = float(row["input_usd_per_1m_tokens"])
            out_rate = float(row["output_usd_per_1m_tokens"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"BLOCKED: invalid rate for {spec['provider']}") from None
        if in_rate < 0 or out_rate < 0:
            raise ValueError(f"BLOCKED: negative rate for {spec['provider']}")
        rates[spec["provider"]] = {
            "model_id": spec["model_id"],
            "input_usd_per_1m_tokens": in_rate,
            "output_usd_per_1m_tokens": out_rate,
            "source": str(row.get("source", "")),
        }
    return rates, str(document.get("pricing_snapshot_date", "unknown"))


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _fingerprint(text: str) -> dict[str, Any]:
    return {
        "raw_text_empty": not text.strip(),
        "raw_text_chars": len(text),
        "raw_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _save(report: dict[str, Any], path: Path, secrets: list[str]) -> None:
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if any(secret and secret in encoded for secret in secrets) or KEYLIKE_RE.search(encoded):
        raise RuntimeError("Refusing to save: credential-like content detected.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(encoded, encoding="utf-8")
    temp.replace(path)


def run_stage(
    spec: dict[str, str],
    api_key: str,
    item_id: str,
    stage: str,
    messages: list[dict[str, str]],
    timeout: int,
    rate: dict[str, Any],
    guard: SpendGuard,
    report: dict[str, Any],
    checkpoint: Any,
) -> tuple[dict[str, Any], str]:
    output_cap = MAX_TOKENS[stage]
    reserved = guard.reserve(
        messages,
        output_cap,
        rate["input_usd_per_1m_tokens"],
        rate["output_usd_per_1m_tokens"],
    )
    if reserved is None:
        row = {
            "call_id": f"pilot-{len(report['calls']) + 1:04d}",
            "provider": spec["provider"], "model_id": spec["model_id"],
            "item_id": item_id, "stage": stage,
            "request_state": "not_started_budget_cap",
            "http_call_started": False, "http_status": None,
            "latency_ms": 0, "available": False,
            "error_category": "pre_request_spend_cap",
            "input_tokens": None, "output_tokens": None,
            "estimated_usd": 0.0, "budget_reservation_usd": 0.0,
        }
        report["calls"].append(row)
        checkpoint()
        return row, ""
    input_upper, reservation = reserved

    call_id = f"pilot-{len(report['calls']) + 1:04d}"
    request_body = _payload(spec, messages, output_cap, None)
    attempt: dict[str, Any] = {
        "call_id": call_id,
        "provider": spec["provider"], "model_id": spec["model_id"],
        "item_id": item_id, "stage": stage,
        "request_state": "started", "http_call_started": True,
        "started_utc": utc_now(), "http_status": None,
        "prompt_sha256": hashlib.sha256(
            json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "request_body_sha256": hashlib.sha256(
            json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "reserved_input_tokens_upper_bound": input_upper,
        "budget_reservation_usd": reservation,
    }
    report["calls"].append(attempt)
    checkpoint()

    response = execute_request(
        spec, api_key, messages, output_cap, timeout_seconds=timeout
    )
    data = normalize_response(spec["provider"], response.get("payload"))
    text = str(data.get("raw_text") or "")
    blockers = []
    if response.get("http_status") != 200:
        blockers.append("http_status_not_200")
    if not text.strip():
        blockers.append("raw_text_empty")
    if data.get("finish_reason") == "length":
        blockers.append("finish_reason_length")
    reasoning = data.get("reasoning_tokens")
    if reasoning is not None and reasoning > 0:
        blockers.append("reasoning_tokens_positive")
    word_count = len(text.split()) if stage == "utility_style_scrub" else None
    if stage == "utility_style_scrub" and not 45 <= (word_count or 0) <= 55:
        blockers.append("style_scrub_word_count_out_of_range")
    digit = None
    if stage in {"phase1_digit_evaluation", "domain2_digit_evaluation"}:
        digit = text.strip() if text.strip() in {"0", "1"} else None
        if digit is None:
            blockers.append("evaluation_not_single_digit")
    in_tokens = data.get("input_tokens")
    out_tokens = data.get("output_tokens")
    cost = guard.settle(
        reservation,
        in_tokens,
        out_tokens,
        rate["input_usd_per_1m_tokens"],
        rate["output_usd_per_1m_tokens"],
    )
    row: dict[str, Any] = {
        "call_id": call_id,
        "request_state": "http_response_received" if response.get("http_status") is not None else "no_http_response",
        "http_call_started": True,
        "started_utc": attempt["started_utc"],
        "completed_utc": utc_now(),
        "provider": spec["provider"], "model_id": spec["model_id"],
        "item_id": item_id,
        "stage": stage,
        "http_status": response.get("http_status"),
        "latency_ms": response.get("latency_ms"),
        "available": not blockers,
        "availability_blockers": blockers,
        "error_category": response.get("error_category"),
        **_fingerprint(text),
        "finish_reason": data.get("finish_reason"),
        "reasoning_tokens": reasoning,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "total_tokens": data.get("total_tokens"),
        "reserved_input_tokens_upper_bound": input_upper,
        "estimated_usd": cost,
        "budget_reservation_usd": reservation,
    }
    if word_count is not None:
        row["style_scrub_word_count"] = word_count
    if stage in {"phase1_digit_evaluation", "domain2_digit_evaluation"}:
        row["evaluation_digit"] = digit
    report["calls"][-1] = row
    checkpoint()
    return row, text


def _aggregate(
    calls: list[dict[str, Any]],
    rates: dict[str, dict[str, Any]],
    items_count: int,
    stopped: bool,
) -> list[dict[str, Any]]:
    summaries = []
    for spec in CANDIDATES:
        rows = [c for c in calls if c.get("provider") == spec["provider"]]
        in_values = [c["input_tokens"] for c in rows if c.get("input_tokens") is not None]
        out_values = [c["output_tokens"] for c in rows if c.get("output_tokens") is not None]
        complete = len(rows) == items_count * 5 and all(c.get("available") for c in rows)
        rate = rates[spec["provider"]]
        summaries.append(
            {
                "provider": spec["provider"],
                "model_id": spec["model_id"],
                "available": complete,
                "complete_pipeline": complete,
                "calls_recorded": len(rows),
                "calls_expected": items_count * 5,
                "input_tokens": sum(in_values),
                "output_tokens": sum(out_values),
                "usage_missing_calls": len(rows) - min(len(in_values), len(out_values)),
                "latency_ms": sum(int(c.get("latency_ms") or 0) for c in rows),
                "estimated_usd": round(sum(float(c.get("estimated_usd") or 0) for c in rows), 10),
                "input_usd_per_1m_tokens": rate["input_usd_per_1m_tokens"],
                "output_usd_per_1m_tokens": rate["output_usd_per_1m_tokens"],
                "halted_early": stopped and not complete,
            }
        )
    return summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, default=repo_root() / "items_pool_v1.json")
    parser.add_argument("--rates", type=Path, default=Path(__file__).resolve().parent / "model_rates_v9.json")
    parser.add_argument("--budget-usd", type=float, default=DEFAULT_BUDGET_USD)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent / "results" / f"pilot_b_v9_{stamp}.json")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--execute", action="store_true",
                        help="send requests after pool, rate, and key preflight")
    args = parser.parse_args(argv)
    if args.budget_usd <= 0 or args.budget_usd > MAX_BUDGET_USD:
        print("BLOCKED: budget must be positive and no more than USD 0.25")
        return 2
    try:
        pool_hash, items = load_items(args.items)
        rates, pricing_date = load_rate_card(args.rates)
    except ValueError as exc:
        print(str(exc))
        return 2
    if not args.execute:
        print(
            "DRY RUN: frozen pool verified; first five items selected; "
            "planned calls=100; no keys read and no HTTP requests sent."
        )
        return 0
    if args.timeout < 1:
        print("BLOCKED: timeout must be at least 1 second")
        return 2
    if args.output.exists():
        print("BLOCKED: output exists; refusing to overwrite a prior run")
        return 2

    missing = sorted({s["env_var"] for s in CANDIDATES if not os.environ.get(s["env_var"])})
    if missing:
        print("BLOCKED: missing required environment variables: " + ", ".join(missing))
        return 2
    keys = {name: os.environ[name] for name in ENV_BY_PROVIDER.values()}
    guard = SpendGuard(args.budget_usd)
    report: dict[str, Any] = {
        "schema": "designlab-v9-pilot-b-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "run_classification": "prospective_pilot_b_not_confirmatory_study",
        "confirmatory_data_collected": False,
        "item_pool_sha256": pool_hash,
        "item_pool_file": str(args.items.resolve()),
        "selected_first_items": [
            {
                "item_id": str(item["item_id"]),
                "category": str(item["category"]),
                "item_sha256": hashlib.sha256(
                    json.dumps(item, sort_keys=True, ensure_ascii=False).encode("utf-8")
                ).hexdigest(),
            }
            for item in items
        ],
        "planned_pipeline": [
            "phase0_harvest", "utility_perturb", "utility_style_scrub",
            "phase1_digit_evaluation", "domain2_digit_evaluation",
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "evaluation_max_tokens": 16,
        "budget_cap_usd": args.budget_usd,
        "pricing_snapshot_date": pricing_date,
        "budget_method": "pre-request UTF-8 byte and output-token reservation at versioned rate card",
        "http_calls_started": 0,
        "http_responses_received": 0,
        "budget_reserved_usd": 0.0,
        "total_estimated_usd": 0.0,
        "stopped_early": False,
        "halt_reason": None,
        "calls": [],
        "per_model_summary": [],
    }

    def checkpoint() -> None:
        report["http_calls_started"] = sum(
            1 for call in report["calls"] if call.get("http_call_started")
        )
        report["http_responses_received"] = sum(
            1 for call in report["calls"]
            if call.get("request_state") == "http_response_received"
        )
        report["budget_reserved_usd"] = round(guard.reserved_usd, 10)
        report["total_estimated_usd"] = round(
            sum(float(c.get("estimated_usd") or 0) for c in report["calls"]), 10
        )
        _save(report, args.output, list(keys.values()))

    checkpoint()

    stopped = False
    try:
        for spec in CANDIDATES:
            rate = rates[spec["provider"]]
            api_key = keys[spec["env_var"]]
            failed = False
            for item in items:
                item_id = str(item["item_id"])
                prompt = item["prompt_text"]
                stage_specs: list[tuple[str, list[dict[str, str]]]] = [
                    (
                        "phase0_harvest",
                        _messages(
                            "Answer the research item directly and concisely. Return only the answer.",
                            prompt,
                        ),
                    ),
                ]
                for stage, messages in stage_specs:
                    row, harvested = run_stage(
                        spec, api_key, item_id, stage, messages, args.timeout, rate, guard,
                        report, checkpoint,
                    )
                    row.update(provider=spec["provider"], model_id=spec["model_id"])
                    if not row["available"]:
                        if row.get("error_category") == "pre_request_spend_cap":
                            report["stopped_early"] = True
                            report["halt_reason"] = "estimated spend cap reached before request"
                            stopped = True
                        failed = True
                        break
                if failed:
                    break

                perturb_messages = _messages(
                    "Make a small utility-preserving wording perturbation. Keep task-relevant "
                    "facts and answer unchanged. Return only the perturbed answer.",
                    "Research item:\n" + prompt + "\n\nHarvested answer:\n" + harvested,
                )
                row, perturbed = run_stage(
                    spec, api_key, item_id, "utility_perturb", perturb_messages,
                    args.timeout, rate, guard, report, checkpoint,
                )
                row.update(provider=spec["provider"], model_id=spec["model_id"])
                if not row["available"]:
                    if row.get("error_category") == "pre_request_spend_cap":
                        report["stopped_early"] = True
                        report["halt_reason"] = "estimated spend cap reached before request"
                        stopped = True
                    failed = True
                    break

                scrub_messages = _messages(
                    "Neutralize stylistic framing in 45 to 55 whitespace-delimited words. "
                    "Preserve the perturbed answer's task utility and facts. Return only text.",
                    "Research item:\n" + prompt + "\n\nPerturbed answer:\n" + perturbed,
                )
                row, scrubbed = run_stage(
                    spec, api_key, item_id, "utility_style_scrub", scrub_messages,
                    args.timeout, rate, guard, report, checkpoint,
                )
                row.update(provider=spec["provider"], model_id=spec["model_id"])
                if not row["available"]:
                    if row.get("error_category") == "pre_request_spend_cap":
                        report["stopped_early"] = True
                        report["halt_reason"] = "estimated spend cap reached before request"
                        stopped = True
                    failed = True
                    break

                evaluations = [
                    (
                        "phase1_digit_evaluation",
                        "Is the scrubbed answer still a useful answer to the item? Return 1 if yes, 0 if no.",
                    ),
                    (
                        "domain2_digit_evaluation",
                        "Did the scrub remove noticeable style while preserving utility? Return 1 if both, 0 otherwise.",
                    ),
                ]
                for stage, rubric in evaluations:
                    messages = _messages(
                        "Follow the rubric. Return exactly one ASCII digit and no other text.",
                        rubric + "\n\nResearch item:\n" + prompt
                        + "\n\nHarvested answer:\n" + harvested
                        + "\n\nScrubbed answer:\n" + scrubbed,
                    )
                    row, _ = run_stage(
                        spec, api_key, item_id, stage, messages, args.timeout, rate, guard,
                        report, checkpoint,
                    )
                    row.update(provider=spec["provider"], model_id=spec["model_id"])
                    if not row["available"]:
                        if row.get("error_category") == "pre_request_spend_cap":
                            report["stopped_early"] = True
                            report["halt_reason"] = "estimated spend cap reached before request"
                            stopped = True
                        failed = True
                        break
                if failed:
                    break
            if stopped:
                break
            if failed:
                report.setdefault("provider_failures", []).append(spec["provider"])
    except KeyboardInterrupt:
        report["stopped_early"] = True
        report["halt_reason"] = "interrupted by operator"
        stopped = True
    finally:
        report["budget_reserved_usd"] = round(guard.reserved_usd, 10)
        report["total_estimated_usd"] = round(
            sum(float(c.get("estimated_usd") or 0) for c in report["calls"]), 10
        )
        report["per_model_summary"] = _aggregate(
            report["calls"], rates, len(items), stopped
        )
        _save(report, args.output, list(keys.values()))

    print(
        "Wrote redacted Pilot B metrics to "
        f"{args.output}; calls={len(report['calls'])}; "
        f"estimated_usd={report['total_estimated_usd']:.6f}; "
        f"reserved_usd={report['budget_reserved_usd']:.6f}"
    )
    return 2 if report["stopped_early"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
