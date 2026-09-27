#!/usr/bin/env python3
"""Offline fail-closed collection-readiness gate for frozen v8.6.3.

This script performs NO network calls and reads NO credentials. It does not
amend MASTER_LOCK_v8_6_3.md. It only decides whether the operational evidence
needed to begin any v8.6.3 collection is complete enough to proceed.

Exit codes:
  0 = READY_FOR_ENGINEERING_PING_OR_COLLECTION_GATE (all automated checks pass)
  2 = BLOCKED (one or more required conditions unresolved)
  3 = malformed input / checker error

A zero exit code is not scientific validation and is not permission to replace
registered models. Human verification of exact model/snapshot identity and any
OSF successor amendment remains required where the frozen protocol requires it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

EXPECTED_ITEM_SHA256 = "128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3"
UTILITY_MODEL = "Yi-1.5-34B-Chat"
OPEN_MODELS = [
    "Meta-Llama-3.1-8B-Instruct",
    "Meta-Llama-3.1-70B-Instruct",
    "Meta-Llama-3.1-405B-Instruct",
    "Meta-Llama-3.3-70B-Instruct",
    "Qwen2.5-7B-Instruct",
    "Qwen2.5-32B-Instruct",
    "Qwen2.5-72B-Instruct",
    "Mistral-7B-Instruct-v0.3",
    "Mixtral-8x22B-Instruct-v0.1",
    "Gemma-2-9b-it",
    "Gemma-2-27b-it",
    "DeepSeek-V2.5",
]
CLOSED_SLOTS = [
    "openai_flagship", "openai_lightweight",
    "anthropic_flagship", "anthropic_lightweight",
    "google_flagship", "google_lightweight",
    "cohere_flagship", "mistral_flagship",
]
REGISTERED_CLOSED_CLASSES = {
    "openai_flagship": ("OpenAI", "gpt-4o class"),
    "openai_lightweight": ("OpenAI", "gpt-4o-mini class"),
    "anthropic_flagship": ("Anthropic", "Claude 3.5 Sonnet class"),
    "anthropic_lightweight": ("Anthropic", "Claude 3.5 Haiku class"),
    "google_flagship": ("Google", "Gemini 1.5 Pro class"),
    "google_lightweight": ("Google", "Gemini 1.5 Flash class"),
    "cohere_flagship": ("Cohere", "Command R+ class"),
    "mistral_flagship": ("Mistral AI", "Mistral Large class"),
}
PLACEHOLDER_RE = re.compile(r"REPLACE|PLACEHOLDER|TBD|TODO|DEFERRED_PENDING", re.I)
SECRET_NAME_RE = re.compile(r"(api[_-]?key|token|secret|authorization|bearer)", re.I)
FLOATING_ALIAS_RE = re.compile(r"(?:-latest|-stable|latest-|preview)", re.I)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def add(report, name, status, detail, **extra):
    row = {"check": name, "status": status, "detail": detail}
    row.update(extra)
    report["checks"].append(row)
    if status == "BLOCKED":
        report["blockers"].append(name)
    elif status == "WARN":
        report["warnings"].append(name)


def is_resolved_text(v) -> bool:
    return isinstance(v, str) and bool(v.strip()) and not PLACEHOLDER_RE.search(v)


def check_master(root: Path, report):
    p = root / "MASTER_LOCK_v8_6_3.md"
    if not p.is_file():
        add(report, "master_lock_present", "BLOCKED", "MASTER_LOCK_v8_6_3.md missing")
        return
    text = p.read_text(encoding="utf-8", errors="replace")
    required = [
        "Version 8.6.3",
        EXPECTED_ITEM_SHA256,
        "Yi-1.5-34B-Chat",
        "local inference via vLLM",
        "max_tokens = 256",
        "max_tokens = 16",
        "12 open-weights primary models",
        "8 closed API sensitivity snapshots",
        "direct documented successor",
        "OSF preregistration amendment",
    ]
    missing = [s for s in required if s not in text]
    if missing:
        add(report, "master_lock_content", "BLOCKED", f"missing locked markers: {missing}", sha256=sha256(p))
    else:
        add(report, "master_lock_content", "PASS", "required v8.6.3 operational markers present", sha256=sha256(p))


def check_item_pool(root: Path, report):
    p = root / "items_pool_v1.json"
    if not p.is_file():
        add(report, "item_pool", "BLOCKED", "items_pool_v1.json missing")
        return
    got = sha256(p)
    if got != EXPECTED_ITEM_SHA256:
        add(report, "item_pool", "BLOCKED", "item pool bytes do not match frozen SHA-256", expected=EXPECTED_ITEM_SHA256, observed=got)
        return
    try:
        items = read_json(p)
    except Exception as e:
        add(report, "item_pool", "BLOCKED", f"cannot parse item pool: {type(e).__name__}")
        return
    schema_ok = (
        isinstance(items, list) and len(items) == 260
        and len({x.get("item_id") for x in items if isinstance(x, dict)}) == 260
        and all(isinstance(x, dict) and set(x) == {"item_id", "category", "prompt_text"} for x in items)
    )
    add(report, "item_pool", "PASS" if schema_ok else "BLOCKED",
        "frozen SHA-256 and 260-item schema verified" if schema_ok else "hash matched but 260-item schema check failed",
        sha256=got)


def check_review_code(root: Path, report):
    p0 = root / "phase0_pipeline.py"
    c = root / "collect_gate5.py"
    mf = root / "make_frozen.py"
    for p in (p0, c, mf):
        if not p.is_file():
            add(report, f"review_source_{p.name}", "BLOCKED", f"{p.name} missing")
            continue
        add(report, f"review_source_{p.name}", "PASS", "present", sha256=sha256(p))
    if p0.is_file():
        t = p0.read_text(encoding="utf-8", errors="replace")
        ok = (
            'UTILITY_MODEL = "Yi-1.5-34B-Chat"' in t
            and "if model_id != UTILITY_MODEL" in t
            and "max_tokens=max_tokens" in t
            and "class _Mock" not in t
            and "Using mock utility" not in t
        )
        add(report, "review_phase0_exact_utility", "PASS" if ok else "BLOCKED",
            "review Phase 0 enforces exact Yi utility and has no mock fallback" if ok else "review Phase 0 utility enforcement/fallback check failed")
    if c.is_file():
        t = c.read_text(encoding="utf-8", errors="replace")
        ok = (
            "Exactly 20 bindings required" in t
            and "Unresolved {field} at position {pos}" in t
            and "completion(client, model_id" in t
            and "], 16)" in t
            and "Confirmatory launch is not enabled" in t
        )
        add(report, "review_collector_fail_closed", "PASS" if ok else "BLOCKED",
            "review collector requires resolved 20-slot bindings, uses 16-token candidate call, and keeps confirmatory launch disabled" if ok else "review collector fail-closed markers incomplete")


def check_roster(root: Path, report):
    p = root / "roster_bindings.json"
    template = root / "roster_bindings.template.json"
    if not p.is_file():
        detail = "roster_bindings.json missing"
        if template.is_file():
            detail += "; only unresolved template is present"
        add(report, "roster_bindings", "BLOCKED", detail)
        return
    try:
        cfg = read_json(p)
    except Exception as e:
        add(report, "roster_bindings", "BLOCKED", f"cannot parse: {type(e).__name__}")
        return
    expected = OPEN_MODELS + CLOSED_SLOTS
    problems = []
    if not isinstance(cfg, dict) or len(cfg) != 20:
        problems.append("must contain exactly 20 positions")
    else:
        ids = []
        for i, canonical in enumerate(expected, 1):
            b = cfg.get(str(i))
            if not isinstance(b, dict):
                problems.append(f"position {i} missing")
                continue
            if b.get("canonical") != canonical:
                problems.append(f"position {i} canonical mismatch")
            for fld in ("id", "endpoint", "revision", "verification_evidence"):
                if not is_resolved_text(b.get(fld)):
                    problems.append(f"position {i} unresolved {fld}")
            if is_resolved_text(b.get("id")):
                ids.append(b["id"].strip())
        if len(ids) != len(set(ids)):
            problems.append("deployment model IDs are not unique across 20 positions")
    add(report, "roster_bindings", "BLOCKED" if problems else "PASS",
        "; ".join(problems) if problems else "20 registered identities have explicit id/endpoint/revision/evidence bindings")


def check_closed_targets(root: Path, report):
    p = root / "closed_api_targets.json"
    if not p.is_file():
        add(report, "closed_api_targets", "BLOCKED", "closed_api_targets.json missing")
        return
    try:
        cfg = read_json(p)
    except Exception as e:
        add(report, "closed_api_targets", "BLOCKED", f"cannot parse: {type(e).__name__}")
        return
    problems = []
    if set(cfg) != set(CLOSED_SLOTS):
        problems.append("must contain exactly the 8 registered closed slots")
    for key in CLOSED_SLOTS:
        s = cfg.get(key, {})
        if not isinstance(s, dict):
            problems.append(f"{key}: not an object")
            continue
        rid = s.get("requested_id")
        if not is_resolved_text(rid):
            problems.append(f"{key}: unresolved requested_id")
        elif FLOATING_ALIAS_RE.search(rid):
            problems.append(f"{key}: floating/preview alias cannot establish a frozen snapshot")
    add(report, "closed_api_targets", "BLOCKED" if problems else "PASS",
        "; ".join(problems) if problems else "all 8 target IDs are explicitly populated (identity evidence still checked separately)")


def check_endpoint_resolution(root: Path, report):
    p = root / "closed_endpoint_resolution.json"
    if not p.is_file():
        add(report, "closed_endpoint_resolution", "BLOCKED",
            "missing manual evidence record for original snapshot vs same-vendor successor and OSF amendment status")
        return
    try:
        cfg = read_json(p)
    except Exception as e:
        add(report, "closed_endpoint_resolution", "BLOCKED", f"cannot parse: {type(e).__name__}")
        return
    problems = []
    for key in CLOSED_SLOTS:
        s = cfg.get(key)
        if not isinstance(s, dict):
            problems.append(f"{key}: missing")
            continue
        expected_vendor, expected_class = REGISTERED_CLOSED_CLASSES[key]
        if s.get("vendor") != expected_vendor or s.get("registered_class") != expected_class:
            problems.append(f"{key}: registered vendor/class mismatch")
        rtype = s.get("resolution_type")
        if rtype not in {"verified_original_snapshot", "verified_same_vendor_successor"}:
            problems.append(f"{key}: resolution_type unresolved")
        for fld in ("model_id", "endpoint", "snapshot_or_revision", "verification_evidence"):
            if not is_resolved_text(s.get(fld)):
                problems.append(f"{key}: unresolved {fld}")
        if rtype == "verified_same_vendor_successor":
            for fld in ("successor_of", "osf_amendment_reference", "amendment_date", "rationale"):
                if not is_resolved_text(s.get(fld)):
                    problems.append(f"{key}: successor missing {fld}")
    add(report, "closed_endpoint_resolution", "BLOCKED" if problems else "PASS",
        "; ".join(problems) if problems else "all 8 cells have explicit snapshot/successor evidence; successor cells include amendment record")


def scan_ping_source(path: Path):
    if not path.is_file():
        return False, ["missing"]
    t = path.read_text(encoding="utf-8", errors="replace")
    problems = []
    unsafe_url_lines = [line for line in t.splitlines()
                        if "url" in line and "?key=" in line and "serialized" not in line]
    if unsafe_url_lines:
        problems.append("Google credential appears in URL construction")
    if "x-goog-api-key" not in t:
        problems.append("Google API key is not sent via x-goog-api-key header")
    if "payload[:" in t or 'r["error"] = str(e)' in t:
        problems.append("raw error/response material may be serialized")
    if "assert_no_secret_leak" not in t:
        problems.append("no explicit output secret-leak guard")
    return not problems, problems


def check_safe_ping(root: Path, report):
    legacy = root / "api_ping_check.py"
    if legacy.is_file():
        t = legacy.read_text(encoding="utf-8", errors="replace")
        if "?key=" in t and 'r["endpoint"] = url' in t:
            add(report, "legacy_ping_safety", "WARN",
                "archived api_ping_check.py can serialize a Google key in the endpoint URL; preserve it for provenance but do not execute with live Gemini credentials")
        else:
            add(report, "legacy_ping_safety", "PASS", "no known URL-key serialization pattern detected")
    safe = root / "api_ping_check_safe.py"
    ok, problems = scan_ping_source(safe)
    add(report, "safe_ping_replacement", "PASS" if ok else "BLOCKED",
        "credential-safe replacement present" if ok else "; ".join(problems))


def check_ping_result(root: Path, report):
    p = root / "api_ping_check.json"
    if not p.is_file():
        add(report, "api_ping_check_result", "BLOCKED", "api_ping_check.json missing; no registered 8-cell availability evidence")
        return
    try:
        obj = read_json(p)
    except Exception as e:
        add(report, "api_ping_check_result", "BLOCKED", f"cannot parse: {type(e).__name__}")
        return
    rows = obj.get("results") if isinstance(obj, dict) else obj
    if not isinstance(rows, list) or len(rows) != 8:
        add(report, "api_ping_check_result", "BLOCKED", "ping report must contain exactly 8 cell results")
        return
    problems = []
    for row in rows:
        if not isinstance(row, dict):
            problems.append("non-object row")
            continue
        if row.get("key") not in CLOSED_SLOTS:
            problems.append("unknown/missing slot key")
        if row.get("available") is not True or row.get("http_status") != 200:
            problems.append(f"{row.get('key')}: unavailable/non-200")
        pc = row.get("param_compliance", {})
        if pc != {"temperature": 0.0, "top_p": 1.0, "max_tokens": 16}:
            problems.append(f"{row.get('key')}: decoding settings mismatch")
        endpoint = str(row.get("endpoint", ""))
        if "?" in endpoint or "key=" in endpoint.lower():
            problems.append(f"{row.get('key')}: saved endpoint contains query material")
        for k, v in row.items():
            if SECRET_NAME_RE.search(str(k)) and v not in (None, "", False):
                problems.append(f"{row.get('key')}: secret-like field serialized: {k}")
    add(report, "api_ping_check_result", "BLOCKED" if problems else "PASS",
        "; ".join(problems) if problems else "8-cell engineering availability report present at frozen candidate decoding settings")


def check_runtime_lock(root: Path, report):
    p = root / "runtime_lock.json"
    if not p.is_file():
        add(report, "runtime_lock", "BLOCKED", "runtime_lock.json missing")
        return
    try:
        obj = read_json(p)
    except Exception as e:
        add(report, "runtime_lock", "BLOCKED", f"cannot parse: {type(e).__name__}")
        return
    problems = []
    u = obj.get("utility", {})
    expected_pairs = {
        "canonical_model": UTILITY_MODEL,
        "model_id": UTILITY_MODEL,
        "engine": "vLLM",
        "deployment_mode": "local",
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 256,
    }
    for k, v in expected_pairs.items():
        if u.get(k) != v:
            problems.append(f"utility.{k} must equal {v!r}")
    for fld in ("weights_revision", "weights_verification", "endpoint", "verification_evidence"):
        if not is_resolved_text(u.get(fld)):
            problems.append(f"utility.{fld} unresolved")
    c = obj.get("candidate_decoding", {})
    if c != {"temperature": 0.0, "top_p": 1.0, "max_tokens": 16, "identical_retry_limit": 1, "sdk_automatic_retries": False}:
        problems.append("candidate_decoding must lock T=0, top_p=1, max_tokens=16, one identical retry, SDK retries off")
    ctx = obj.get("context_length", {})
    if ctx.get("tokenizer") != "cl100k_base":
        problems.append("context_length.tokenizer must be cl100k_base")
    if not is_resolved_text(ctx.get("measurement_scope")) or PLACEHOLDER_RE.search(str(ctx.get("measurement_scope", ""))):
        problems.append("context_length.measurement_scope unresolved")
    for fld in ("software", "adapters", "preflight_evidence"):
        v = obj.get(fld)
        if not v:
            problems.append(f"{fld} missing/empty")
    add(report, "runtime_lock", "BLOCKED" if problems else "PASS",
        "; ".join(problems) if problems else "exact Yi local-vLLM utility, candidate decoding, tokenizer, software/adapters and evidence are pinned")


def check_freeze_inputs(root: Path, report):
    required = [
        "MASTER_LOCK_v8_6_3.md", "estimator.py", "sensitivity.py",
        "collect_gate5.py", "phase0_pipeline.py", "make_frozen.py", "runlog.py",
        "items_pool_v1.json", "roster_bindings.json", "closed_api_targets.json",
        "api_ping_check.json", "runtime_lock.json",
    ]
    missing = [x for x in required if not (root / x).is_file()]
    if not (root / "api_ping_check_safe.py").is_file():
        missing.append("api_ping_check_safe.py")
    add(report, "runtime_freeze_inputs", "BLOCKED" if missing else "PASS",
        f"missing: {missing}" if missing else "all operational freeze inputs are present")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--output", default="v8_6_3_readiness_report.json")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    report = {
        "schema": "v8.6.3-offline-readiness-v1",
        "root": str(root),
        "network_calls": 0,
        "credentials_read": False,
        "confirmatory_data_collected": False,
        "checks": [], "blockers": [], "warnings": [],
    }
    try:
        check_master(root, report)
        check_item_pool(root, report)
        check_review_code(root, report)
        check_roster(root, report)
        check_closed_targets(root, report)
        check_endpoint_resolution(root, report)
        check_safe_ping(root, report)
        check_ping_result(root, report)
        check_runtime_lock(root, report)
        check_freeze_inputs(root, report)
    except Exception as e:
        report["checker_error"] = type(e).__name__
        report["checker_error_detail"] = str(e)
        report["status"] = "CHECKER_ERROR"
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 3
    report["status"] = "BLOCKED" if report["blockers"] else "READY_FOR_ENGINEERING_PING_OR_COLLECTION_GATE"
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["status"])
    for row in report["checks"]:
        print(f"{row['status']:7s} {row['check']}: {row['detail']}")
    print(f"Report: {Path(args.output).resolve()}")
    return 2 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
