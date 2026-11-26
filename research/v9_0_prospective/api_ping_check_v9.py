#!/usr/bin/env python3
"""Credential-safe v9 OpenRouter connectivity probes for prospective work.

This script is a dry-run unless --execute is supplied. All four candidate model
slots use OPENROUTER_API_KEY in an Authorization: Bearer header and the same
OpenRouter chat/completions endpoint. Probe results are engineering checks,
not study data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROMPT = "Engineering connectivity test. Reply with exactly the single digit 1."
TEMPERATURE = 0.0
TOP_P = 1.0
MAX_TOKENS = 16
TIMEOUT_SECONDS = 30
MAX_TRANSIENT_RETRIES = 3
TRANSIENT_HTTP_STATUSES = (429, 503)
RETRY_BACKOFF_SECONDS = (2.0, 4.0, 8.0)
MIN_INTER_CALL_SPACING_SECONDS = 0.35
_LAST_HTTP_COMPLETED_MONOTONIC: float | None = None
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
ENV_BY_PROVIDER = {"openrouter": "OPENROUTER_API_KEY"}
CANDIDATES: list[dict[str, str]] = [
    {
        "slot": "qwen_72b",
        "provider": "openrouter",
        "env_var": "OPENROUTER_API_KEY",
        "model_id": "qwen/qwen-2.5-72b-instruct",
        "endpoint": OPENROUTER_ENDPOINT,
        "api_style": "openai",
    },
    {
        "slot": "gemma_27b",
        "provider": "openrouter",
        "env_var": "OPENROUTER_API_KEY",
        "model_id": "google/gemma-2-27b-it",
        "endpoint": OPENROUTER_ENDPOINT,
        "api_style": "openai",
    },
    {
        "slot": "llama_70b",
        "provider": "openrouter",
        "env_var": "OPENROUTER_API_KEY",
        "model_id": "meta-llama/llama-3.3-70b-instruct",
        "endpoint": OPENROUTER_ENDPOINT,
        "api_style": "openai",
    },
    {
        "slot": "mistral_24b",
        "provider": "openrouter",
        "env_var": "OPENROUTER_API_KEY",
        "model_id": "mistralai/mistral-small-24b-instruct-2501",
        "endpoint": OPENROUTER_ENDPOINT,
        "api_style": "openai",
    },
]
KEYLIKE_RE = re.compile(
    r"(?:AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,}|"
    r"gsk_[0-9A-Za-z_-]{20,}|[?]key=|(?i:Bearer)\s+[A-Za-z0-9._~+/-]{16,}={0,})"
)


def _integer(value: Any) -> int | None:
    try:
        return None if value is None else max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            part if isinstance(part, str) else part.get("text", "")
            for part in value
            if isinstance(part, str) or isinstance(part, dict)
        )
    return ""


def _finish(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip().lower()
    return "length" if ("length" in result or "max_tokens" in result) else (result or None)


def normalize_response(provider: str, payload: Any) -> dict[str, Any]:
    """Extract only redacted response metrics from an OpenAI-compatible reply."""
    out: dict[str, Any] = {
        "raw_text": "", "finish_reason": None, "reasoning_tokens": None,
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "logprobs_present": False, "logprobs_token_count": 0,
    }
    if provider != "openrouter" or not isinstance(payload, dict):
        return out
    choices = payload.get("choices") or []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message", {})
    message = message if isinstance(message, dict) else {}
    out["raw_text"] = _text(message.get("content", choice.get("text", "")))
    out["finish_reason"] = _finish(choice.get("finish_reason"))
    usage = payload.get("usage", {})
    if isinstance(usage, dict):
        out["input_tokens"] = _integer(usage.get("prompt_tokens", usage.get("input_tokens")))
        out["output_tokens"] = _integer(usage.get("completion_tokens", usage.get("output_tokens")))
        out["total_tokens"] = _integer(usage.get("total_tokens"))
        details = usage.get("completion_tokens_details") or usage.get("output_tokens_details")
        if isinstance(details, dict):
            out["reasoning_tokens"] = _integer(details.get("reasoning_tokens"))
        if out["reasoning_tokens"] is None:
            out["reasoning_tokens"] = _integer(usage.get("reasoning_tokens"))
    return out


def _payload(spec: dict[str, str], messages: list[dict[str, str]],
             max_tokens: int, logprobs: int | None = None) -> dict[str, Any]:
    if spec["provider"] != "openrouter" or spec["endpoint"] != OPENROUTER_ENDPOINT:
        raise ValueError("Candidate is not routed through the verified OpenRouter endpoint")
    if logprobs is not None:
        raise ValueError("This v9 runner does not issue provider-specific logprobs probes")
    return {
        "model": spec["model_id"],
        "messages": messages,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "max_tokens": max_tokens,
    }


def reset_request_pacing_state() -> None:
    """Reset process-local pacing state; exposed for deterministic offline checks."""
    global _LAST_HTTP_COMPLETED_MONOTONIC
    _LAST_HTTP_COMPLETED_MONOTONIC = None


def execute_request(
    spec: dict[str, str],
    api_key: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout_seconds: int = TIMEOUT_SECONDS,
    logprobs: int | None = None,
    before_attempt: Callable[[dict[str, Any]], None] | None = None,
    authorize_retry: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    on_retry: Callable[[dict[str, Any]], None] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    monotonic_fn: Callable[[], float] | None = None,
    urlopen_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Make a redacted, paced request with bounded retries for HTTP 429/503 only."""
    global _LAST_HTTP_COMPLETED_MONOTONIC
    if spec.get("env_var") != "OPENROUTER_API_KEY":
        raise ValueError("Candidate must use OPENROUTER_API_KEY")
    body = json.dumps(_payload(spec, messages, max_tokens, logprobs),
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        spec["endpoint"],
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    sleep = sleep_fn or time.sleep
    clock = monotonic_fn or time.monotonic
    open_url = urlopen_fn or urllib.request.urlopen
    logical_started = clock()
    attempts: list[dict[str, Any]] = []
    retry_events: list[dict[str, Any]] = []
    pending_reservation: dict[str, Any] | None = None
    response: dict[str, Any] = {
        "http_status": None, "latency_ms": 0, "payload": None,
        "error_category": "no_request_attempt",
    }

    for attempt_number in range(1, MAX_TRANSIENT_RETRIES + 2):
        spacing_wait = 0.0
        if _LAST_HTTP_COMPLETED_MONOTONIC is not None:
            spacing_wait = max(
                0.0,
                MIN_INTER_CALL_SPACING_SECONDS - (clock() - _LAST_HTTP_COMPLETED_MONOTONIC),
            )
            if spacing_wait:
                sleep(spacing_wait)
        attempt_record: dict[str, Any] = {
            "attempt_number": attempt_number,
            "retry_index": attempt_number - 1,
            "request_state": "started",
            "http_status": None,
            "inter_call_wait_seconds": round(spacing_wait, 3),
        }
        if pending_reservation is not None:
            attempt_record["pre_request_budget_reservation"] = pending_reservation
            pending_reservation = None
        attempts.append(attempt_record)
        if before_attempt is not None:
            before_attempt(attempt_record)

        request_started = clock()
        try:
            with open_url(req, timeout=timeout_seconds) as http_response:
                status = int(http_response.status)
                raw = http_response.read(2_000_001)
            if len(raw) > 2_000_000:
                response = {"http_status": status, "payload": None,
                            "error_category": "response_too_large"}
            else:
                try:
                    payload = json.loads(raw.decode("utf-8"))
                    error = None if status == 200 else "http_non_200"
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload, error = None, "invalid_json_response"
                response = {"http_status": status, "payload": payload,
                            "error_category": error}
        except urllib.error.HTTPError as exc:
            response = {"http_status": int(exc.code), "payload": None,
                        "error_category": "http_error"}
            try:
                exc.close()
            except Exception:
                pass
        except (urllib.error.URLError, socket.timeout, TimeoutError):
            response = {"http_status": None, "payload": None,
                        "error_category": "transport_error"}
        except Exception:
            response = {"http_status": None, "payload": None,
                        "error_category": "unexpected_transport_error"}
        completed = clock()
        _LAST_HTTP_COMPLETED_MONOTONIC = completed
        attempt_record.update({
            "request_state": "http_response_received" if response.get("http_status") is not None else "no_http_response",
            "http_status": response.get("http_status"),
            "latency_ms": max(0, int((completed - request_started) * 1000)),
            "error_category": response.get("error_category"),
        })

        status = response.get("http_status")
        if status not in TRANSIENT_HTTP_STATUSES:
            break
        if attempt_number > MAX_TRANSIENT_RETRIES:
            response["error_category"] = "transient_http_retries_exhausted"
            response["transient_retries_exhausted"] = True
            break

        backoff = RETRY_BACKOFF_SECONDS[attempt_number - 1]
        event: dict[str, Any] = {
            "retry_number": attempt_number,
            "after_attempt_number": attempt_number,
            "next_attempt_number": attempt_number + 1,
            "after_http_status": status,
            "backoff_seconds": backoff,
            "retry_scheduled": True,
        }
        reservation = authorize_retry(event) if authorize_retry is not None else {}
        if authorize_retry is not None and reservation is None:
            event["retry_scheduled"] = False
            event["retry_block_reason"] = "pre_request_spend_cap"
            response["error_category"] = "pre_request_spend_cap_retry"
            response["retry_blocked_by_budget"] = True
        else:
            pending_reservation = reservation
        retry_events.append(event)
        if on_retry is not None:
            on_retry(event)
        if not event["retry_scheduled"]:
            break
        sleep(backoff)

    response["latency_ms"] = max(0, int((clock() - logical_started) * 1000))
    response["request_attempts"] = attempts
    response["retry_events"] = retry_events
    response["http_attempt_count"] = len(attempts)
    response["retry_count"] = max(0, len(attempts) - 1)
    return response


def _result(spec: dict[str, str], response: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "slot": spec["slot"], "provider": spec["provider"], "model_id": spec["model_id"],
        "endpoint": spec["endpoint"], "auth_env_var": "OPENROUTER_API_KEY",
        "http_status": response.get("http_status"),
        "latency_ms": response.get("latency_ms"), "available": not blockers,
        "availability_blockers": blockers, "raw_text_empty": not text.strip(),
        "raw_text_chars": len(text),
        "raw_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "raw_text_is_single_digit_1": text.strip() == "1",
        "finish_reason": data.get("finish_reason"),
        "reasoning_tokens": reasoning,
        "input_tokens": data.get("input_tokens"), "output_tokens": data.get("output_tokens"),
        "total_tokens": data.get("total_tokens"), "error_category": response.get("error_category"),
        "http_attempt_count": response.get("http_attempt_count", 1),
        "retry_count": response.get("retry_count", 0),
    }


def _save(report: dict[str, Any], output: Path, secrets: list[str]) -> None:
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if any(secret and secret in text for secret in secrets) or KEYLIKE_RE.search(text):
        raise RuntimeError("Refusing to save report: credential-like content detected.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(output)


def _tracked_request(
    spec: dict[str, str], api_key: str, output: Path,
    report: dict[str, Any], secrets: list[str], timeout: int,
) -> dict[str, Any]:
    messages = [{"role": "user", "content": PROMPT}]
    call_id = f"probe-{len(report['api_request_ledger']) + 1:04d}"
    request_body = _payload(spec, messages, MAX_TOKENS)
    attempt: dict[str, Any] = {
        "call_id": call_id, "slot": spec["slot"], "provider": spec["provider"],
        "model_id": spec["model_id"], "endpoint": spec["endpoint"],
        "request_state": "started", "started_utc": datetime.now(timezone.utc).isoformat(),
        "prompt_sha256": hashlib.sha256(
            json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "request_body_sha256": hashlib.sha256(
            json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE, "top_p": TOP_P,
        "auth_env_var": "OPENROUTER_API_KEY", "http_attempts": [], "retry_events": [],
    }
    report["api_request_ledger"].append(attempt)

    def checkpoint() -> None:
        report["http_calls_started"] = sum(
            len(call.get("http_attempts", [])) for call in report["api_request_ledger"]
        )
        report["http_responses_received"] = sum(
            1 for call in report["api_request_ledger"]
            for http_attempt in call.get("http_attempts", [])
            if http_attempt.get("http_status") is not None
        )
        _save(report, output, secrets)

    def before_attempt(http_attempt: dict[str, Any]) -> None:
        attempt["http_attempts"].append(http_attempt)
        checkpoint()

    def on_retry(event: dict[str, Any]) -> None:
        attempt["retry_events"].append(event)
        checkpoint()

    checkpoint()
    response = execute_request(
        spec, api_key, messages, MAX_TOKENS, timeout_seconds=timeout,
        before_attempt=before_attempt, on_retry=on_retry,
    )
    row = _result(spec, response)
    row["call_id"] = call_id
    attempt.update({
        "request_state": "http_response_received" if response.get("http_status") is not None else "no_http_response",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": response.get("http_status"), "latency_ms": response.get("latency_ms"),
        "error_category": response.get("error_category"), "available": row["available"],
        "retry_count": response.get("retry_count", 0),
    })
    report["results"].append(row)
    checkpoint()
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="send four OpenRouter engineering connectivity probes")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parser.add_argument("--output", default=f"results/api_ping_check_v9_{stamp}.json")
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    if not args.execute:
        print(
            "DRY RUN: no keys read and no HTTP requests sent; planned probes=4; "
            "maximum HTTP attempts=16 with up to three 429/503 retries each."
        )
        return 0
    if args.timeout < 1:
        print("BLOCKED: timeout must be at least 1 second")
        return 2
    output = Path(args.output)
    if not output.is_absolute():
        output = Path(__file__).resolve().parent / output
    if output.exists():
        print("BLOCKED: output exists; refusing to overwrite a prior run")
        return 2
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        print("BLOCKED: missing required environment variable: OPENROUTER_API_KEY")
        return 2

    report: dict[str, Any] = {
        "schema": "designlab-v9-engineering-connectivity-v2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "run_classification": "engineering_connectivity_not_study_data",
        "prompt": PROMPT, "temperature": TEMPERATURE, "top_p": TOP_P,
        "max_tokens": MAX_TOKENS, "confirmatory_data": False,
        "endpoint": OPENROUTER_ENDPOINT, "auth_env_var": "OPENROUTER_API_KEY",
        "connectivity_probe_count": len(CANDIDATES), "http_calls_started": 0,
        "http_responses_received": 0,
        "transient_retry_policy": {
            "statuses": list(TRANSIENT_HTTP_STATUSES),
            "maximum_retries": MAX_TRANSIENT_RETRIES,
            "backoff_seconds": list(RETRY_BACKOFF_SECONDS),
            "minimum_inter_call_spacing_seconds": MIN_INTER_CALL_SPACING_SECONDS,
        },
        "api_request_ledger": [], "results": [],
        "halt_reason": None, "not_attempted_slots": [],
    }
    _save(report, output, [key])
    try:
        for index, spec in enumerate(CANDIDATES):
            row = _tracked_request(spec, key, output, report, [key], args.timeout)
            print(f"{row['slot']} {row['model_id']}: HTTP {row['http_status']} "
                  f"available={row['available']} retries={row.get('retry_count', 0)}")
            if row.get("http_status") == 402:
                report["halt_reason"] = "http_402_insufficient_credits"
                report["not_attempted_slots"] = [candidate["slot"] for candidate in CANDIDATES[index + 1:]]
                break
    finally:
        _save(report, output, [key])
    all_available = len(report["results"]) == len(CANDIDATES) and all(
        row["available"] for row in report["results"]
    )
    print(f"Wrote redacted result metadata to {output}")
    print("Connectivity gate: " + ("PASS" if all_available else "FAIL"))
    return 0 if all_available else 2


if __name__ == "__main__":
    raise SystemExit(main())
