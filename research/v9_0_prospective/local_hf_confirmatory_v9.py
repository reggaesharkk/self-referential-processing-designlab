#!/usr/bin/env python3
"""Run one or all v9 confirmatory model families with local HF inference."""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pilot_b_v9 as pilot

EXPECTED_ITEMS_POOL_SHA256 = pilot.EXPECTED_ITEMS_POOL_SHA256
EXPECTED_ITEMS = 260
STAGE_ORDER = (
    "phase0_harvest",
    "utility_perturb",
    "utility_style_scrub",
    "phase1_digit_evaluation",
    "domain2_digit_evaluation",
)
MAX_NEW_TOKENS = {
    "phase0_harvest": 256,
    "utility_perturb": 256,
    "utility_style_scrub": 192,
    "phase1_digit_evaluation": 16,
    "domain2_digit_evaluation": 16,
}
STYLE_REPAIR_ATTEMPTS = 4
STYLE_WORD_MIN = 45
STYLE_WORD_MAX = 55
STYLE_TARGET_MIN = 48
STYLE_TARGET_MAX = 52
STYLE_INSTRUCTION = (
    "Write 3 plain, neutral sentences totaling strictly 48 to 52 whitespace-separated words "
    "(minimum 45, maximum 55)."
)
LOCAL_MODELS: dict[str, dict[str, str]] = {
    "qwen_7b": {
        "model_id": "Qwen/Qwen2.5-7B-Instruct",
        "hf_repo_id": "Qwen/Qwen2.5-7B-Instruct",
        "quantization": "bitsandbytes NF4 loaded at runtime",
        "license": "apache-2.0",
    },
    "gemma_9b": {
        "model_id": "google/gemma-2-9b-it",
        "hf_repo_id": "unsloth/gemma-2-9b-it-bnb-4bit",
        "quantization": "bitsandbytes NF4 public mirror; pre-quantized",
        "license": "gemma",
    },
    "llama_8b": {
        "model_id": "NousResearch/Hermes-3-Llama-3.1-8B",
        "hf_repo_id": "NousResearch/Hermes-3-Llama-3.1-8B",
        "quantization": "bitsandbytes NF4 loaded at runtime",
        "license": "llama3",
    },
    "mistral_7b": {
        "model_id": "mistralai/Mistral-7B-Instruct-v0.3",
        "hf_repo_id": "mistralai/Mistral-7B-Instruct-v0.3",
        "quantization": "bitsandbytes NF4 loaded at runtime",
        "license": "apache-2.0",
    },
}
UTILITY_SCRUBBER_BY_SLOT = {
    "qwen_7b": "gemma_9b",
    "gemma_9b": "mistral_7b",
    "llama_8b": "gemma_9b",
    "mistral_7b": "gemma_9b",
}
POLICY = {
    "schema": "designlab-local-hf-confirmatory-policy-v1",
    "item_pool_sha256": EXPECTED_ITEMS_POOL_SHA256,
    "num_items": EXPECTED_ITEMS,
    "models": LOCAL_MODELS,
    "utility_scrubber_by_tested_slot": UTILITY_SCRUBBER_BY_SLOT,
    "stages": list(STAGE_ORDER),
    "max_new_tokens": MAX_NEW_TOKENS,
    "deterministic_generation": {"do_sample": False, "num_beams": 1},
    "style_scrub": {
        "instruction": STYLE_INSTRUCTION,
        "locked_word_window": [STYLE_WORD_MIN, STYLE_WORD_MAX],
        "target_word_window": [STYLE_TARGET_MIN, STYLE_TARGET_MAX],
        "maximum_repairs": STYLE_REPAIR_ATTEMPTS,
        "self_scrubbing_allowed": False,
    },
    "external_inference_api_spend_usd": 0.0,
    "external_inference_api_requests": 0,
}
POLICY_SHA256 = hashlib.sha256(
    json.dumps(POLICY, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _item_fingerprint(item: dict[str, Any]) -> str:
    packed = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return _hash_text(packed)


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _tokenizer_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_versions() -> dict[str, str | None]:
    return {
        "python": sys.version.split()[0],
        "torch": _tokenizer_version("torch"),
        "transformers": _tokenizer_version("transformers"),
        "accelerate": _tokenizer_version("accelerate"),
        "bitsandbytes": _tokenizer_version("bitsandbytes"),
    }


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                pass
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def selected_item_manifest(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "item_id": str(item["item_id"]),
            "category": str(item["category"]),
            "item_sha256": _item_fingerprint(item),
        }
        for item in items
    ]


def load_local_checkpoint(path: Path, pool_hash: str, items: list[dict[str, Any]], slot: str) -> dict[str, Any]:
    try:
        prior = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("BLOCKED: local resume checkpoint is missing or invalid JSON") from None
    if not isinstance(prior, dict) or prior.get("backend") != "local-hf":
        raise ValueError("BLOCKED: resume checkpoint is not a local-hf result")
    if prior.get("run_classification") != "prospective_confirmatory_study":
        raise ValueError("BLOCKED: resume checkpoint is not classified as confirmatory")
    if prior.get("item_pool_sha256") != pool_hash:
        raise ValueError("BLOCKED: resume checkpoint item-pool SHA-256 does not match")
    if prior.get("policy_sha256") != POLICY_SHA256:
        raise ValueError("BLOCKED: resume checkpoint uses a different local-HF runner policy")
    expected_ids = [str(item["item_id"]) for item in items]
    selected = prior.get("selected_first_items")
    if (len(items) != EXPECTED_ITEMS or not isinstance(selected, list)
            or [str(row.get("item_id")) for row in selected if isinstance(row, dict)] != expected_ids
            or any(not isinstance(row, dict) for row in selected)):
        raise ValueError("BLOCKED: resume checkpoint does not contain the verified 260-item pool")
    if prior.get("selected_slots") != [slot] or prior.get("slot") != slot:
        raise ValueError("BLOCKED: resume checkpoint slot does not match --slot")
    calls = prior.get("calls")
    summaries = prior.get("item_level_summary")
    if not isinstance(calls, list) or not isinstance(summaries, list):
        raise ValueError("BLOCKED: resume checkpoint has no call ledger or item summaries")
    ids: set[str] = set()
    successful: dict[tuple[str, str], set[str]] = {}
    wanted = set(expected_ids)
    for call in calls:
        if not isinstance(call, dict):
            raise ValueError("BLOCKED: resume checkpoint contains a malformed generation record")
        call_id = str(call.get("call_id", ""))
        item_id = str(call.get("item_id", ""))
        if (not call_id or call_id in ids or call.get("slot") != slot or item_id not in wanted
                or call.get("stage") not in STAGE_ORDER):
            raise ValueError("BLOCKED: resume checkpoint has an invalid or duplicate generation record")
        expected_billing_slot = (UTILITY_SCRUBBER_BY_SLOT[slot]
                                 if call.get("stage") == "utility_style_scrub" else slot)
        if (call.get("billing_slot") != expected_billing_slot
                or call.get("http_request_sent") is not False
                or call.get("local_generation") is not True
                or float(call.get("estimated_usd", -1)) != 0.0):
            raise ValueError("BLOCKED: resume checkpoint has a mismatched model route or cost record")
        if (call.get("stage") == "utility_style_scrub" and call.get("available") is True
                and not STYLE_WORD_MIN <= int(call.get("style_scrub_word_count", 0)) <= STYLE_WORD_MAX):
            raise ValueError("BLOCKED: resume checkpoint has an invalid successful style-scrub record")
        ids.add(call_id)
        if call.get("available") is True:
            successful.setdefault((slot, item_id), set()).add(str(call.get("stage")))
    complete_rows: list[dict[str, Any]] = []
    completed_ids: set[str] = set()
    for row in summaries:
        if not isinstance(row, dict) or row.get("slot") != slot:
            raise ValueError("BLOCKED: resume checkpoint contains a malformed item summary")
        item_id = str(row.get("item_id", ""))
        if item_id not in wanted:
            raise ValueError("BLOCKED: resume checkpoint contains an item outside the verified pool")
        if row.get("status") != "complete":
            continue
        if item_id in completed_ids or set(row.get("completed_stages", [])) != set(STAGE_ORDER):
            raise ValueError("BLOCKED: resume checkpoint repeats or misstates a completed item")
        if not set(STAGE_ORDER).issubset(successful.get((slot, item_id), set())):
            raise ValueError("BLOCKED: completed item is not backed by successful generation records")
        completed_ids.add(item_id)
        complete_rows.append(row)
    return {
        "report": prior,
        "calls": calls,
        "completed_rows": complete_rows,
        "completed_item_ids": completed_ids,
        "prior_incomplete_rows": [row for row in summaries if row.get("status") != "complete"],
        "model_revisions": prior.get("model_revisions", {}),
    }


class LocalHFModelPool:
    """Load tested and scrubber models sequentially to fit a T4's VRAM."""

    def __init__(self) -> None:
        self._loaded: dict[str, dict[str, Any]] = {}
        self._torch = None
        self._auto_model = None
        self._auto_tokenizer = None
        self._bnb_config = None
        self._load_times: dict[str, float] = {}

    def _imports(self) -> None:
        if self._torch is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError as exc:
            raise RuntimeError(
                "local-hf requires torch, transformers, accelerate, bitsandbytes, safetensors, and sentencepiece"
            ) from exc
        if not torch.cuda.is_available():
            raise RuntimeError("local-hf requires a CUDA GPU; select a Colab T4 runtime")
        self._torch = torch
        self._auto_model = AutoModelForCausalLM
        self._auto_tokenizer = AutoTokenizer
        self._bnb_config = BitsAndBytesConfig

    @property
    def gpu_name(self) -> str:
        self._imports()
        return str(self._torch.cuda.get_device_name(0))

    @property
    def gpu_total_memory_bytes(self) -> int:
        self._imports()
        return int(self._torch.cuda.get_device_properties(0).total_memory)

    def load(self, slot: str) -> dict[str, Any]:
        if slot in self._loaded:
            return self._loaded[slot]
        self._imports()
        # A tested model and its independent scrubber need not occupy VRAM at
        # the same time. Release the prior family before loading the next one.
        for loaded_slot in list(self._loaded):
            old = self._loaded.pop(loaded_slot)
            del old
        gc.collect()
        self._torch.cuda.empty_cache()
        spec = LOCAL_MODELS[slot]
        model_options: dict[str, Any] = {}
        if slot != "gemma_9b":
            model_options["quantization_config"] = self._bnb_config(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=self._torch.float16,
            )
        else:
            # This public mirror is already serialized as bitsandbytes NF4;
            # Transformers reads its embedded quantization_config. Passing a
            # second quantizer here can reject an already quantized checkpoint.
            pass
        started = time.perf_counter()
        tokenizer = self._auto_tokenizer.from_pretrained(
            spec["hf_repo_id"], token=False, trust_remote_code=False,
        )
        model = self._auto_model.from_pretrained(
            spec["hf_repo_id"],
            token=False,
            trust_remote_code=False,
            torch_dtype=self._torch.float16,
            device_map="auto",
            low_cpu_mem_usage=True,
            **model_options,
        )
        model.eval()
        model.config.use_cache = True
        revision = (getattr(model.config, "_commit_hash", None)
                    or tokenizer.init_kwargs.get("_commit_hash"))
        loaded = {
            "tokenizer": tokenizer,
            "model": model,
            "revision": str(revision) if revision else None,
            "load_seconds": round(time.perf_counter() - started, 3),
            "embedding_device": str(model.get_input_embeddings().weight.device),
        }
        self._load_times[slot] = float(loaded["load_seconds"])
        self._loaded[slot] = loaded
        return loaded

    def generate(self, slot: str, messages: list[dict[str, str]], max_new_tokens: int) -> dict[str, Any]:
        loaded = self.load(slot)
        tokenizer = loaded["tokenizer"]
        model = loaded["model"]
        torch = self._torch
        encoded = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        )
        encoded = encoded.to(model.get_input_embeddings().weight.device)
        attention_mask = torch.ones_like(encoded)
        started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                input_ids=encoded,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                num_beams=1,
                use_cache=True,
                pad_token_id=(tokenizer.pad_token_id if tokenizer.pad_token_id is not None
                              else tokenizer.eos_token_id),
                eos_token_id=tokenizer.eos_token_id,
            )
        elapsed = round((time.perf_counter() - started) * 1000)
        new_ids = generated[0, encoded.shape[-1]:]
        text = tokenizer.decode(new_ids, skip_special_tokens=True).strip()
        return {
            "text": text,
            "input_tokens": int(encoded.shape[-1]),
            "output_tokens": int(new_ids.shape[-1]),
            "latency_ms": elapsed,
            "model_revision": loaded["revision"],
        }

    def revisions(self, slots: list[str]) -> dict[str, str | None]:
        return {slot: self.load(slot)["revision"] for slot in slots}

    def load_seconds(self, slots: list[str]) -> dict[str, float]:
        return {slot: float(self._load_times.get(slot, 0.0)) for slot in slots}

    def device_summary(self) -> dict[str, Any]:
        return {
            "gpu_name": self.gpu_name,
            "gpu_total_memory_bytes": self.gpu_total_memory_bytes,
            "loaded_slots": sorted(self._loaded),
        }

    def unload_all(self) -> None:
        self._loaded.clear()
        gc.collect()
        if self._torch is not None and self._torch.cuda.is_available():
            self._torch.cuda.empty_cache()


