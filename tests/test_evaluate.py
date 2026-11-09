import hashlib
import unittest
from unittest.mock import AsyncMock, patch

from bench.evaluate import extract_gsm8k_answer, parse_judge_response, score_gsm8k, score_judge
from bench.run import add_quality_deltas, run_domain_quality, run_gsm8k_quality


class JudgeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": '{"score":4,"reason":"Correcta"}'}}]}


class JudgeClient:
    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, *_args, **_kwargs):
        return JudgeResponse()


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    def test_extracts_only_gsm8k_final_marker(self):
        self.assertEqual(extract_gsm8k_answer("Work: 7 x 6.\n#### 42"), "42")
        self.assertIsNone(extract_gsm8k_answer("The answer is 42."))

    def test_normalizes_commas_and_decimal_zeros(self):
        self.assertEqual(extract_gsm8k_answer("#### 1,200.0"), "1200")

    def test_exact_match_scoring(self):
        report = score_gsm8k(
            [{"expected": "42"}, {"expected": "9"}],
            ["#### 42", "#### 8"],
        )
        self.assertEqual(report, {"accuracy_exact_match": 0.5, "correct": 1, "n_samples": 2})

    def test_missing_answer_marker_is_not_a_match(self):
        report = score_gsm8k([{"expected": ""}], ["No final marker"])
        self.assertEqual(report["correct"], 0)

    def test_judge_requires_valid_score_and_reason(self):
        self.assertEqual(parse_judge_response('{"score":4,"reason":"Correct"}'), {
            "score": 4,
            "reason": "Correct",
        })
        with self.assertRaises(ValueError):
            parse_judge_response('{"score":6,"reason":"invalid"}')

    def test_judge_mean_ignores_invalid_values(self):
        self.assertEqual(score_judge([4, 3, None]), {"accuracy_judge_mean": 3.5, "n_samples": 2})

    async def test_gsm8k_runner_emits_auditable_scores(self):
        examples = [{"id": "a", "prompt": "Q1", "expected": "42"}]
        generated = {"text": "Reasoning\n#### 42"}
        with patch("bench.run.request_completion", new=AsyncMock(return_value=generated)):
            result = await run_gsm8k_quality("http://model", "model", examples, 64, 1)
        self.assertEqual(result["accuracy_exact_match"], 1.0)
        self.assertEqual(result["n_samples"], 1)
        self.assertTrue(result["samples"][0]["correct"])

    async def test_domain_runner_uses_judge_prompt_and_records_scores(self):
        examples = [{
            "id": "case-1",
            "task_type": "information_extraction",
            "selection_bucket": "high_volume",
            "prompt": "What should be checked?",
            "expected_output": "Check the pressure gauge.",
        }]
        generated = {"text": "Check the pressure gauge."}
        prompt = "Judge with the documented rubric."
        rubric = {
            "score_scale": {"1": "wrong", "5": "right"},
            "global_rules": ["Use only the reference."],
            "task_types": {"information_extraction": {"criteria": ["Extract accurately."]}},
        }
        with patch("bench.run.request_completion", new=AsyncMock(return_value=generated)), \
             patch("bench.run.httpx.AsyncClient", new=JudgeClient):
            result = await run_domain_quality(
                "http://model", "model", examples, 64, 1,
                "http://judge/v1", "judge-model", "", prompt, rubric,
            )
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["accuracy_judge_mean"], 4.0)
        self.assertEqual(result["samples"][0]["id"], "case-1")
        self.assertEqual(result["by_task_type"]["information_extraction"]["n_samples"], 1)
        self.assertEqual(result["judge_prompt_sha256"], hashlib.sha256(prompt.encode()).hexdigest())

    def test_quality_deltas_are_reported_in_their_native_units(self):
        results = {
            "fp16_naive": {"quality": {
                "gsm8k": {"accuracy_exact_match": 0.8},
                "domain": {"accuracy_judge_mean": 4.0},
            }},
            "fp8_vllm": {"quality": {
                "gsm8k": {"accuracy_exact_match": 0.78},
                "domain": {"accuracy_judge_mean": 3.75},
            }},
        }
        add_quality_deltas(results)
        self.assertEqual(results["fp8_vllm"]["quality"]["gsm8k"]["delta_vs_baseline_pp"], -2.0)
        self.assertEqual(results["fp8_vllm"]["quality"]["domain"]["delta_vs_baseline"], -0.25)


if __name__ == "__main__":
    unittest.main()