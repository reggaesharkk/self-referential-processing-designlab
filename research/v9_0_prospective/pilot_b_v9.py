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
    MAX_TRANSIENT_RETRIES,
    MIN_INTER_CALL_SPACING_SECONDS,
    RETRY_BACKOFF_SECONDS,
    TRANSIENT_HTTP_STATUSES,
    _payload,
    execute_request,
    normalize_response,
)

EXPECTED_ITEMS_POOL_SHA256 = (
    "128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3"
)
DEFAULT_BUDGET_USD = 0.25
MAX_BUDGET_USD = 0.25
DEFAULT_NUM_ITEMS = 5
PILOT_ITEMS_PER_RUN = DEFAULT_NUM_ITEMS
SUPPORTED_NUM_ITEMS = (5, 50, 260)
RESERVATION_OUTPUT_TOKEN_MULTIPLIER = 2
MAX_STYLE_REPAIRS = 4
SHARED_SCRUBBER_PRIMARY_SLOT = "gemma_27b"
SHARED_SCRUBBER_FALLBACK_SLOT = "mistral_24b"
NON_SCRUB_STAGES_PER_ITEM = 4
MAX_LOGICAL_CALLS_PER_TEST_SLOT_PER_ITEM = NON_SCRUB_STAGES_PER_ITEM + 2 * (1 + MAX_STYLE_REPAIRS)
STYLE_WORD_MIN = 45
STYLE_WORD_MAX = 55
STYLE_WORD_TARGET_MIN = 48
STYLE_WORD_TARGET_MAX = 52
STYLE_SCRUB_INSTRUCTION = (
    "Write 3 plain, neutral sentences totaling strictly 48 to 52 whitespace-separated words "
    "(minimum 45, maximum 55)."
)
MAX_TOKENS = {
    "phase0_harvest": 256,
    "utility_perturb": 256,
    "utility_style_scrub": 192,
    "phase1_digit_evaluation": 16,
    "domain2_digit_evaluation": 16,
}


def style_scrubber_route(tested_slot: str) -> tuple[str, str | None]:
    """Choose an independent utility model for one tested model slot."""
    if tested_slot == "gemma_27b":
        return "mistral_24b", None
    fallback = "mistral_24b" if tested_slot in {"qwen_72b", "llama_70b"} else None
    return "gemma_27b", fallback


def run_classification_for_num_items(num_items: int) -> tuple[str, bool]:
    if num_items == 5:
        return "prospective_pilot_b_not_confirmatory_study", False
    if num_items == 50:
        return "prospective_pilot_a_not_confirmatory_study", False
    if num_items == 260:
        return "prospective_confirmatory_study", True
    raise ValueError("num_items must be one of 5, 50, or 260")


def maximum_calls_per_test_slot_per_item(tested_slot: str) -> int:
    scrubbers = tuple(slot for slot in style_scrubber_route(tested_slot) if slot)
    return NON_SCRUB_STAGES_PER_ITEM + len(scrubbers) * (1 + MAX_STYLE_REPAIRS)