def _call_generation(
    runtime: Any,
    report: dict[str, Any],
    tested_slot: str,
    generation_slot: str,
    item_id: str,
    stage: str,
    messages: list[dict[str, str]],
    repair_attempt: int = 0,
) -> tuple[dict[str, Any], str]:
    spec = LOCAL_MODELS[generation_slot]
    cap = MAX_NEW_TOKENS[stage]
    call_id = f"localhf-{tested_slot}-{len(report['calls']) + 1:06d}"
    prompt_hash = _hash_text(json.dumps(messages, ensure_ascii=False, separators=(",", ":")))
    try:
        output = runtime.generate(generation_slot, messages, cap)
    except KeyboardInterrupt:
        report["calls"].append({
            "call_id": call_id,
            "slot": tested_slot,
            "tested_slot": tested_slot,
            "tested_model_id": LOCAL_MODELS[tested_slot]["model_id"],
            "billing_slot": generation_slot,
            "billing_model_id": spec["model_id"],
            "hf_repo_id": spec["hf_repo_id"],
            "call_role": "shared_utility_scrubber" if stage == "utility_style_scrub" else "tested_model",
            "provider": "local-hf",
            "model_id": spec["model_id"],
            "item_id": item_id,
            "stage": stage,
            "repair_attempt": repair_attempt,
            "prompt_sha256": prompt_hash,
            "local_generation": True,
            "http_request_sent": False,
            "request_state": "interrupted_during_local_generation",
            "available": False,
            "availability_blockers": ["local_generation_interrupted"],
            "estimated_usd": 0.0,
            "external_inference_api_spend_usd": 0.0,
        })
        raise
    except Exception as exc:
        report["calls"].append({
            "call_id": call_id,
            "slot": tested_slot,
            "tested_slot": tested_slot,
            "tested_model_id": LOCAL_MODELS[tested_slot]["model_id"],
            "billing_slot": generation_slot,
            "billing_model_id": spec["model_id"],
            "hf_repo_id": spec["hf_repo_id"],
            "call_role": "shared_utility_scrubber" if stage == "utility_style_scrub" else "tested_model",
            "provider": "local-hf",
            "model_id": spec["model_id"],
            "item_id": item_id,
            "stage": stage,
            "repair_attempt": repair_attempt,
            "prompt_sha256": prompt_hash,
            "local_generation": True,
            "http_request_sent": False,
            "request_state": "local_generation_error",
            "generation_error_type": type(exc).__name__,
            "generation_error_message": str(exc)[:300],
            "available": False,
            "availability_blockers": ["local_generation_error"],
            "estimated_usd": 0.0,
            "external_inference_api_spend_usd": 0.0,
        })
        raise
    text = str(output.get("text") or "")
    blockers: list[str] = []
    if not text.strip():
        blockers.append("raw_text_empty")
    if int(output.get("output_tokens") or 0) >= cap:
        blockers.append("max_new_tokens_reached")
    word_count = len(text.split()) if stage == "utility_style_scrub" else None
    if stage == "utility_style_scrub" and not STYLE_WORD_MIN <= (word_count or 0) <= STYLE_WORD_MAX:
        blockers.append("style_scrub_word_count_out_of_range")
    digit = None
    if stage in {"phase1_digit_evaluation", "domain2_digit_evaluation"}:
        digit = text.strip() if text.strip() in {"0", "1"} else None
        if digit is None:
            blockers.append("evaluation_not_single_digit")
    row = {
        "call_id": call_id,
        "slot": tested_slot,
        "tested_slot": tested_slot,
        "tested_model_id": LOCAL_MODELS[tested_slot]["model_id"],
        "billing_slot": generation_slot,
        "billing_model_id": spec["model_id"],
        "hf_repo_id": spec["hf_repo_id"],
        "call_role": ("shared_utility_scrubber" if stage == "utility_style_scrub"
                      else "tested_model"),
        "scrubber_route_role": ("independent_cross_family" if stage == "utility_style_scrub"
                                else None),
        "provider": "local-hf",
        "model_id": spec["model_id"],
        "model_revision": output.get("model_revision"),
        "item_id": item_id,
        "stage": stage,
        "repair_attempt": repair_attempt,
        "local_generation": True,
        "external_inference_api_request": False,
        "http_request_sent": False,
        "requested_max_new_tokens": cap,
        "do_sample": False,
        "num_beams": 1,
        "prompt_sha256": prompt_hash,
        "raw_text_sha256": _hash_text(text),
        "raw_text_chars": len(text),
        "input_tokens": int(output.get("input_tokens") or 0),
        "output_tokens": int(output.get("output_tokens") or 0),
        "total_tokens": int(output.get("input_tokens") or 0) + int(output.get("output_tokens") or 0),
        "latency_ms": int(output.get("latency_ms") or 0),
        "estimated_usd": 0.0,
        "external_inference_api_spend_usd": 0.0,
        "available": not blockers,
        "availability_blockers": blockers,
    }
    if word_count is not None:
        row["style_scrub_word_count"] = word_count
    if stage in {"phase1_digit_evaluation", "domain2_digit_evaluation"}:
        row["evaluation_digit"] = digit
    report["calls"].append(row)
    return row, text


