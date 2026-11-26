from __future__ import annotations

import io
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

    def test_rate_card_matches_runner_policy(self) -> None:
        rates, snapshot = pilot.load_rate_card(V9_DIR / "model_rates_v9.json")
        self.assertEqual(snapshot, "2026-11-26")
        self.assertEqual(set(rates), {s["slot"] for s in api.CANDIDATES})
        self.assertEqual(rates["mistral_24b"]["input_usd_per_1m_tokens"], 0.05)


if __name__ == "__main__":
    unittest.main()