def call_bounds(num_items: int) -> dict[str, int]:
    if num_items not in SUPPORTED_NUM_ITEMS:
        raise ValueError("num_items must be one of 5, 50, or 260")
    baseline = len(CANDIDATES) * num_items * len(MAX_TOKENS)
    maximum_logical = num_items * sum(
        maximum_calls_per_test_slot_per_item(spec["slot"]) for spec in CANDIDATES
    )
    return {
        "baseline_logical_calls": baseline,
        "maximum_logical_calls_with_shared_scrub_fallback": maximum_logical,
        "maximum_http_attempts_with_transient_retries": maximum_logical * (MAX_TRANSIENT_RETRIES + 1),
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
        output_upper = output_limit * RESERVATION_OUTPUT_TOKEN_MULTIPLIER
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


def load_items(path: Path, num_items: int = DEFAULT_NUM_ITEMS) -> tuple[str, list[dict[str, Any]]]:
    if num_items not in SUPPORTED_NUM_ITEMS:
        raise ValueError("BLOCKED: --num-items must be 5, 50, or 260")
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
    return actual, data[:num_items]


def load_rate_card(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("BLOCKED: model_rates_v9.json is missing or invalid") from None
    if (document.get("currency") != "USD"
            or document.get("provider") != "openrouter"
            or not isinstance(document.get("models"), dict)):
        raise ValueError("BLOCKED: rate-card schema is invalid")
    expected_policy = {
        "stage_max_tokens": MAX_TOKENS,
        "style_scrub": {
            "instruction": STYLE_SCRUB_INSTRUCTION,
            "locked_word_window": [STYLE_WORD_MIN, STYLE_WORD_MAX],
            "target_word_window": [STYLE_WORD_TARGET_MIN, STYLE_WORD_TARGET_MAX],
            "maximum_repair_attempts": MAX_STYLE_REPAIRS,
            "repairs_only_when_word_count_is_only_blocker": True,
        },
        "shared_utility_scrubber": {
            "primary_slot": SHARED_SCRUBBER_PRIMARY_SLOT,
            "fallback_slot": SHARED_SCRUBBER_FALLBACK_SLOT,
            "avoid_self_scrub": True,
            "routes_by_tested_slot": {
                spec["slot"]: {
                    "primary_slot": style_scrubber_route(spec["slot"])[0],
                    "fallback_slot": style_scrubber_route(spec["slot"])[1],
                }
                for spec in CANDIDATES
            },
        },
        "transient_http_retry": {
            "statuses": list(TRANSIENT_HTTP_STATUSES),
            "maximum_retries": MAX_TRANSIENT_RETRIES,
            "backoff_seconds": list(RETRY_BACKOFF_SECONDS),
            "minimum_inter_call_spacing_seconds": MIN_INTER_CALL_SPACING_SECONDS,
        },
        "num_items": {"default": DEFAULT_NUM_ITEMS, "supported": list(SUPPORTED_NUM_ITEMS)},
        "model_slots_per_run": len(CANDIDATES),
        "baseline_calls_per_item_per_model": len(MAX_TOKENS),
        "maximum_logical_calls_per_item_per_model_with_fallback": MAX_LOGICAL_CALLS_PER_TEST_SLOT_PER_ITEM,
        "baseline_total_logical_calls_for_default_items": call_bounds(DEFAULT_NUM_ITEMS)["baseline_logical_calls"],
        "maximum_logical_calls_with_fallback_for_default_items": call_bounds(DEFAULT_NUM_ITEMS)["maximum_logical_calls_with_shared_scrub_fallback"],
        "maximum_http_attempts_with_retries_for_default_items": call_bounds(DEFAULT_NUM_ITEMS)["maximum_http_attempts_with_transient_retries"],
        "output_token_reservation_multiplier": RESERVATION_OUTPUT_TOKEN_MULTIPLIER,
        "budget_cap_usd": MAX_BUDGET_USD,
    }
    if document.get("runner_policy") != expected_policy:
        raise ValueError("BLOCKED: rate-card runner policy does not match locked token, retry, call, and budget settings")
    expected_slots = {spec["slot"] for spec in CANDIDATES}
    if set(document["models"]) != expected_slots:
        raise ValueError("BLOCKED: rate-card slots do not match the four candidate slots 1-to-1")
    rates: dict[str, dict[str, Any]] = {}
    for spec in CANDIDATES:
        slot = spec["slot"]
        row = document["models"].get(slot)
        if (not isinstance(row, dict)
                or row.get("provider") != spec["provider"]
                or row.get("model_id") != spec["model_id"]):
            raise ValueError(f"BLOCKED: no matching provider/model rate for slot {slot}")
        try:
            in_rate = float(row["input_usd_per_1m_tokens"])
            out_rate = float(row["output_usd_per_1m_tokens"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"BLOCKED: invalid rate for slot {slot}") from None
        if in_rate < 0 or out_rate < 0:
            raise ValueError(f"BLOCKED: negative rate for slot {slot}")
        rates[slot] = {
            "provider": spec["provider"],
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
    repair_attempt: int = 0,
    tested_slot: str | None = None,
    tested_model_id: str | None = None,
    call_role: str = "tested_model",
    scrubber_route_role: str | None = None,
    fallback_reason: str | None = None,
) -> tuple[dict[str, Any], str]:
    output_cap = MAX_TOKENS[stage]
    tested_slot = tested_slot or spec["slot"]
    tested_model_id = tested_model_id or spec["model_id"]
    billing_slot = spec["slot"]
    call_id = f"pilot-{len(report['calls']) + 1:05d}"
    reserved = guard.reserve(
        messages, output_cap,
        rate["input_usd_per_1m_tokens"], rate["output_usd_per_1m_tokens"],
    )
    base = {
        "call_id": call_id,
        "slot": tested_slot,
        "tested_slot": tested_slot,
        "tested_model_id": tested_model_id,
        "billing_slot": billing_slot,
        "billing_model_id": spec["model_id"],
        "call_role": call_role,
        "scrubber_route_role": scrubber_route_role,
        "fallback_reason": fallback_reason,
        "provider": spec["provider"], "model_id": spec["model_id"],
        "item_id": item_id, "stage": stage, "repair_attempt": repair_attempt,
        "requested_max_tokens": output_cap,
        "http_call_started": False, "http_attempts_started": 0,
        "http_attempts": [], "retry_events": [], "budget_reservations": [],
        "http_status": None, "latency_ms": 0,
    }
    if reserved is None:
        row = {
            **base,
            "request_state": "not_started_budget_cap",
            "available": False,
            "availability_blockers": ["pre_request_spend_cap"],
            "error_category": "pre_request_spend_cap",
            "input_tokens": None, "output_tokens": None,
            "estimated_usd": 0.0, "budget_reservation_usd": 0.0,
            "reserved_input_tokens_upper_bound": 0,
            "reserved_output_tokens_upper_bound": 0,
        }
        report["calls"].append(row)
        checkpoint()
        return row, ""

    input_upper, reservation = reserved
    reservation_row = {
        "attempt_number": 1,
        "reserved_input_tokens_upper_bound": input_upper,
        "reserved_output_tokens_upper_bound": output_cap * RESERVATION_OUTPUT_TOKEN_MULTIPLIER,
        "budget_reservation_usd": reservation,
    }
    base["budget_reservations"].append(reservation_row)
    base["budget_reservation_usd"] = reservation
    request_body = _payload(spec, messages, output_cap, None)
    base.update({
        "request_state": "started",
        "started_utc": utc_now(),
        "prompt_sha256": hashlib.sha256(
            json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "request_body_sha256": hashlib.sha256(
            json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "reserved_input_tokens_upper_bound": input_upper,
        "reserved_output_tokens_upper_bound": reservation_row["reserved_output_tokens_upper_bound"],
    })
    report["calls"].append(base)
    checkpoint()

    def before_attempt(http_attempt: dict[str, Any]) -> None:
        base["http_call_started"] = True
        base["http_attempts_started"] += 1
        base["http_attempts"].append(http_attempt)
        checkpoint()

    def authorize_retry(event: dict[str, Any]) -> dict[str, Any] | None:
        retry_reservation = guard.reserve(
            messages, output_cap,
            rate["input_usd_per_1m_tokens"], rate["output_usd_per_1m_tokens"],
        )
        if retry_reservation is None:
            return None
        retry_input_upper, retry_amount = retry_reservation
        reservation_data = {
            "attempt_number": event["next_attempt_number"],
            "reserved_input_tokens_upper_bound": retry_input_upper,
            "reserved_output_tokens_upper_bound": output_cap * RESERVATION_OUTPUT_TOKEN_MULTIPLIER,
            "budget_reservation_usd": retry_amount,
        }
        base["budget_reservations"].append(reservation_data)
        base["budget_reservation_usd"] = round(
            sum(float(r["budget_reservation_usd"]) for r in base["budget_reservations"]), 10
        )
        base["reserved_input_tokens_upper_bound"] += retry_input_upper
        base["reserved_output_tokens_upper_bound"] += reservation_data["reserved_output_tokens_upper_bound"]
        return reservation_data

    def on_retry(event: dict[str, Any]) -> None:
        base["retry_events"].append(event)
        checkpoint()

    response = execute_request(
        spec, api_key, messages, output_cap, timeout_seconds=timeout,
        before_attempt=before_attempt, authorize_retry=authorize_retry, on_retry=on_retry,
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
    if response.get("retry_blocked_by_budget"):
        blockers.append("pre_request_spend_cap_retry")
    reasoning = data.get("reasoning_tokens")
    if reasoning is not None and reasoning > 0:
        blockers.append("reasoning_tokens_positive")
    word_count = len(text.split()) if stage == "utility_style_scrub" else None
    if stage == "utility_style_scrub" and not STYLE_WORD_MIN <= (word_count or 0) <= STYLE_WORD_MAX:
        blockers.append("style_scrub_word_count_out_of_range")
    digit = None
    if stage in {"phase1_digit_evaluation", "domain2_digit_evaluation"}:
        digit = text.strip() if text.strip() in {"0", "1"} else None
        if digit is None:
            blockers.append("evaluation_not_single_digit")

    attempts = response.get("request_attempts", [])
    reservation_rows = base["budget_reservations"]
    last_reservation = float(reservation_rows[-1]["budget_reservation_usd"])
    final_cost = guard.settle(
        last_reservation, data.get("input_tokens"), data.get("output_tokens"),
        rate["input_usd_per_1m_tokens"], rate["output_usd_per_1m_tokens"],
    )
    prior_retry_reservations = sum(
        float(r["budget_reservation_usd"]) for r in reservation_rows[:-1]
    )
    cost = round(prior_retry_reservations + final_cost, 10)
    base.update({
        "request_state": "http_response_received" if response.get("http_status") is not None else "no_http_response",
        "completed_utc": utc_now(),
        "http_status": response.get("http_status"),
        "latency_ms": response.get("latency_ms"),
        "available": not blockers,
        "availability_blockers": blockers,
        "error_category": response.get("error_category"),
        "http_attempt_count": len(attempts),
        "retry_count": response.get("retry_count", 0),
        **_fingerprint(text),
        "finish_reason": data.get("finish_reason"),
        "reasoning_tokens": reasoning,
        "input_tokens": data.get("input_tokens"),
        "output_tokens": data.get("output_tokens"),
        "total_tokens": data.get("total_tokens"),
        "estimated_usd": cost,
    })
    if word_count is not None:
        base["style_scrub_word_count"] = word_count
    if stage in {"phase1_digit_evaluation", "domain2_digit_evaluation"}:
        base["evaluation_digit"] = digit
    checkpoint()
    return base, text


def run_style_scrub_with_repairs(
    tested_spec: dict[str, str],
    keys: dict[str, str],
    item_id: str,
    prompt: str,
    perturbed: str,
    timeout: int,
    rates: dict[str, dict[str, Any]],
    guard: SpendGuard,
    report: dict[str, Any],
    checkpoint: Any,
) -> tuple[dict[str, Any], str]:
    """Use the shared utility model, then an independent fallback when configured."""
    primary_slot, fallback_slot = style_scrubber_route(tested_spec["slot"])

    def scrub_with(slot: str, route_role: str, fallback_reason: str | None = None) -> tuple[dict[str, Any], str]:
        scrubber_spec = next(spec for spec in CANDIDATES if spec["slot"] == slot)
        system = (
            "Neutralize stylistic framing while preserving the answer's utility and facts. "
            f"{STYLE_SCRUB_INSTRUCTION} Return only the rewritten text."
        )
        row, current = run_stage(
            scrubber_spec, keys[scrubber_spec["env_var"]], item_id, "utility_style_scrub",
            _messages(system, "Research item:\n" + prompt + "\n\nPerturbed answer:\n" + perturbed),
            timeout, rates[slot], guard, report, checkpoint,
            tested_slot=tested_spec["slot"], tested_model_id=tested_spec["model_id"],
            call_role="shared_utility_scrubber", scrubber_route_role=route_role,
            fallback_reason=fallback_reason,
        )
        for attempt_number in range(1, MAX_STYLE_REPAIRS + 1):
            if row.get("available"):
                return row, current
            if row.get("availability_blockers") != ["style_scrub_word_count_out_of_range"]:
                return row, current

            current_count = len(current.split())
            repair_messages = _messages(
                "This is a length-adjustment repair. Preserve the existing rewrite's meaning, "
                "task utility, and facts; do not add a new answer. "
                f"{STYLE_SCRUB_INSTRUCTION} The exact current rewrite contains "
                f"{current_count} whitespace-separated words. Adjust it toward 50 words "
                "while meeting the stated sentence count and word window. Return only the revised text.",
                f"Current rewrite word count: {current_count}. Target: "
                f"{STYLE_WORD_TARGET_MIN}–{STYLE_WORD_TARGET_MAX} words.\n\n"
                "Research item:\n" + prompt + "\n\nCurrent rewrite:\n" + current,
            )
            row, current = run_stage(
                scrubber_spec, keys[scrubber_spec["env_var"]], item_id,
                "utility_style_scrub", repair_messages, timeout, rates[slot], guard,
                report, checkpoint, repair_attempt=attempt_number,
                tested_slot=tested_spec["slot"], tested_model_id=tested_spec["model_id"],
                call_role="shared_utility_scrubber", scrubber_route_role=route_role,
                fallback_reason=fallback_reason,
            )
        return row, current

    row, current = scrub_with(primary_slot, "primary")
    if row.get("available") or fallback_slot is None:
        return row, current
    if row.get("availability_blockers") != ["style_scrub_word_count_out_of_range"]:
        return row, current
    return scrub_with(
        fallback_slot, "fallback",
        f"{primary_slot}_exhausted_{MAX_STYLE_REPAIRS}_word_count_repairs",
    )


def _aggregate(
    calls: list[dict[str, Any]],
    item_ids: list[str],
    stopped: bool,
) -> list[dict[str, Any]]:
    summaries = []
    required_stages = set(MAX_TOKENS)
    for spec in CANDIDATES:
        rows = [c for c in calls if c.get("slot") == spec["slot"]]
        tested_rows = [c for c in rows if c.get("call_role") != "shared_utility_scrubber"]
        scrub_rows = [c for c in rows if c.get("call_role") == "shared_utility_scrubber"]
        in_values = [c["input_tokens"] for c in tested_rows if c.get("input_tokens") is not None]
        out_values = [c["output_tokens"] for c in tested_rows if c.get("output_tokens") is not None]
        scrub_in_values = [c["input_tokens"] for c in scrub_rows if c.get("input_tokens") is not None]
        scrub_out_values = [c["output_tokens"] for c in scrub_rows if c.get("output_tokens") is not None]
        successful_pairs = {
            (str(c.get("item_id")), str(c.get("stage")))
            for c in rows if c.get("available") is True
        }
        complete = all(
            (item_id, stage) in successful_pairs
            for item_id in item_ids for stage in required_stages
        )
        summaries.append(
            {
                "slot": spec["slot"],
                "provider": spec["provider"],
                "model_id": spec["model_id"],
                "available": complete,
                "complete_pipeline": complete,
                "calls_recorded": len(rows),
                "http_attempts_started": sum(int(c.get("http_attempts_started") or 0) for c in rows),
                "transient_retry_attempts": sum(int(c.get("retry_count") or 0) for c in rows),
                "calls_expected_baseline": len(item_ids) * len(required_stages),
                "calls_max_with_shared_scrub_fallback": len(item_ids) * maximum_calls_per_test_slot_per_item(spec["slot"]),
                "style_repair_calls": sum(
                    1 for c in rows
                    if c.get("stage") == "utility_style_scrub" and int(c.get("repair_attempt") or 0) > 0
                ),
                "shared_scrub_calls": sum(1 for c in rows if c.get("call_role") == "shared_utility_scrubber"),
                "shared_scrub_billed_model_slots": sorted({
                    str(c.get("billing_slot")) for c in rows
                    if c.get("call_role") == "shared_utility_scrubber"
                }),
                "tested_model_estimated_usd": round(sum(
                    float(c.get("estimated_usd") or 0) for c in rows
                    if c.get("call_role") != "shared_utility_scrubber"
                ), 10),
                "shared_scrub_estimated_usd": round(sum(
                    float(c.get("estimated_usd") or 0) for c in rows
                    if c.get("call_role") == "shared_utility_scrubber"
                ), 10),
                "successful_item_stage_pairs": len(successful_pairs),
                "input_tokens": sum(in_values),
                "output_tokens": sum(out_values),
                "usage_missing_calls": len(tested_rows) - min(len(in_values), len(out_values)),
                "shared_scrub_input_tokens": sum(scrub_in_values),
                "shared_scrub_output_tokens": sum(scrub_out_values),
                "shared_scrub_usage_missing_calls": len(scrub_rows) - min(len(scrub_in_values), len(scrub_out_values)),
                "latency_ms": sum(int(c.get("latency_ms") or 0) for c in rows),
                "estimated_usd": round(sum(float(c.get("estimated_usd") or 0) for c in rows), 10),
                "budget_reservation_usd": round(sum(float(c.get("budget_reservation_usd") or 0) for c in rows), 10),
                "halted_early": stopped and not complete,
            }
        )
    return summaries


def _aggregate_billing_models(
    calls: list[dict[str, Any]], rates: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries = []
    for spec in CANDIDATES:
        rows = [c for c in calls if c.get("billing_slot", c.get("slot")) == spec["slot"]]
        input_values = [c["input_tokens"] for c in rows if c.get("input_tokens") is not None]
        output_values = [c["output_tokens"] for c in rows if c.get("output_tokens") is not None]
        rate = rates[spec["slot"]]
        summaries.append({
            "billing_slot": spec["slot"],
            "provider": spec["provider"],
            "model_id": spec["model_id"],
            "logical_call_records": len(rows),
            "http_attempts_started": sum(int(c.get("http_attempts_started") or 0) for c in rows),
            "shared_scrub_calls": sum(1 for c in rows if c.get("call_role") == "shared_utility_scrubber"),
            "input_tokens": sum(input_values),
            "output_tokens": sum(output_values),
            "usage_missing_calls": len(rows) - min(len(input_values), len(output_values)),
            "estimated_usd": round(sum(float(c.get("estimated_usd") or 0) for c in rows), 10),
            "budget_reservation_usd": round(sum(float(c.get("budget_reservation_usd") or 0) for c in rows), 10),
            "input_usd_per_1m_tokens": rate["input_usd_per_1m_tokens"],
            "output_usd_per_1m_tokens": rate["output_usd_per_1m_tokens"],
        })
    return summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, default=repo_root() / "items_pool_v1.json")
    parser.add_argument("--rates", type=Path, default=Path(__file__).resolve().parent / "model_rates_v9.json")
    parser.add_argument("--budget-usd", type=float, default=DEFAULT_BUDGET_USD)
    parser.add_argument("--num-items", type=int, choices=SUPPORTED_NUM_ITEMS, default=DEFAULT_NUM_ITEMS,
                        help="number of leading pool items: 5 Pilot B, 50 Pilot A, or 260 confirmatory")
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
        pool_hash, items = load_items(args.items, args.num_items)
        rates, pricing_date = load_rate_card(args.rates)
    except ValueError as exc:
        print(str(exc))
        return 2
    if not args.execute:
        classification, _ = run_classification_for_num_items(args.num_items)
        bounds = call_bounds(args.num_items)
        print(
            f"DRY RUN: frozen pool verified; selected {len(items)} leading items "
            f"({classification}); baseline logical calls={bounds['baseline_logical_calls']}; "
            f"maximum logical calls with shared scrub fallback="
            f"{bounds['maximum_logical_calls_with_shared_scrub_fallback']}; "
            f"maximum HTTP attempts including retries="
            f"{bounds['maximum_http_attempts_with_transient_retries']}; "
            "no keys read and no HTTP requests sent."
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
    classification, _ = run_classification_for_num_items(args.num_items)
    bounds = call_bounds(args.num_items)
    report: dict[str, Any] = {
        "schema": "designlab-v9-pilot-b-v4",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "run_classification": classification,
        "num_items_requested": args.num_items,
        "num_items_selected": len(items),
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
        "candidate_slots": [
            {"slot": spec["slot"], "provider": spec["provider"], "model_id": spec["model_id"],
             "endpoint": spec["endpoint"], "auth_env_var": spec["env_var"]}
            for spec in CANDIDATES
        ],
        "stage_max_tokens": dict(MAX_TOKENS),
        "output_token_reservation_multiplier": RESERVATION_OUTPUT_TOKEN_MULTIPLIER,
        "baseline_expected_logical_calls": bounds["baseline_logical_calls"],
        "maximum_logical_calls_with_shared_scrub_fallback": bounds["maximum_logical_calls_with_shared_scrub_fallback"],
        "maximum_http_attempts_with_transient_retries": bounds["maximum_http_attempts_with_transient_retries"],
        "shared_utility_scrubber_policy": {
            "primary_slot": SHARED_SCRUBBER_PRIMARY_SLOT,
            "fallback_slot": SHARED_SCRUBBER_FALLBACK_SLOT,
            "avoid_self_scrub": True,
            "routes_by_tested_slot": {spec["slot"]: {
                "primary_slot": style_scrubber_route(spec["slot"])[0],
                "fallback_slot": style_scrubber_route(spec["slot"])[1],
            } for spec in CANDIDATES},
        },
        "transient_http_retry_policy": {
            "statuses": list(TRANSIENT_HTTP_STATUSES),
            "maximum_retries": MAX_TRANSIENT_RETRIES,
            "backoff_seconds": list(RETRY_BACKOFF_SECONDS),
            "minimum_inter_call_spacing_seconds": MIN_INTER_CALL_SPACING_SECONDS,
        },
        "style_scrub_repair_policy": {
            "locked_word_window": [STYLE_WORD_MIN, STYLE_WORD_MAX],
            "instruction": STYLE_SCRUB_INSTRUCTION,
            "target_word_window": [STYLE_WORD_TARGET_MIN, STYLE_WORD_TARGET_MAX],
            "maximum_repair_attempts_per_item_and_model": MAX_STYLE_REPAIRS,
            "repairs_only_when_word_count_is_the_only_blocker": True,
            "repair_prompt_records_exact_current_word_count": True,
        },
        "temperature": 0.0,
        "top_p": 1.0,
        "evaluation_max_tokens": 16,
        "evaluation_stage_max_tokens_locked": {
            "phase1_digit_evaluation": 16,
            "domain2_digit_evaluation": 16,
        },
        "budget_cap_usd": args.budget_usd,
        "pricing_snapshot_date": pricing_date,
        "budget_method": "pre-request UTF-8 byte and output-token reservation at versioned rate card",
        "logical_call_records": 0,
        "http_calls_started": 0,
        "http_responses_received": 0,
        "budget_reserved_usd": 0.0,
        "total_estimated_usd": 0.0,
        "stopped_early": False,
        "halt_reason": None,
        "calls": [],
        "per_model_summary": [],
        "per_billing_model_summary": [],
    }

    def checkpoint() -> None:
        report["logical_call_records"] = len(report["calls"])
        report["http_calls_started"] = sum(
            int(call.get("http_attempts_started") or 0) for call in report["calls"]
        )
        report["http_responses_received"] = sum(
            1 for call in report["calls"] for attempt in call.get("http_attempts", [])
            if attempt.get("http_status") is not None
        )
        report["confirmatory_data_collected"] = bool(
            args.num_items == 260 and any(
                call.get("stage") == "phase0_harvest"
                and call.get("http_status") == 200
                and int(call.get("raw_text_chars") or 0) > 0
                for call in report["calls"]
            )
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
            rate = rates[spec["slot"]]
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
                        if row.get("error_category") in {"pre_request_spend_cap", "pre_request_spend_cap_retry"}:
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
                    if row.get("error_category") in {"pre_request_spend_cap", "pre_request_spend_cap_retry"}:
                        report["stopped_early"] = True
                        report["halt_reason"] = "estimated spend cap reached before request"
                        stopped = True
                    failed = True
                    break

                row, scrubbed = run_style_scrub_with_repairs(
                    spec, keys, item_id, prompt, perturbed,
                    args.timeout, rates, guard, report, checkpoint,
                )
                if not row["available"]:
                    if row.get("error_category") in {"pre_request_spend_cap", "pre_request_spend_cap_retry"}:
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
                        if row.get("error_category") in {"pre_request_spend_cap", "pre_request_spend_cap_retry"}:
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
                report.setdefault("provider_failures", []).append(spec["slot"])
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
            report["calls"], [str(item["item_id"]) for item in items], stopped
        )
        report["per_billing_model_summary"] = _aggregate_billing_models(report["calls"], rates)
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