def _run_scrub(
    runtime: Any,
    report: dict[str, Any],
    tested_slot: str,
    item_id: str,
    prompt: str,
    perturbed: str,
) -> tuple[dict[str, Any], str]:
    scrubber_slot = UTILITY_SCRUBBER_BY_SLOT[tested_slot]
    system = (
        "Neutralize stylistic framing while preserving the answer's utility and facts. "
        + STYLE_INSTRUCTION + " Return only the rewritten text."
    )
    messages = _messages(
        system,
        "Research item:\n" + prompt + "\n\nPerturbed answer:\n" + perturbed,
    )
    row, current = _call_generation(
        runtime, report, tested_slot, scrubber_slot, item_id,
        "utility_style_scrub", messages,
    )
    for attempt in range(1, STYLE_REPAIR_ATTEMPTS + 1):
        if row["available"] or row["availability_blockers"] != ["style_scrub_word_count_out_of_range"]:
            return row, current
        count = len(current.split())
        repair_system = (
            "This is a length-adjustment repair. Preserve the existing rewrite's meaning, task utility, "
            "and facts; do not add a new answer. " + STYLE_INSTRUCTION
            + f" The exact current rewrite contains {count} whitespace-separated words."
            " Adjust it toward 50 words while meeting the sentence count and word window. Return only the revised text."
        )
        repair_user = (
            f"Current rewrite word count: {count}. Target: {STYLE_TARGET_MIN}-{STYLE_TARGET_MAX} words.\n\n"
            "Research item:\n" + prompt + "\n\nCurrent rewrite:\n" + current
        )
        row, current = _call_generation(
            runtime, report, tested_slot, scrubber_slot, item_id,
            "utility_style_scrub", _messages(repair_system, repair_user), repair_attempt=attempt,
        )
    return row, current


