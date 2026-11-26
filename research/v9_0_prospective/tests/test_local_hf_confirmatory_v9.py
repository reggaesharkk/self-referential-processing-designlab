from __future__ import annotations

import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

V9_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V9_DIR))

import confirmatory_v9 as confirmatory
import local_hf_confirmatory_v9 as local


def make_items(count: int = 260) -> list[dict[str, str]]:
    return [
        {"item_id": f"TR_{index:03d}", "category": "offline-test", "prompt_text": f"Prompt {index}"}
        for index in range(1, count + 1)
    ]


def make_complete_checkpoint(items: list[dict[str, str]], slot: str) -> dict:
    calls = []
    stages = list(local.STAGE_ORDER)
    for index, stage in enumerate(stages, 1):
        calls.append({
            "call_id": f"localhf-{slot}-{index:06d}",
            "slot": slot,
            "billing_slot": local.UTILITY_SCRUBBER_BY_SLOT[slot]
            if stage == "utility_style_scrub" else slot,
            "item_id": items[0]["item_id"],
            "stage": stage,
            "available": True,
            "local_generation": True,
            "http_request_sent": False,
            "estimated_usd": 0.0,
            **({"style_scrub_word_count": 48} if stage == "utility_style_scrub" else {}),
        })
    row = {
        "slot": slot,
        "item_id": items[0]["item_id"],
        "status": "complete",
        "available": True,
        "completed_stages": stages,
    }
    return {
        "schema": "designlab-v9-local-hf-confirmatory-v1",
        "backend": "local-hf",
        "run_classification": "prospective_confirmatory_study",
        "item_pool_sha256": local.EXPECTED_ITEMS_POOL_SHA256,
        "policy_sha256": local.POLICY_SHA256,
        "selected_first_items": local.selected_item_manifest(items),
        "num_items_requested": 260,
        "num_items_selected": 260,
        "slot": slot,
        "selected_slots": [slot],
        "calls": calls,
        "item_level_summary": [row],
        "model_revisions": {},
        "per_model_summary": [{"slot": slot, "complete_pipeline": False}],
    }


class FakeRuntime:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.calls = 0
        self.fail_on_call = fail_on_call

    def revisions(self, slots: list[str]) -> dict[str, str]:
        return {slot: "offline-revision-" + slot for slot in slots}

    def load_seconds(self, slots: list[str]) -> dict[str, float]:
        return {slot: 0.0 for slot in slots}

    def device_summary(self) -> dict:
        return {"gpu_name": "Tesla T4 (mock)", "gpu_total_memory_bytes": 16_000_000_000}

    def generate(self, slot: str, messages: list[dict[str, str]], max_new_tokens: int) -> dict:
        self.calls += 1
        if self.fail_on_call == self.calls:
            raise RuntimeError("offline simulated disconnect")
        system = messages[0]["content"]
        if system.startswith("Neutralize stylistic framing"):
            sentence = " ".join(["neutral"] * 16) + "."
            text = " ".join([sentence, sentence, sentence])
            output_tokens = 50
        elif "Return exactly one ASCII digit" in system:
            text = "1"
            output_tokens = 1
        elif system.startswith("Make a small utility-preserving"):
            text = "Perturbed answer."
            output_tokens = 4
        else:
            text = "Harvested answer."
            output_tokens = 3
        return {
            "text": text,
            "input_tokens": max(1, len(messages[1]["content"].split())),
            "output_tokens": output_tokens,
            "latency_ms": 1,
            "model_revision": "offline-revision-" + slot,
        }

    def unload_all(self) -> None:
        return None


