#!/usr/bin/env python3
"""Credential-safe replacement for the archived v8.6.3 endpoint ping checker.

Engineering only. It uses an unrelated prompt, never reads study items, sends
Google credentials in the x-goog-api-key header (not a query string), never
stores request headers/bodies, and saves only redacted error categories.

This does NOT decide whether a model is an allowed replacement under v8.6.3.
That decision must already be documented in closed_endpoint_resolution.json and,
for a successor, in the required OSF preregistration amendment before data
collection for that cell.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REQUIRED_KEYS = [
    "openai_flagship", "openai_lightweight",
    "anthropic_flagship", "anthropic_lightweight",
    "google_flagship", "google_lightweight",
    "cohere_flagship", "mistral_flagship",
]
ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "cohere": "COHERE_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}
ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "google": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    "cohere": "https://api.cohere.com/v2/chat",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
}
T, TOP_P, MAX_TOK = 0.0, 1.0, 16
PROMPT = "Engineering endpoint availability check. Reply with exactly the single digit 1."
TIMEOUT_S = 30
PLACEHOLDER_RE = re.compile(r"REPLACE|PLACEHOLDER|TBD|TODO|DEFERRED_PENDING", re.I)
FLOATING_ALIAS_RE = re.compile(r"(?:-latest|-stable|latest-|preview)", re.I)
KEYLIKE_RE = re.compile(r"(?:AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{12,}|gsk_[0-9A-Za-z_-]{12,})")


def normalize_vendor(v):
    s = (v or "").lower()
    for x in ("openai", "anthropic", "google", "cohere", "mistral"):
        if x in s:
            return x
    return ""


def clean_endpoint(url):
    u = urlsplit(url)
    return urlunsplit((u.scheme, u.netloc, u.path, "", ""))


def load_targets(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(cfg) != set(REQUIRED_KEYS):
        raise SystemExit("FAIL: closed_api_targets.json must contain exactly the 8 registered slots")
    for key in REQUIRED_KEYS:
        s = cfg[key]
        if not isinstance(s, dict):
            raise SystemExit(f"FAIL [{key}]: target must be an object")
        vendor = normalize_vendor(s.get("vendor"))
        rid = str(s.get("requested_id", "")).strip()
        if not vendor:
            raise SystemExit(f"FAIL [{key}]: unknown vendor")
        if not rid or PLACEHOLDER_RE.search(rid) or FLOATING_ALIAS_RE.search(rid):
            raise SystemExit(f"FAIL [{key}]: unresolved or floating requested_id")
    return cfg


def preflight_credentials(cfg):
    vendors = {normalize_vendor(s["vendor"]) for s in cfg.values()}
    missing = [ENV[v] for v in sorted(vendors) if not os.environ.get(ENV[v])]
    if missing:
        raise SystemExit("FAIL: missing required environment variables: " + ", ".join(missing))


def build_request(vendor, model_id, key):
    if vendor == "openai":
        url = ENDPOINTS[vendor]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body = {"model": model_id, "messages": [{"role": "user", "content": PROMPT}],
                "temperature": T, "top_p": TOP_P, "max_tokens": MAX_TOK}
    elif vendor == "anthropic":
        url = ENDPOINTS[vendor]
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        body = {"model": model_id, "max_tokens": MAX_TOK, "temperature": T, "top_p": TOP_P,
                "messages": [{"role": "user", "content": PROMPT}]}
    elif vendor == "google":
        url = ENDPOINTS[vendor].format(model=model_id)
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        body = {"contents": [{"parts": [{"text": PROMPT}]}],
                "generationConfig": {"temperature": T, "topP": TOP_P, "maxOutputTokens": MAX_TOK}}
    elif vendor == "cohere":
        url = ENDPOINTS[vendor]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body = {"model": model_id, "messages": [{"role": "user", "content": PROMPT}],
                "temperature": T, "p": TOP_P, "max_tokens": MAX_TOK}
    elif vendor == "mistral":
        url = ENDPOINTS[vendor]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body = {"model": model_id, "messages": [{"role": "user", "content": PROMPT}],
                "temperature": T, "top_p": TOP_P, "max_tokens": MAX_TOK}
    else:
        raise ValueError("unsupported vendor")
    return url, headers, json.dumps(body).encode("utf-8")


def safe_error(kind, status=None):
    out = {"type": kind}
    if status is not None:
        out["http_status"] = int(status)
    return out


def extract_echoed_model(payload):
    try:
        obj = json.loads(payload)
    except Exception:
        return ""
    value = obj.get("model") or obj.get("modelVersion") or ""
    return str(value)[:200] if value is not None else ""


def ping(slot, spec):
    vendor = normalize_vendor(spec["vendor"])
    model_id = spec["requested_id"]
    secret = os.environ[ENV[vendor]]
    url, headers, body = build_request(vendor, model_id, secret)
    result = {
        "key": slot,
        "vendor": vendor,
        "role": spec.get("role", ""),
        "requested_id": model_id,
        "endpoint": clean_endpoint(url),
        "http_status": None,
        "available": False,
        "latency_ms": None,
        "echoed_model_id": "",
        "error": None,
        "param_compliance": {"temperature": T, "top_p": TOP_P, "max_tokens": MAX_TOK},
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            status = int(resp.status)
            payload = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        result["latency_ms"] = int((time.time() - t0) * 1000)
        result["http_status"] = int(e.code)
        result["error"] = safe_error("HTTPError", e.code)
        return result
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        result["latency_ms"] = int((time.time() - t0) * 1000)
        result["error"] = safe_error("TransportError")
        return result
    except Exception:
        result["latency_ms"] = int((time.time() - t0) * 1000)
        result["error"] = safe_error("UnexpectedTransportError")
        return result
    result["latency_ms"] = int((time.time() - t0) * 1000)
    result["http_status"] = status
    if status != 200:
        result["error"] = safe_error("Non200", status)
        return result
    result["available"] = True
    result["echoed_model_id"] = extract_echoed_model(payload)
    return result


def assert_no_secret_leak(serialized, cfg):
    secrets = [os.environ.get(ENV[v], "") for v in ENV]
    for secret in secrets:
        if secret and secret in serialized:
            raise RuntimeError("refusing to save report: credential value detected")
    if KEYLIKE_RE.search(serialized):
        raise RuntimeError("refusing to save report: key-like token detected")
    if "?key=" in serialized.lower():
        raise RuntimeError("refusing to save report: query-string credential pattern detected")
    for spec in cfg.values():
        for k in spec:
            if k.lower() in {"api_key", "apikey", "token", "secret", "authorization"}:
                raise RuntimeError("refusing to run: secret-like field present in target config")


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "closed_api_targets.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "api_ping_check.json"
    cfg = load_targets(cfg_path)
    preflight_credentials(cfg)
    results = [ping(k, cfg[k]) for k in REQUIRED_KEYS]
    report = {
        "schema": "v8.6.3-credential-safe-engineering-ping-v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "prompt_class": "unrelated engineering connectivity prompt; no study item",
        "confirmatory_data": False,
        "results": results,
    }
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    assert_no_secret_leak(serialized, cfg)
    Path(out_path).write_text(serialized, encoding="utf-8")
    n_ok = sum(r["available"] for r in results)
    print(f"Wrote {out_path}: {n_ok}/{len(results)} available")
    return 0 if n_ok == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