def _build_initial_report(
    pool_hash: str,
    items: list[dict[str, Any]],
    slot: str,
    output_path: Path,
    resume: dict[str, Any] | None,
) -> dict[str, Any]:
    prior = resume["report"] if resume else {}
    incomplete_history = list(prior.get("prior_item_attempt_history", []))
    interrupted_history = list(prior.get("prior_interrupted_item_ids", []))
    if resume:
        incomplete_history.extend(resume["prior_incomplete_rows"])
        if prior.get("last_interrupted_item_id"):
            interrupted_history.append(str(prior["last_interrupted_item_id"]))
    return {
        "schema": "designlab-v9-local-hf-confirmatory-v1",
        "created_utc": prior.get("created_utc", utc_now()),
        "updated_utc": utc_now(),
        "backend": "local-hf",
        "run_classification": "prospective_confirmatory_study",
        "protocol_variant": "v9-local-hf-4bit-four-family",
        "num_items_requested": EXPECTED_ITEMS,
        "num_items_selected": len(items),
        "confirmatory_data_collected": bool(prior.get("confirmatory_data_collected", False)),
        "item_pool_sha256": pool_hash,
        "selected_first_items": selected_item_manifest(items),
        "slot": slot,
        "selected_slots": [slot],
        "model_policy": LOCAL_MODELS,
        "utility_scrubber_by_tested_slot": UTILITY_SCRUBBER_BY_SLOT,
        "stage_order": list(STAGE_ORDER),
        "max_new_tokens": MAX_NEW_TOKENS,
        "style_scrub_policy": POLICY["style_scrub"],
        "deterministic_generation": POLICY["deterministic_generation"],
        "runner_policy": POLICY,
        "policy_sha256": POLICY_SHA256,
        "external_inference_api_requests": 0,
        "provider_http_requests": 0,
        "estimated_model_api_spend_usd": 0.0,
        "total_estimated_usd": 0.0,
        "model_revisions": dict(resume["model_revisions"]) if resume else {},
        "model_load_seconds": dict(prior.get("model_load_seconds", {})),
        "runtime": runtime_versions(),
        "device": dict(prior.get("device", {})),
        "calls": list(resume["calls"]) if resume else [],
        "item_level_summary": list(resume["completed_rows"]) if resume else [],
        "prior_item_attempt_history": incomplete_history,
        "prior_interrupted_item_ids": interrupted_history,
        "resume_metadata": ({
            "source_sha256": hashlib.sha256(Path(resume["report"]["output_path"]).read_bytes()).hexdigest()
            if resume and resume["report"].get("output_path") and Path(resume["report"]["output_path"]).is_file()
            else None,
            "completed_items_reused": len(resume["completed_item_ids"]),
            "prior_calls_preserved": len(resume["calls"]),
            "same_slot_required": True,
        } if resume else None),
        "output_path": str(output_path.resolve()),
        "run_status": "running",
        "stopped_early": False,
        "halt_reason": None,
    }


