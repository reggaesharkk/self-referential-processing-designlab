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
from typing import Any

PROMPT = "Engineering connectivity test. Reply with exactly the single digit 1."
TEMPERATURE = 0.0
TOP_P = 1.0
MAX_TOKENS = 16
TIMEOUT_SECONDS = 30
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
    r"gsk_[0-9A-Za-z_-]{20,}|\?key=|(?i:Bearer)\s+[A-Za-z0-9._~+/-]{16,}={0,})"
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


def execute_request(spec: dict[str, str], api_key: str,
                    messages: list[dict[str, str]], max_tokens: int,
                    timeout_seconds: int = TIMEOUT_SECONDS,
                    logprobs: int | None = None) -> dict[str, Any]:
    """Make one request; the API key is used only in the HTTP Authorization header."""
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
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            status = int(response.status)
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            return {"http_status": status, "latency_ms": int((time.monotonic()-started)*1000),
                    "payload": None, "error_category": "response_too_large"}
        try:
            payload = json.loads(raw.decode("utf-8"))
            error = None if status == 200 else "http_non_200"
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload, error = None, "invalid_json_response"
        return {"http_status": status, "latency_ms": int((time.monotonic()-started)*1000),
                "payload": payload, "error_category": error}
    except urllib.error.HTTPError as exc:
        return {"http_status": int(exc.code), "latency_ms": int((time.monotonic()-started)*1000),
                "payload": None, "error_category": "http_error"}
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        return {"http_status": None, "latency_ms": int((time.monotonic()-started)*1000),
                "payload": None, "error_category": "transport_error"}
    except Exception:
        return {"http_status": None, "latency_ms": int((time.monotonic()-started)*1000),
                "payload": None, "error_category": "unexpected_transport_error"}


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
    call_id = f"http-{len(report['api_request_ledger']) + 1:04d}"
    request_body = _payload(spec, messages, MAX_TOKENS)
    attempt = {
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
        "auth_env_var": "OPENROUTER_API_KEY",
    }
    report["api_request_ledger"].append(attempt)
    report["http_calls_started"] = len(report["api_request_ledger"])
    _save(report, output, secrets)

    response = execute_request(spec, api_key, messages, MAX_TOKENS, timeout_seconds=timeout)
    row = _result(spec, response)
    row["call_id"] = call_id
    attempt.update({
        "request_state": "http_response_received" if response.get("http_status") is not None else "no_http_response",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": response.get("http_status"), "latency_ms": response.get("latency_ms"),
        "error_category": response.get("error_category"), "available": row["available"],
    })
    report["http_responses_received"] = sum(
        1 for call in report["api_request_ledger"]
        if call["request_state"] == "http_response_received"
    )
    report["results"].append(row)
    _save(report, output, secrets)
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
        print("DRY RUN: no keys read and no HTTP requests sent; planned calls=4.")
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
        "http_responses_received": 0, "api_request_ledger": [], "results": [],
    }
    _save(report, output, [key])
    try:
        for spec in CANDIDATES:
            row = _tracked_request(spec, key, output, report, [key], args.timeout)
            print(f"{row['slot']} {row['model_id']}: HTTP {row['http_status']} "
                  f"available={row['available']}")
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
