import json
import re
import unittest
from pathlib import Path

from bench.run import create_report_template
from tools.validate_intake import SELECTION_BUCKETS, TASK_TYPES, detect_pii, validate_schema


def key_shape(value):
    if isinstance(value, dict):
        return {key: key_shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [key_shape(value[0])] if value else []
    return None


class IntakeValidatorTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "id": "case-001",
            "task_type": "information_extraction",
            "selection_bucket": "high_volume",
            "prompt": "Extract the equipment status from the supplied context.",
            "expected_output": "Status: operating",
        }

    def test_accepts_complete_record(self):
        self.assertEqual(validate_schema([self.case]), [])

    def test_rejects_missing_or_empty_expected_output(self):
        missing = {key: value for key, value in self.case.items() if key != "expected_output"}
        self.assertTrue(any("missing required field `expected_output`" in issue
                            for issue in validate_schema([missing])))
        empty = {**self.case, "expected_output": "  "}
        self.assertTrue(any("expected_output` must not be blank" in issue
                            for issue in validate_schema([empty])))

    def test_rejects_invalid_task_type_bucket_and_extra_fields(self):
        invalid = {**self.case, "task_type": "chemical_plant", "selection_bucket": "synthetic", "extra": "x"}
        issues = validate_schema([invalid])
        self.assertTrue(any("invalid `task_type`" in issue for issue in issues))
        self.assertTrue(any("invalid `selection_bucket`" in issue for issue in issues))
        self.assertTrue(any("unsupported field" in issue for issue in issues))

    def test_rejects_non_string_enums_without_crashing(self):
        invalid = {**self.case, "task_type": [], "selection_bucket": {}}
        issues = validate_schema([invalid])
        self.assertTrue(any("invalid `task_type`" in issue for issue in issues))
        self.assertTrue(any("invalid `selection_bucket`" in issue for issue in issues))

    def test_intake_schema_rubric_and_validator_share_enums(self):
        root = Path(__file__).resolve().parents[1]
        intake = (root / "INTAKE.md").read_text()
        match = re.search(
            r"## Anexo técnico: schema de `domain_set.jsonl`.*?```json\n(.*?)\n```",
            intake,
            re.S,
        )
        self.assertIsNotNone(match)
        schema = json.loads(match.group(1))
        rubric = json.loads((root / "eval/rubric_template.json").read_text())
        self.assertEqual(set(schema["properties"]["task_type"]["enum"]), TASK_TYPES)
        self.assertEqual(set(schema["properties"]["selection_bucket"]["enum"]), SELECTION_BUCKETS)
        self.assertEqual(set(rubric["task_types"]), TASK_TYPES)

    def test_detects_email_phone_iban_and_labeled_person_name(self):
        private_case = {
            **self.case,
            "context": "Contact: Jane Doe, jane@example.com, +1 415 555 0134, IBAN GB82 WEST 1234 5698 7654 32",
        }
        findings = detect_pii([private_case])
        joined = " ".join(findings)
        for kind in ("email", "phone", "iban", "proper_name_heuristic"):
            self.assertIn(kind, joined)
        self.assertNotIn("jane@example.com", joined)
        self.assertNotIn("Jane Doe", joined)

    def test_iso_date_is_not_flagged_as_phone(self):
        self.assertEqual(detect_pii([{**self.case, "context": "Inspection date: 2026-11-09"}]), [])

    def test_detects_pii_in_expected_output(self):
        findings = detect_pii([{**self.case, "expected_output": "Call +1 415 555 0134"}])
        self.assertTrue(any("possible PII (phone)" in finding for finding in findings))

    def test_examples_domain_set_is_valid(self):
        path = Path(__file__).resolve().parents[1] / "examples/domain_set.example.jsonl"
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        self.assertEqual(len(records), 3)
        self.assertEqual(validate_schema(records), [])
        self.assertEqual(detect_pii(records), [])

    def test_examples_pii_invalid_is_rejected(self):
        path = Path(__file__).resolve().parents[1] / "examples/domain_set.pii_invalid.jsonl"
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        self.assertEqual(validate_schema(records), [])
        findings = detect_pii(records)
        self.assertTrue(any("line 1" in finding and "(email)" in finding for finding in findings))
        self.assertTrue(any("line 2" in finding and "(phone)" in finding for finding in findings))

    def test_examples_results_schema(self):
        path = Path(__file__).resolve().parents[1] / "examples/results.example.json"
        example = json.loads(path.read_text())
        self.assertTrue(example["_example"])
        self.assertEqual(example["_note"], "Solo esquema sintético; los resultados reales son privados.")
        public_report_fields = {key: value for key, value in example.items() if not key.startswith("_")}
        self.assertEqual(key_shape(public_report_fields), key_shape(create_report_template()))
        for config in example["results"].values():
            for measurement in config["load_tests"]:
                self.assertIsNone(measurement["cost_usd_per_million_tokens"])
                self.assertIsNone(measurement["ttft_p95_ms"])
            self.assertEqual(config["quality"]["gsm8k"]["accuracy_exact_match"], "pending")
            self.assertEqual(config["quality"]["domain"]["accuracy_judge_mean"], "pending")


if __name__ == "__main__":
    unittest.main()