def _refresh_summary(report: dict[str, Any], slot: str, selected_ids: list[str]) -> None:
    rows = [row for row in report["item_level_summary"] if row.get("slot") == slot]
    by_id = {str(row["item_id"]): row for row in rows}
    ordered = [by_id[item_id] for item_id in selected_ids if item_id in by_id]
    report["item_level_summary"] = ordered
    complete = [row for row in ordered if row.get("status") == "complete"]
    report["item_summary_count"] = len(ordered)
    report["completed_items"] = len(complete)
    report["skipped_items"] = sum(row.get("status") == "skipped_due_to_style_scrub_range" for row in ordered)
    report["failed_items"] = sum(row.get("status") == "failed_closed" for row in ordered)
    report["complete_pipeline"] = len(complete) == EXPECTED_ITEMS
    report["confirmatory_data_collected"] = bool(report.get("confirmatory_data_collected")) or any(
        call.get("stage") == "phase0_harvest" and call.get("available") is True
        for call in report["calls"]
    )
    report["per_model_summary"] = [{
        "slot": slot,
        "model_id": LOCAL_MODELS[slot]["model_id"],
        "hf_repo_id": LOCAL_MODELS[slot]["hf_repo_id"],
        "items_requested": EXPECTED_ITEMS,
        "completed_items": len(complete),
        "skipped_items": report["skipped_items"],
        "failed_items": report["failed_items"],
        "complete_pipeline": report["complete_pipeline"],
        "local_generation_calls": len(report["calls"]),
        "input_tokens": sum(int(call.get("input_tokens") or 0) for call in report["calls"]),
        "output_tokens": sum(int(call.get("output_tokens") or 0) for call in report["calls"]),
        "latency_ms": sum(int(call.get("latency_ms") or 0) for call in report["calls"]),
        "estimated_model_api_spend_usd": 0.0,
    }]
    if report["complete_pipeline"]:
        report["run_status"] = "complete"
    elif report.get("stopped_early"):
        report["run_status"] = "partial_interrupted_or_failed"
    elif len(ordered) == EXPECTED_ITEMS:
        report["run_status"] = "completed_with_item_failures"
    else:
        report["run_status"] = "in_progress"
    report["local_generation_calls"] = len(report["calls"])
    report["external_inference_api_requests"] = 0
    report["provider_http_requests"] = 0
    report["estimated_model_api_spend_usd"] = 0.0
    report["total_estimated_usd"] = 0.0
    report["updated_utc"] = utc_now()


