from __future__ import annotations

import io
import contextlib
import os
import tempfile
import json
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

V9_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V9_DIR))

import api_ping_check_v9 as api
import pilot_b_v9 as pilot
import pilot_a_v9 as pilot_a
import confirmatory_v9 as confirmatory


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, _: int) -> bytes:
        return self.body


def response_body() -> bytes:
    return json.dumps({
        "choices": [{"message": {"content": "1"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
    }).encode("utf-8")


class RetryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        api.reset_request_pacing_state()
        self.spec = api.CANDIDATES[0]
        self.clock = FakeClock()
        self.calls = 0

    def run_statuses(self, statuses: list[int]):
        def opener(request, timeout):
            self.calls += 1
            status = statuses.pop(0)
            if status in {429, 503}:
                raise HTTPError(request.full_url, status, "transient", {}, io.BytesIO(b""))
            return FakeResponse(status, response_body())

        attempts = []
        retries = []
        authorized = []

        def authorize(event):
            authorized.append(event["next_attempt_number"])
            return {"attempt": event["next_attempt_number"]}

        result = api.execute_request(
            self.spec, "unit-test-key", [{"role": "user", "content": "test"}], 16,
            before_attempt=attempts.append, authorize_retry=authorize, on_retry=retries.append,
            sleep_fn=self.clock.sleep, monotonic_fn=self.clock.monotonic, urlopen_fn=opener,
        )
        return result, attempts, retries, authorized

    def test_retries_429_and_503_with_logged_attempts_and_reservations(self) -> None:
        result, attempts, retries, authorized = self.run_statuses([429, 503, 200])
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["http_attempt_count"], 3)
        self.assertEqual([x["http_status"] for x in attempts], [429, 503, 200])
        self.assertEqual([x["backoff_seconds"] for x in retries], [2.0, 4.0])
        self.assertEqual(authorized, [2, 3])
        self.assertEqual([x["next_attempt_number"] for x in retries], [2, 3])
        self.assertNotIn("unit-test-key", repr(result))
        self.assertNotIn("Authorization", repr(attempts + retries))

    def test_retry_exhaustion_is_bounded_at_three_retries(self) -> None:
        result, attempts, retries, _ = self.run_statuses([429, 503, 429, 503])
        self.assertEqual(result["http_attempt_count"], 4)
        self.assertEqual(result["retry_count"], 3)
        self.assertEqual(result["error_category"], "transient_http_retries_exhausted")
        self.assertEqual([x["backoff_seconds"] for x in retries], [2.0, 4.0, 8.0])
        self.assertEqual(len(attempts), 4)

    def test_spacing_is_applied_between_logical_calls(self) -> None:
        def opener(request, timeout):
            self.calls += 1
            self.clock.now += 0.01
            return FakeResponse(200, response_body())

        first = api.execute_request(
            self.spec, "unit-test-key", [{"role": "user", "content": "one"}], 16,
            sleep_fn=self.clock.sleep, monotonic_fn=self.clock.monotonic, urlopen_fn=opener,
        )
        second = api.execute_request(
            self.spec, "unit-test-key", [{"role": "user", "content": "two"}], 16,
            sleep_fn=self.clock.sleep, monotonic_fn=self.clock.monotonic, urlopen_fn=opener,
        )
        self.assertEqual(first["http_status"], 200)
        self.assertEqual(second["request_attempts"][0]["inter_call_wait_seconds"], 0.35)
        self.assertAlmostEqual(self.clock.sleeps[-1], 0.35)


class RunnerPolicyTests(unittest.TestCase):
    def test_shared_scrubber_routes_never_self_scrub(self) -> None:
        expected = {
            "qwen_72b": ("gemma_27b", "mistral_24b"),
            "gemma_27b": ("mistral_24b", None),
            "llama_70b": ("gemma_27b", "mistral_24b"),
            "mistral_24b": ("gemma_27b", None),
        }
        for tested_slot, route in expected.items():
            with self.subTest(tested_slot=tested_slot):
                self.assertEqual(pilot.style_scrubber_route(tested_slot), route)
                self.assertNotIn(tested_slot, route)

    def test_shared_scrubber_is_billed_to_actual_utility_model(self) -> None:
        routes = []
        rewritten = " ".join(["neutral"] * 48)

        def fake_stage(spec, api_key, item_id, stage, messages, timeout, rate,
                       guard, report, checkpoint, **kwargs):
            routes.append((spec["slot"], rate["input_usd_per_1m_tokens"], kwargs))
            return {
                "slot": kwargs["tested_slot"],
                "billing_slot": spec["slot"],
                "available": True,
                "availability_blockers": [],
                "style_scrub_word_count": 48,
                "estimated_usd": 0.00001,
            }, rewritten

        rates = {
            "gemma_27b": {"input_usd_per_1m_tokens": 0.65, "output_usd_per_1m_tokens": 0.65},
            "mistral_24b": {"input_usd_per_1m_tokens": 0.05, "output_usd_per_1m_tokens": 0.08},
        }
        keys = {"OPENROUTER_API_KEY": "unit-test-key"}
        for tested in ("qwen_72b", "gemma_27b", "llama_70b", "mistral_24b"):
            tested_spec = next(s for s in api.CANDIDATES if s["slot"] == tested)
            with patch.object(pilot, "run_stage", side_effect=fake_stage):
                row, _ = pilot.run_style_scrub_with_repairs(
                    tested_spec, keys, "TR_TEST", "prompt", "answer", 1, rates,
                    pilot.SpendGuard(0.25), {"calls": []}, lambda: None,
                )
            billed_slot = next(s for s in api.CANDIDATES if s["slot"] == row["billing_slot"])
            self.assertNotEqual(row["slot"], row["billing_slot"])
            self.assertEqual(routes[-1][0], pilot.style_scrubber_route(tested)[0])
            self.assertEqual(routes[-1][1], rates[billed_slot["slot"]]["input_usd_per_1m_tokens"])

    def test_word_count_exhaustion_falls_back_only_to_independent_slot(self) -> None:
        slots = []
        calls = []

        def fake_stage(spec, api_key, item_id, stage, messages, timeout, rate,
                       guard, report, checkpoint, **kwargs):
            slots.append(spec["slot"])
            calls.append(kwargs)
            if spec["slot"] == "gemma_27b":
                return {
                    "slot": kwargs["tested_slot"],
                    "billing_slot": spec["slot"],
                    "available": False,
                    "availability_blockers": ["style_scrub_word_count_out_of_range"],
                    "style_scrub_word_count": 39,
                }, " ".join(["short"] * 39)
            return {
                "slot": kwargs["tested_slot"],
                "billing_slot": spec["slot"],
                "available": True,
                "availability_blockers": [],
                "style_scrub_word_count": 48,
            }, " ".join(["neutral"] * 48)

        rates = {
            "gemma_27b": {"input_usd_per_1m_tokens": 0.65, "output_usd_per_1m_tokens": 0.65},
            "mistral_24b": {"input_usd_per_1m_tokens": 0.05, "output_usd_per_1m_tokens": 0.08},
        }
        qwen = next(s for s in api.CANDIDATES if s["slot"] == "qwen_72b")
        with patch.object(pilot, "run_stage", side_effect=fake_stage):
            row, _ = pilot.run_style_scrub_with_repairs(
                qwen, {"OPENROUTER_API_KEY": "unit-test-key"}, "TR_TEST", "prompt",
                "answer", 1, rates, pilot.SpendGuard(0.25), {"calls": []}, lambda: None,
            )
        self.assertEqual(slots, ["gemma_27b"] * 5 + ["mistral_24b"])
        self.assertTrue(row["available"])
        self.assertEqual(row["billing_slot"], "mistral_24b")
        self.assertEqual(calls[-1]["scrubber_route_role"], "fallback")

    def test_scaling_bounds_and_model_locks(self) -> None:
        self.assertEqual(pilot.call_bounds(5), {
            "baseline_logical_calls": 100,
            "maximum_logical_calls_with_shared_scrub_fallback": 230,
            "maximum_http_attempts_with_transient_retries": 920,
        })
        self.assertEqual(pilot.call_bounds(50)["maximum_logical_calls_with_shared_scrub_fallback"], 2300)
        self.assertEqual(pilot.call_bounds(260)["maximum_http_attempts_with_transient_retries"], 47840)
        self.assertEqual(pilot.run_classification_for_num_items(260),
                         ("prospective_confirmatory_study", True))
        self.assertEqual(pilot.MAX_TOKENS["phase1_digit_evaluation"], 16)
        self.assertEqual(pilot.MAX_TOKENS["domain2_digit_evaluation"], 16)

    def test_tested_and_billing_model_token_totals_are_separate(self) -> None:
        rates, _ = pilot.load_rate_card(V9_DIR / "model_rates_v9.json")
        calls = [
            {
                "slot": "qwen_72b", "billing_slot": "qwen_72b",
                "call_role": "tested_model", "item_id": "TR_TEST",
                "stage": "phase0_harvest", "available": True,
                "input_tokens": 11, "output_tokens": 2,
                "estimated_usd": 0.000010, "budget_reservation_usd": 0.000020,
                "http_attempts_started": 1, "latency_ms": 10,
            },
            {
                "slot": "qwen_72b", "billing_slot": "gemma_27b",
                "call_role": "shared_utility_scrubber", "item_id": "TR_TEST",
                "stage": "utility_style_scrub", "available": True,
                "input_tokens": 7, "output_tokens": 48,
                "estimated_usd": 0.000040, "budget_reservation_usd": 0.000050,
                "http_attempts_started": 1, "latency_ms": 20,
            },
        ]
        tested = next(x for x in pilot._aggregate(calls, ["TR_TEST"], False)
                      if x["slot"] == "qwen_72b")
        billed = {x["billing_slot"]: x for x in pilot._aggregate_billing_models(calls, rates)}
        self.assertEqual(tested["input_tokens"], 11)
        self.assertEqual(tested["output_tokens"], 2)
        self.assertEqual(tested["shared_scrub_input_tokens"], 7)
        self.assertEqual(tested["shared_scrub_output_tokens"], 48)
        self.assertEqual(billed["qwen_72b"]["input_tokens"], 11)
        self.assertEqual(billed["gemma_27b"]["input_tokens"], 7)
        self.assertEqual(billed["gemma_27b"]["estimated_usd"], 0.00004)

    def test_pilot_a_locks_fifty_items_and_half_dollar_cap(self) -> None:
        forwarded = []
        with patch.object(pilot_a.pilot_b_v9, "main", side_effect=lambda argv: forwarded.extend(argv) or 0):
            self.assertEqual(pilot_a.main(["--execute"]), 0)
        self.assertIn("--num-items", forwarded)
        self.assertEqual(forwarded[forwarded.index("--num-items") + 1], "50")
        self.assertEqual(forwarded[forwarded.index("--budget-usd") + 1], "0.5")
        self.assertIn("--execute", forwarded)
        self.assertEqual(pilot.BUDGET_CAP_USD_BY_NUM_ITEMS, {5: 0.25, 50: 0.50, 260: 1.25})
        self.assertEqual(pilot.run_classification_for_num_items(50),
                         ("prospective_pilot_a_not_confirmatory_study", False))

    def test_pilot_a_rejects_budget_above_half_dollar(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                pilot_a.main(["--budget-usd", "0.51"])

    def test_style_scrub_range_exhaustion_skips_only_that_item(self) -> None:
        items = [
            {"item_id": f"TR_{index:02d}", "category": "test", "prompt_text": f"prompt {index}"}
            for index in (1, 2, 3)
        ]
        rates = {
            spec["slot"]: {"input_usd_per_1m_tokens": 0.1, "output_usd_per_1m_tokens": 0.1}
            for spec in api.CANDIDATES
        }
        attempted: list[tuple[str, str, str]] = []

        def fake_stage(spec, api_key, item_id, stage, messages, timeout, rate,
                       guard, report, checkpoint):
            attempted.append((spec["slot"], item_id, stage))
            row = {
                "slot": spec["slot"], "tested_slot": spec["slot"],
                "billing_slot": spec["slot"], "call_role": "tested_model",
                "provider": spec["provider"], "model_id": spec["model_id"],
                "item_id": item_id, "stage": stage, "available": True,
                "availability_blockers": [], "http_status": 200,
                "http_attempts_started": 1, "http_attempts": [{"http_status": 200}],
                "retry_count": 0, "input_tokens": 1, "output_tokens": 1,
                "estimated_usd": 0.000001, "budget_reservation_usd": 0.000001,
                "latency_ms": 1,
            }
            report["calls"].append(row)
            checkpoint()
            return row, f"{stage} answer"

        def fake_style(tested_spec, keys, item_id, prompt, perturbed, timeout,
                       all_rates, guard, report, checkpoint):
            attempted.append((tested_spec["slot"], item_id, "utility_style_scrub"))
            billing_slot, _ = pilot.style_scrubber_route(tested_spec["slot"])
            available = item_id != "TR_02"
            row = {
                "slot": tested_spec["slot"], "tested_slot": tested_spec["slot"],
                "billing_slot": billing_slot, "call_role": "shared_utility_scrubber",
                "provider": tested_spec["provider"], "model_id": tested_spec["model_id"],
                "item_id": item_id, "stage": "utility_style_scrub",
                "available": available,
                "availability_blockers": [] if available else ["style_scrub_word_count_out_of_range"],
                "http_status": 200, "http_attempts_started": 1,
                "http_attempts": [{"http_status": 200}], "retry_count": 0,
                "input_tokens": 1, "output_tokens": 1,
                "estimated_usd": 0.000001, "budget_reservation_usd": 0.000001,
                "latency_ms": 1, "style_scrub_word_count": 48 if available else 44,
            }
            report["calls"].append(row)
            checkpoint()
            return row, "neutral scrubbed answer" if available else "short rewrite"

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "isolated-run.json"
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "unit-test-placeholder"}):
                with patch.object(pilot, "load_items", return_value=(pilot.EXPECTED_ITEMS_POOL_SHA256, items)):
                    with patch.object(pilot, "load_rate_card", return_value=(rates, "2026-11-26")):
                        with patch.object(pilot, "run_stage", side_effect=fake_stage):
                            with patch.object(pilot, "run_style_scrub_with_repairs", side_effect=fake_style):
                                self.assertEqual(pilot.main(["--execute", "--output", str(output)]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(len(report["item_level_summary"]), 12)
        for slot in (spec["slot"] for spec in api.CANDIDATES):
            rows = [x for x in report["item_level_summary"] if x["slot"] == slot]
            self.assertEqual([x["item_id"] for x in rows], ["TR_01", "TR_02", "TR_03"])
            self.assertEqual([x["status"] for x in rows], ["complete", "skipped_due_to_style_scrub_range", "complete"])
            self.assertFalse(rows[1]["available"])
            self.assertEqual(rows[1]["skip_reason"], "skipped_due_to_style_scrub_range")
            self.assertEqual(rows[1]["final_style_word_count"], 44)
            self.assertEqual(rows[1]["completed_stages"], ["phase0_harvest", "utility_perturb"])
            self.assertIn((slot, "TR_03", "phase0_harvest"), attempted)
            self.assertNotIn((slot, "TR_02", "phase1_digit_evaluation"), attempted)
        self.assertFalse(report["stopped_early"])

    def test_confirmatory_entrypoint_locks_260_and_one_dollar_twenty_five_cap(self) -> None:
        forwarded: list[str] = []
        with patch.object(confirmatory.pilot_b_v9, "main", side_effect=lambda argv: forwarded.extend(argv) or 0):
            self.assertEqual(confirmatory.main(["--execute", "--resume-from", "prior.json"]), 0)
        self.assertEqual(forwarded[forwarded.index("--resume-from") + 1], "prior.json")
        self.assertEqual(forwarded[forwarded.index("--num-items") + 1], "260")
        self.assertEqual(forwarded[forwarded.index("--budget-usd") + 1], "1.25")
        self.assertIn("--execute", forwarded)
        self.assertEqual(pilot.BUDGET_CAP_USD_BY_NUM_ITEMS[260], 1.25)
        self.assertEqual(pilot.run_classification_for_num_items(260),
                         ("prospective_confirmatory_study", True))

    def test_confirmatory_entrypoint_rejects_budget_above_cap(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                confirmatory.main(["--budget-usd", "1.26"])

    def test_rate_card_matches_runner_policy(self) -> None:
        rates, snapshot = pilot.load_rate_card(V9_DIR / "model_rates_v9.json")
        self.assertEqual(snapshot, "2026-11-26")
        self.assertEqual(set(rates), {s["slot"] for s in api.CANDIDATES})
        self.assertEqual(rates["mistral_24b"]["input_usd_per_1m_tokens"], 0.05)


class FailFastAndResumeTests(unittest.TestCase):
    def test_engineering_ping_stops_after_first_http_402(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "ping.json"
            requested = []

            def fake_request(spec, key, out, report, secrets, timeout):
                requested.append(spec["slot"])
                row = {"slot": spec["slot"], "provider": spec["provider"],
                       "model_id": spec["model_id"], "http_status": 402,
                       "available": False, "retry_count": 0,
                       "availability_blockers": ["http_status_not_200"]}
                report["results"].append(row)
                report["api_request_ledger"].append({"slot": spec["slot"], "http_status": 402})
                return row

            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "unit-test-placeholder"}):
                with patch.object(api, "_tracked_request", side_effect=fake_request):
                    self.assertEqual(api.main(["--execute", "--output", str(output)]), 2)
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(requested, [api.CANDIDATES[0]["slot"]])
        self.assertEqual(report["halt_reason"], "http_402_insufficient_credits")
        self.assertEqual(report["not_attempted_slots"], [x["slot"] for x in api.CANDIDATES[1:]])
        self.assertEqual(len(report["results"]), 1)

    def test_pipeline_402_stops_before_other_slots(self) -> None:
        items = [{"item_id": "TR_01", "category": "test", "prompt_text": "prompt"}]
        rates = {slot: {"input_usd_per_1m_tokens": 0.1, "output_usd_per_1m_tokens": 0.1}
                 for slot in (x["slot"] for x in api.CANDIDATES)}
        seen = []

        def fake_stage(spec, api_key, item_id, stage, messages, timeout, rate,
                       guard, report, checkpoint, **kwargs):
            seen.append((spec["slot"], item_id, stage))
            row = {"call_id": f"call-{len(report['calls']) + 1}", "slot": spec["slot"],
                   "billing_slot": spec["slot"], "call_role": "tested_model",
                   "item_id": item_id, "stage": stage, "available": False,
                   "availability_blockers": ["http_status_not_200"],
                   "http_status": 402, "error_category": "insufficient_credits",
                   "http_attempts_started": 1, "http_attempts": [{"http_status": 402}],
                   "retry_count": 0, "estimated_usd": 0.0,
                   "budget_reservation_usd": 0.000001, "latency_ms": 1}
            guard.reserved_usd += 0.000001
            report["calls"].append(row)
            return row, ""

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run.json"
            env = {name: "unit-test-placeholder" for name in set(api.ENV_BY_PROVIDER.values())}
            with patch.dict(os.environ, env):
                with patch.object(pilot, "load_items", return_value=(pilot.EXPECTED_ITEMS_POOL_SHA256, items)):
                    with patch.object(pilot, "load_rate_card", return_value=(rates, "test")):
                        with patch.object(pilot, "run_stage", side_effect=fake_stage):
                            self.assertEqual(pilot.main(["--execute", "--output", str(output)]), 2)
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], api.CANDIDATES[0]["slot"])
        self.assertEqual(report["halt_reason"], "http_402_insufficient_credits")
        self.assertTrue(report["stopped_early"])
        self.assertEqual(report["http_calls_started"], 1)

    def test_resume_verifies_and_merges_completed_pairs_without_recalling_them(self) -> None:
        items = [{"item_id": f"TR_{i:02d}", "category": "test", "prompt_text": f"prompt {i}"}
                 for i in range(1, 261)]
        first_id = items[0]["item_id"]
        complete_calls = [{"call_id": f"old-{i}", "slot": "qwen_72b", "item_id": first_id,
                           "stage": stage, "available": True, "http_status": 200,
                           "http_attempts_started": 1, "http_attempts": [{"http_status": 200}],
                           "estimated_usd": 0.000001, "budget_reservation_usd": 0.000001}
                          for i, stage in enumerate(pilot.MAX_TOKENS, 1)]
        complete_row = {"slot": "qwen_72b", "model_id": api.CANDIDATES[0]["model_id"],
                        "item_id": first_id, "available": True, "status": "complete",
                        "completed_stages": list(pilot.MAX_TOKENS)}
        prior = {"run_classification": "prospective_confirmatory_study",
                 "num_items_requested": 260,
                 "item_pool_sha256": pilot.EXPECTED_ITEMS_POOL_SHA256,
                 "selected_first_items": [{"item_id": x["item_id"]} for x in items],
                 "budget_cap_usd": 1.25, "budget_reserved_usd": 0.000005,
                 "halt_reason": "http_402_insufficient_credits",
                 "calls": complete_calls, "item_level_summary": [complete_row]}
        rates, _ = pilot.load_rate_card(V9_DIR / "model_rates_v9.json")
        seen = []

        def fake_stage(spec, api_key, item_id, stage, messages, timeout, rate,
                       guard, report, checkpoint, **kwargs):
            seen.append((spec["slot"], item_id, stage))
            guard.reserved_usd += 0.000003
            row = {"call_id": f"pilot-{len(report['calls']) + 1:05d}", "slot": spec["slot"],
                   "billing_slot": spec["slot"], "call_role": "tested_model",
                   "item_id": item_id, "stage": stage, "available": False,
                   "availability_blockers": ["http_status_not_200"],
                   "http_status": 402, "error_category": "insufficient_credits",
                   "http_attempts_started": 1, "http_attempts": [{"http_status": 402}],
                   "retry_count": 0, "estimated_usd": 0.0,
                   "budget_reservation_usd": 0.000003, "latency_ms": 1}
            report["calls"].append(row)
            return row, ""

        with tempfile.TemporaryDirectory() as temp_dir:
            prior_path = Path(temp_dir) / "prior.json"
            output = Path(temp_dir) / "resumed.json"
            prior_path.write_text(json.dumps(prior), encoding="utf-8")
            bad_prior = {**prior, "item_pool_sha256": "0" * 64}
            bad_path = Path(temp_dir) / "wrong-pool.json"
            bad_path.write_text(json.dumps(bad_prior), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "item_pool_sha256"):
                pilot.load_resume_receipt(bad_path, pilot.EXPECTED_ITEMS_POOL_SHA256, items)
            env = {name: "unit-test-placeholder" for name in set(api.ENV_BY_PROVIDER.values())}
            with patch.dict(os.environ, env):
                with patch.object(pilot, "load_items", return_value=(pilot.EXPECTED_ITEMS_POOL_SHA256, items)):
                    with patch.object(pilot, "load_rate_card", return_value=(rates, "test")):
                        with patch.object(pilot, "run_stage", side_effect=fake_stage):
                            self.assertEqual(pilot.main([
                                "--execute", "--num-items", "260", "--budget-usd", "1.25",
                                "--resume-from", str(prior_path), "--output", str(output),
                            ]), 2)
            merged = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(seen, [("qwen_72b", "TR_02", "phase0_harvest")])
        self.assertEqual(len(merged["calls"]), len(complete_calls) + 1)
        self.assertEqual(merged["calls"][:len(complete_calls)], complete_calls)
        self.assertEqual(merged["resume_metadata"]["completed_pairs_reused"], 1)
        self.assertEqual(merged["budget_cap_usd"], 1.25)
        self.assertEqual(merged["budget_reserved_usd"], 0.000008)
        self.assertEqual(merged["halt_reason"], "http_402_insufficient_credits")
        rows = {(x["slot"], x["item_id"]): x for x in merged["item_level_summary"]}
        self.assertEqual(rows[("qwen_72b", "TR_01")]["status"], "complete")
        self.assertEqual(rows[("qwen_72b", "TR_02")]["status"], "failed_closed")



if __name__ == "__main__":
    unittest.main()
