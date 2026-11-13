"""S03 / T05–T06: saved-response validation tests before implementation.

Proposed API in access_intake.validation:
  validate_shape(extraction, *, schema_path) -> None, raising
  ExtractionValidationError for schema violations;
  validate_response(document, response, *, response_source, schema_path) -> dict.

Success returns extraction/error=None and document/hash/source provenance, with
routing deferred to S04. Failure returns the office-policy error envelope. A
normalized response requires status=completed; nonempty refusal and a supplied
noncompleted message_status must override even a schema-valid output_text.
The real provider adapter will normalize its HTTP responses in S08.
"""

import json

from access_intake.ingest import load_document
from support import MOCKS, ROOT, OfflineFixtureTestCase, read_json


class ResponseValidationS03(OfflineFixtureTestCase):
    def setUp(self):
        super().setUp()
        self.expected = read_json(ROOT / "tests" / "expected" / "validation-cases.json")
        self.source_cases = read_json(ROOT / "tests" / "expected" / "source-facts.json")[
            "cases"
        ]
        self.document = load_document(ROOT / self.oracle["input"])
        self.schema_path = ROOT / "snapshot.schema.json"

        from access_intake.validation import (
            ExtractionValidationError,
            validate_response,
            validate_shape,
        )

        self.shape_error = ExtractionValidationError
        self.validate_shape = validate_shape
        self.validate_response = validate_response

    def response_result(self, response, document=None):
        return self.validate_response(
            document or self.document,
            response,
            response_source="mock",
            schema_path=self.schema_path,
        )

    def assert_error(self, response, cause=None):
        result = self.response_result(response)
        self.assertTrue(set(self.expected["required_error_properties"]) <= set(result))
        for field, value in self.expected["error_route"].items():
            self.assertEqual(result[field], value)
        self.assertEqual(result["document_id"], self.document.document_id)
        self.assertEqual(result["source_sha256"], self.document.source_sha256)
        self.assertEqual(result["response_source"], "mock")
        self.assertIsNone(result["extraction"])
        self.assertIsInstance(result["error"], str)
        self.assertTrue(result["error"].strip())
        if cause is not None:
            self.assertIn(cause, result["error"].lower())
        return result

    def assert_source_facts(self, response, oracle_name):
        oracle = self.source_cases[oracle_name]
        document = load_document(ROOT / oracle["input"])
        result = self.response_result(response, document)
        self.assertIsNone(result["error"])
        self.assertEqual(result["document_id"], document.document_id)
        self.assertEqual(result["source_sha256"], document.source_sha256)
        self.assertEqual(result["response_source"], "mock")
        self.assertEqual(result["extraction"], oracle["extraction"])
        return result

    def test_t05_accepts_complete_saved_response_against_independent_O01(self):
        self.assert_source_facts(self.saved_response, "O01")

    def test_t05_rejects_each_schema_violation_with_the_policy_error_envelope(self):
        cases = read_json(MOCKS / "schema-invalid.json")["cases"]
        self.assertEqual(
            [case["name"] for case in cases], self.expected["invalid_schema_cases"]
        )
        for case in cases:
            with self.subTest(case=case["name"]):
                self.assert_error(case["response"], "schema")

    def test_t05_shape_validator_rejects_each_invalid_schema_boundary(self):
        for case in read_json(MOCKS / "schema-invalid.json")["cases"]:
            with self.subTest(case=case["name"]):
                extraction = json.loads(case["response"]["output_text"])
                with self.assertRaises(self.shape_error):
                    self.validate_shape(extraction, schema_path=self.schema_path)

    def test_t05_shape_validator_accepts_documented_nullable_types_and_enums(self):
        # These are schema probes, not source-entailment or routing assertions.
        cases = read_json(MOCKS / "schema-valid.json")["cases"]
        self.assertEqual(
            [case["name"] for case in cases], self.expected["valid_schema_cases"]
        )
        for case in cases:
            with self.subTest(case=case["name"]):
                extraction = json.loads(case["response"]["output_text"])
                self.assertIsNone(
                    self.validate_shape(extraction, schema_path=self.schema_path)
                )

    def test_t05_malformed_json_is_an_explicit_error(self):
        response = read_json(MOCKS / "invalid-json-response.json")
        self.assertEqual(
            response["output_text"], (MOCKS / "invalid-json.txt").read_text(encoding="utf-8")
        )
        self.assert_error(response, "json")

    def test_t05_invalid_envelopes_and_missing_or_nonstring_output_are_errors(self):
        for case in read_json(MOCKS / "response-envelope-invalid.json")["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_error(case["response"])

    def test_t06_decoded_newline_evidence_is_preserved_exactly(self):
        response = read_json(MOCKS / "source-oracles" / "IT-002.json")
        result = self.assert_source_facts(response, "O02")
        source = load_document(ROOT / self.source_cases["O02"]["input"]).message
        quotes = result["extraction"]["supporting_quotes"]
        self.assertTrue(any("\n" in quote for quote in quotes))
        for quote in quotes:
            self.assertIn(quote, source)

    def test_t06_quotes_must_be_exact_substrings_of_message_not_metadata(self):
        for case in read_json(MOCKS / "evidence-invalid.json")["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_error(case["response"], "quote")

    def test_t06_non_YYYY_MM_DD_date_strings_are_rejected(self):
        # Impossible calendar dates remain an open policy question, not a test rule.
        for case in read_json(MOCKS / "date-invalid.json")["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_error(case["response"], "date")

    def test_t06_missing_manager_remains_null_with_its_source_grounded_issue(self):
        result = self.assert_source_facts(
            read_json(MOCKS / "source-oracles" / "IT-009.json"), "O09"
        )
        self.assertIsNone(result["extraction"]["manager"])
        self.assertTrue(result["extraction"]["issues"])

    def test_t06_refusal_is_error_even_when_output_contains_valid_JSON(self):
        self.assert_error(read_json(MOCKS / "refusal.json"), "refus")

    def test_t06_cut_off_interrupted_response_is_not_accepted(self):
        self.assert_error(read_json(MOCKS / "interrupted.json"), "incomplete")

    def test_t06_parseable_valid_JSON_cannot_override_incomplete_status(self):
        self.assert_error(
            read_json(MOCKS / "completed-valid-body-incomplete-status.json"), "incomplete"
        )

    def test_t06_incomplete_output_message_is_error_despite_completed_envelope(self):
        self.assert_error(read_json(MOCKS / "message-incomplete.json"), "incomplete")

    def test_t06_missing_or_unsuccessful_completion_metadata_is_rejected(self):
        for case in read_json(MOCKS / "completion-invalid.json")["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_error(case["response"])

    def test_t06_failure_diagnostics_do_not_echo_untrusted_response_payload(self):
        response = read_json(MOCKS / "invalid-json-response.json")
        result = self.assert_error(response, "json")
        self.assertNotIn("SYNTHETIC_INVALID_JSON", result["error"])
        self.assertNotIn(response["output_text"], result["error"])