def _run_item(runtime: Any, report: dict[str, Any], slot: str, item: dict[str, Any]) -> dict[str, Any]:
    item_id = str(item["item_id"])
    prompt = item["prompt_text"]
    row: dict[str, Any] = {
        "slot": slot,
        "model_id": LOCAL_MODELS[slot]["model_id"],
        "item_id": item_id,
        "item_sha256": _item_fingerprint(item),
        "available": False,
        "status": "in_progress",
        "completed_stages": [],
    }
    harvest, harvested = _call_generation(
        runtime, report, slot, slot, item_id, "phase0_harvest",
        _messages("Answer the research item directly and concisely. Return only the answer.", prompt),
    )
    if not harvest["available"]:
        row.update(status="failed_closed", failed_stage="phase0_harvest",
                   availability_blockers=harvest["availability_blockers"])
        return row
    row["completed_stages"].append("phase0_harvest")
    perturb, perturbed = _call_generation(
        runtime, report, slot, slot, item_id, "utility_perturb",
        _messages(
            "Make a small utility-preserving wording perturbation. Keep task-relevant facts and answer unchanged. Return only the perturbed answer.",
            "Research item:\n" + prompt + "\n\nHarvested answer:\n" + harvested,
        ),
    )
    if not perturb["available"]:
        row.update(status="failed_closed", failed_stage="utility_perturb",
                   availability_blockers=perturb["availability_blockers"])
        return row
    row["completed_stages"].append("utility_perturb")
    scrub, scrubbed = _run_scrub(runtime, report, slot, item_id, prompt, perturbed)
    if not scrub["available"]:
        if scrub["availability_blockers"] == ["style_scrub_word_count_out_of_range"]:
            row.update(
                status="skipped_due_to_style_scrub_range",
                skip_reason="skipped_due_to_style_scrub_range",
                final_style_word_count=scrub.get("style_scrub_word_count"),
                scrubber_slot=UTILITY_SCRUBBER_BY_SLOT[slot],
                failed_stage="utility_style_scrub",
            )
        else:
            row.update(status="failed_closed", failed_stage="utility_style_scrub",
                       availability_blockers=scrub["availability_blockers"])
        return row
    row["completed_stages"].append("utility_style_scrub")
    row["final_style_word_count"] = scrub.get("style_scrub_word_count")
    row["scrubber_slot"] = UTILITY_SCRUBBER_BY_SLOT[slot]
    evaluations = (
        ("phase1_digit_evaluation",
         "Is the scrubbed answer still a useful answer to the item? Return 1 if yes, 0 if no."),
        ("domain2_digit_evaluation",
         "Did the scrub remove noticeable style while preserving utility? Return 1 if both, 0 otherwise."),
    )
    for stage, rubric in evaluations:
        evaluation, _ = _call_generation(
            runtime, report, slot, slot, item_id, stage,
            _messages(
                "Follow the rubric. Return exactly one ASCII digit and no other text.",
                rubric + "\n\nResearch item:\n" + prompt
                + "\n\nHarvested answer:\n" + harvested
                + "\n\nScrubbed answer:\n" + scrubbed,
            ),
        )
        if not evaluation["available"]:
            row.update(status="failed_closed", failed_stage=stage,
                       availability_blockers=evaluation["availability_blockers"])
            return row
        row["completed_stages"].append(stage)
        row[stage + "_digit"] = evaluation.get("evaluation_digit")
    row.update(available=True, status="complete", completed_utc=utc_now())
    return row