class LocalHFPolicyTests(unittest.TestCase):
    def test_model_family_ids_and_independent_scrub_routes(self) -> None:
        self.assertEqual(set(local.LOCAL_MODELS), {"qwen_7b", "gemma_9b", "llama_8b", "mistral_7b"})
        self.assertEqual(local.LOCAL_MODELS["qwen_7b"]["model_id"], "Qwen/Qwen2.5-7B-Instruct")
        self.assertEqual(local.LOCAL_MODELS["gemma_9b"]["hf_repo_id"], "unsloth/gemma-2-9b-it-bnb-4bit")
        self.assertEqual(local.LOCAL_MODELS["llama_8b"]["model_id"], "NousResearch/Hermes-3-Llama-3.1-8B")
        self.assertEqual(local.LOCAL_MODELS["mistral_7b"]["model_id"], "mistralai/Mistral-7B-Instruct-v0.3")
        self.assertEqual(local.UTILITY_SCRUBBER_BY_SLOT, {
            "qwen_7b": "gemma_9b", "gemma_9b": "mistral_7b",
            "llama_8b": "gemma_9b", "mistral_7b": "gemma_9b",
        })
        self.assertEqual(local.MAX_NEW_TOKENS["phase1_digit_evaluation"], 16)
        self.assertEqual(local.MAX_NEW_TOKENS["domain2_digit_evaluation"], 16)
        self.assertEqual(local.POLICY["external_inference_api_requests"], 0)
        self.assertEqual(local.POLICY["external_inference_api_spend_usd"], 0.0)

    def test_wrapper_routes_local_backend_without_openrouter_execution(self) -> None:
        seen: list[str] = []
        with patch("local_hf_confirmatory_v9.main", side_effect=lambda argv: seen.extend(argv) or 0):
            self.assertEqual(confirmatory.main([
                "--backend", "local-hf", "--slot", "qwen_7b", "--execute",
                "--output", "qwen.json", "--resume-from", "qwen.json",
            ]), 0)
        self.assertIn("--slot", seen)
        self.assertEqual(seen[seen.index("--slot") + 1], "qwen_7b")
        self.assertIn("--resume-from", seen)
        self.assertIn("--execute", seen)

    def test_model_pool_releases_prior_family_and_uses_embedded_gemma_nf4(self) -> None:
        calls = []

        class FakeTokenizer:
            init_kwargs = {"_commit_hash": "offline-tokenizer-revision"}
            pad_token_id = 0
            eos_token_id = 1

        class FakeAutoTokenizer:
            @staticmethod
            def from_pretrained(model_id: str, **kwargs: object) -> FakeTokenizer:
                calls.append(("tokenizer", model_id, kwargs))
                return FakeTokenizer()

        class FakeModel:
            def __init__(self) -> None:
                self.config = SimpleNamespace(_commit_hash="offline-model-revision", use_cache=False)

            def eval(self) -> None:
                return None

            def get_input_embeddings(self) -> object:
                return SimpleNamespace(weight=SimpleNamespace(device="cuda:0"))

        class FakeAutoModel:
            @staticmethod
            def from_pretrained(model_id: str, **kwargs: object) -> FakeModel:
                calls.append(("model", model_id, kwargs))
                return FakeModel()

        class FakeCuda:
            @staticmethod
            def empty_cache() -> None:
                return None

        pool = local.LocalHFModelPool()
        pool._torch = SimpleNamespace(cuda=FakeCuda(), float16="fp16")
        pool._auto_model = FakeAutoModel
        pool._auto_tokenizer = FakeAutoTokenizer
        pool._bnb_config = lambda **kwargs: {"mock_nf4": kwargs}

        pool.load("qwen_7b")
        pool.load("gemma_9b")

        self.assertEqual(set(pool._loaded), {"gemma_9b"})
        load_count = len([entry for entry in calls if entry[0] == "model"])
        self.assertEqual(set(pool.load_seconds(["qwen_7b", "gemma_9b"])), {"qwen_7b", "gemma_9b"})
        self.assertEqual(len([entry for entry in calls if entry[0] == "model"]), load_count)
        model_calls = [entry for entry in calls if entry[0] == "model"]
        self.assertIn("quantization_config", model_calls[0][2])
        self.assertNotIn("quantization_config", model_calls[1][2])

    def test_checkpoint_loader_reuses_only_verified_complete_items(self) -> None:
        items = make_items()
        prior = make_complete_checkpoint(items, "qwen_7b")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "qwen.json"
            path.write_text(json.dumps(prior), encoding="utf-8")
            loaded = local.load_local_checkpoint(path, local.EXPECTED_ITEMS_POOL_SHA256, items, "qwen_7b")
            self.assertEqual(loaded["completed_item_ids"], {items[0]["item_id"]})
            bad = dict(prior, item_pool_sha256="0" * 64)
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "item-pool SHA-256"):
                local.load_local_checkpoint(path, local.EXPECTED_ITEMS_POOL_SHA256, items, "qwen_7b")

    def test_completed_item_is_flushed_before_a_later_disconnect(self) -> None:
        items = make_items(2)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "checkpoint.json"
            status = local.run_local_confirmatory(
                local.EXPECTED_ITEMS_POOL_SHA256, items, "qwen_7b", output, None,
                FakeRuntime(fail_on_call=6),
            )
            self.assertEqual(status, 2)
            checkpoint = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["completed_items"], 1)
        self.assertEqual(checkpoint["item_level_summary"][0]["item_id"], items[0]["item_id"])
        self.assertEqual(checkpoint["item_level_summary"][0]["status"], "complete")
        self.assertEqual(checkpoint["external_inference_api_requests"], 0)
        self.assertEqual(checkpoint["estimated_model_api_spend_usd"], 0.0)

    def test_four_slot_merge_verifies_pool_policy_and_has_zero_api_spend(self) -> None:
        items = make_items()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = []
            for slot in local.LOCAL_MODELS:
                report = make_complete_checkpoint(items, slot)
                report["item_level_summary"] = []
                report["calls"] = []
                report["per_model_summary"] = [{"slot": slot, "complete_pipeline": False}]
                path = root / f"{slot}.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                paths.append(path)
            merged = local.merge_slot_checkpoints(paths, root / "merged.json")
        self.assertEqual(merged["selected_slots"], list(local.LOCAL_MODELS))
        self.assertEqual(merged["external_inference_api_requests"], 0)
        self.assertEqual(merged["estimated_model_api_spend_usd"], 0.0)
        self.assertEqual(merged["run_status"], "merged_partial_slot_checkpoints")


if __name__ == "__main__":
    unittest.main()