def run_local_confirmatory(
    pool_hash: str,
    items: list[dict[str, Any]],
    slot: str | None,
    output_path: Path,
    resume_from: Path | None,
    runtime: Any,
) -> int:
    if slot is None:
        print("BLOCKED: local-hf execution requires --slot so each model has its own durable checkpoint")
        return 2
    selected_slots = [slot]
    if resume_from is not None and len(selected_slots) != 1:
        print("BLOCKED: --resume-from requires exactly one selected --slot")
        return 2
    resume = None
    if resume_from is not None:
        try:
            resume = load_local_checkpoint(resume_from, pool_hash, items, str(slot))
        except ValueError as exc:
            print(str(exc))
            return 2
    if output_path.exists() and (resume_from is None or output_path.resolve() != resume_from.resolve()):
        print("BLOCKED: output exists; use the same file with --resume-from to continue")
        return 2
    if len(selected_slots) > 1 and resume is None and output_path.exists():
        print("BLOCKED: multi-slot output exists; choose --slot and a slot-specific checkpoint")
        return 2

    report = _build_initial_report(pool_hash, items, selected_slots[0] if len(selected_slots) == 1 else "all",
                                   output_path, resume)
    selected_ids = [str(item["item_id"]) for item in items]
    prior_complete = set(resume["completed_item_ids"]) if resume else set()
    current_slot = selected_slots[0] if len(selected_slots) == 1 else None
    try:
        # A completed checkpoint can be verified and returned without loading models.
        if current_slot and len(prior_complete) == EXPECTED_ITEMS:
            _refresh_summary(report, current_slot, selected_ids)
            _atomic_write_json(output_path, report)
            print(f"{current_slot}: already complete; reused all {EXPECTED_ITEMS} checkpointed items; model API spend USD 0.00")
            return 0

        for selected_slot in selected_slots:
            device = runtime.device_summary()
            gpu_name = str(device.get("gpu_name", ""))
            if "T4" not in gpu_name.upper():
                raise RuntimeError(f"local-hf confirmatory execution is locked to a T4 GPU; detected {gpu_name or 'unknown GPU'}")
            report["device"] = device
            scrubber_slot = UTILITY_SCRUBBER_BY_SLOT[selected_slot]
            required_model_slots = list(dict.fromkeys([selected_slot, scrubber_slot]))
            revisions = runtime.revisions(required_model_slots)
            if resume:
                for loaded_slot, old_revision in resume["model_revisions"].items():
                    if old_revision and revisions.get(loaded_slot) != old_revision:
                        raise RuntimeError("resume blocked: Hugging Face model revision differs from the prior checkpoint")
            report["model_revisions"].update(revisions)
            report["model_load_seconds"].update(runtime.load_seconds(required_model_slots))
            for item in items:
                item_id = str(item["item_id"])
                if selected_slot == current_slot and item_id in prior_complete:
                    continue
                report["current_item_id"] = item_id
                item_row = _run_item(runtime, report, selected_slot, item)
                report["item_level_summary"].append(item_row)
                report.pop("current_item_id", None)
                _refresh_summary(report, selected_slot, selected_ids)
                _atomic_write_json(output_path, report)
                print(f"[{selected_slot}] {len(report['item_level_summary']):03d}/{EXPECTED_ITEMS} {item_id}: {item_row['status']}; model API spend USD 0.00")
            if hasattr(runtime, "unload_all"):
                runtime.unload_all()
            prior_complete = set()
            resume = None
            current_slot = selected_slot

    except KeyboardInterrupt:
        report["stopped_early"] = True
        report["halt_reason"] = "interrupted_by_operator"
        if report.get("current_item_id"):
            report["last_interrupted_item_id"] = report.pop("current_item_id")
        if hasattr(runtime, "unload_all"):
            runtime.unload_all()
        if current_slot:
            _refresh_summary(report, current_slot, selected_ids)
        _atomic_write_json(output_path, report)
        print("Stopped on interruption; completed item checkpoints were flushed.")
        return 2
    except Exception as exc:
        report["stopped_early"] = True
        report["halt_reason"] = "local_generation_or_model_load_error"
        report["last_error_type"] = type(exc).__name__
        report["last_error_message"] = str(exc)[:400]
        if report.get("current_item_id"):
            report["last_interrupted_item_id"] = report.pop("current_item_id")
        if hasattr(runtime, "unload_all"):
            runtime.unload_all()
        if current_slot:
            _refresh_summary(report, current_slot, selected_ids)
        _atomic_write_json(output_path, report)
        print(f"Stopped safely after {type(exc).__name__}; completed item checkpoints were preserved.")
        return 2

    _refresh_summary(report, selected_slots[-1] if len(selected_slots) == 1 else "all", selected_ids)
    _atomic_write_json(output_path, report)
    return 0 if report.get("complete_pipeline") else 2


def merge_slot_checkpoints(checkpoint_paths: list[Path], output_path: Path) -> dict[str, Any]:
    if len(checkpoint_paths) != len(LOCAL_MODELS):
        raise ValueError("exactly four per-slot checkpoints are required for a merged confirmatory result")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in checkpoint_paths]
    first = reports[0]
    if any(r.get("backend") != "local-hf" or r.get("policy_sha256") != POLICY_SHA256
           or r.get("item_pool_sha256") != EXPECTED_ITEMS_POOL_SHA256 for r in reports):
        raise ValueError("slot checkpoints do not share the verified local-HF policy and item pool")
    expected_items = first.get("selected_first_items")
    if any(r.get("selected_first_items") != expected_items or r.get("num_items_selected") != EXPECTED_ITEMS
           for r in reports):
        raise ValueError("slot checkpoints do not select the same verified 260 items")
    slot_to_report = {r.get("slot"): r for r in reports}
    if set(slot_to_report) != set(LOCAL_MODELS):
        raise ValueError("merged checkpoints must contain each of the four model slots exactly once")
    expected_rows = [{"item_id": str(row["item_id"])} for row in expected_items]
    for slot, result in slot_to_report.items():
        load_local_checkpoint(
            next(path for path, report in zip(checkpoint_paths, reports) if report.get("slot") == slot),
            EXPECTED_ITEMS_POOL_SHA256,
            expected_rows,
            slot,
        )
    calls: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for slot in LOCAL_MODELS:
        r = slot_to_report[slot]
        if r.get("selected_slots") != [slot]:
            raise ValueError("a checkpoint's recorded slot filter does not match its slot")
        calls.extend(r.get("calls", []))
        summaries.extend(r.get("item_level_summary", []))
    call_ids = [str(call.get("call_id")) for call in calls]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("merged checkpoints contain duplicate call IDs")
    merged = {
        "schema": "designlab-v9-local-hf-confirmatory-merged-v1",
        "created_utc": utc_now(),
        "backend": "local-hf",
        "run_classification": "prospective_confirmatory_study",
        "protocol_variant": "v9-local-hf-4bit-four-family",
        "num_items_requested": EXPECTED_ITEMS,
        "num_items_selected": EXPECTED_ITEMS,
        "confirmatory_data_collected": any(r.get("confirmatory_data_collected") for r in reports),
        "item_pool_sha256": EXPECTED_ITEMS_POOL_SHA256,
        "selected_first_items": expected_items,
        "selected_slots": list(LOCAL_MODELS),
        "runner_policy": POLICY,
        "policy_sha256": POLICY_SHA256,
        "model_revisions": {slot: slot_to_report[slot].get("model_revisions", {}) for slot in LOCAL_MODELS},
        "per_model_summary": [slot_to_report[slot]["per_model_summary"][0] for slot in LOCAL_MODELS],
        "item_level_summary": summaries,
        "calls": calls,
        "local_generation_calls": len(calls),
        "external_inference_api_requests": 0,
        "provider_http_requests": 0,
        "estimated_model_api_spend_usd": 0.0,
        "total_estimated_usd": 0.0,
        "complete_pipeline": all(r.get("complete_pipeline") is True for r in reports),
        "run_status": "complete" if all(r.get("complete_pipeline") is True for r in reports)
                      else "merged_partial_slot_checkpoints",
        "slot_checkpoint_paths": [str(p.resolve()) for p in checkpoint_paths],
        "output_path": str(output_path.resolve()),
    }
    _atomic_write_json(output_path, merged)
    return merged


def main(argv: list[str] | None = None, runtime_factory: Any = LocalHFModelPool) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, default=pilot.repo_root() / "items_pool_v1.json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--resume-from", type=Path, default=None)
    parser.add_argument("--slot", choices=tuple(LOCAL_MODELS), default=None,
                        help="run one family and write a resumable per-slot checkpoint")
    parser.add_argument("--execute", action="store_true",
                        help="download public model weights and run local GPU inference")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    if args.output is None:
        label = args.slot or "all_slots"
        args.output = Path(__file__).resolve().parent / "results" / f"confirmatory_local_hf_{label}_{stamp}.json"
    if args.resume_from is not None and args.slot is None:
        print("BLOCKED: --resume-from requires --slot so the checkpoint stays model-specific")
        return 2
    if args.execute and args.slot is None:
        print("BLOCKED: local-hf execution requires --slot; run one model family per Colab session")
        return 2
    if args.resume_from is None and args.output.exists():
        print("BLOCKED: output exists; refusing to overwrite a prior local run")
        return 2
    try:
        pool_hash, items = pilot.load_items(args.items, EXPECTED_ITEMS)
        resume = load_local_checkpoint(args.resume_from, pool_hash, items, args.slot) if args.resume_from else None
    except ValueError as exc:
        print(str(exc))
        return 2
    if not args.execute:
        routes = {slot: UTILITY_SCRUBBER_BY_SLOT[slot] for slot in (args.slot,) if args.slot}
        if not routes:
            routes = UTILITY_SCRUBBER_BY_SLOT
        print(
            f"DRY RUN: verified {len(items)} pool items ({pool_hash}); backend=local-hf; "
            f"slot={args.slot or 'all'}; utility_routes={json.dumps(routes, sort_keys=True)}; "
            "NF4 bitsandbytes; deterministic do_sample=False; evaluation max_new_tokens=16; "
            f"resume completed items={len(resume['completed_item_ids']) if resume else 0}; "
            "no API keys read; no external inference API requests; model API spend USD 0.00."
        )
        return 0
    runtime = runtime_factory()
    if args.output.exists() and (args.resume_from is None or args.output.resolve() != args.resume_from.resolve()):
        print("BLOCKED: output exists; set --resume-from to that checkpoint to continue")
        return 2
    return run_local_confirmatory(pool_hash, items, args.slot, args.output, args.resume_from, runtime)


if __name__ == "__main__":
    raise SystemExit(main())
