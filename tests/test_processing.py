"""S04 / T07–T23: source-authored facts and ordered policy, tests first.

Proposed processing API: process_document(document, *, provider, configuration,
schema_path) composes ingestion's request, a provider response, S03 validation
and ordered routing, returning the current record envelope in memory.
load_extraction_prompt() supplies the tracked trusted extraction instructions.
These saved-mock checks establish orchestration/routing, not live-model accuracy.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from access_intake.ingest import load_document
from access_intake.providers.mock import MockProvider
from support import MOCKS, ROOT, OfflineFixtureTestCase, read_json


class ProcessingS04(OfflineFixtureTestCase):
    def setUp(self):
        super().setUp()
        self.sources = read_json(ROOT / "tests" / "expected" / "source-facts.json")[
            "cases"
        ]
        self.routing = read_json(ROOT / "tests" / "expected" / "routing-cases.json")
        self.configuration = {"provider": "mock", "model": "fixture-v1"}
        self.provider = MockProvider(MOCKS / "s04-manifest.json")
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.staging = Path(temporary.name)

        from access_intake.processing import load_extraction_prompt, process_document

        self.process_document = process_document
        self.load_prompt = load_extraction_prompt

    def process(self, document, provider=None):
        return self.process_document(
            document,
            provider=provider or self.provider,
            configuration=self.configuration,
            schema_path=ROOT / "snapshot.schema.json",
        )

    def assert_record(self, record, document, extraction, route):
        self.assertEqual(record["document_id"], document.document_id)
        self.assertEqual(record["source_sha256"], document.source_sha256)
        self.assertEqual(record["response_source"], "mock")
        self.assertIsNone(record["error"])
        for field, expected in route.items():
            self.assertEqual(record[field], expected)
        actual = record["extraction"]
        self.assertEqual(set(actual), set(extraction))
        for field in extraction:
            if field not in {"issues", "supporting_quotes"}:
                self.assertEqual(actual[field], extraction[field], field)
                if extraction[field] is None:
                    self.assertTrue(
                        any(
                            field.replace("_", " ") in issue.lower().replace("_", " ")
                            for issue in actual["issues"]
                        ),
                        f"No issue explains unresolved {field}",
                    )
        self.assertIsInstance(actual["issues"], list)
        self.assertTrue(all(isinstance(issue, str) for issue in actual["issues"]))
        self.assertTrue(actual["supporting_quotes"])
        for quote in actual["supporting_quotes"]:
            self.assertIsInstance(quote, str)
            self.assertIn(quote, document.message)
        self.assertNotEqual(record["status"], "approved")
        self.assertNotIn("approved", actual)
        return actual

    def check_source(self, oracle_name, provider=None):
        expected = self.sources[oracle_name]
        document = load_document(ROOT / expected["input"])
        record = self.process(document, provider)
        extraction = self.assert_record(
            record,
            document,
            expected["extraction"],
            self.routing["source_routing"][oracle_name],
        )
        for marker in self.routing["expected_issue_markers"].get(oracle_name, []):
            self.assertTrue(any(marker in issue.lower() for issue in extraction["issues"]))
        return record

    def stage_variant(self, expected):
        target = self.staging / expected["name"] / expected["document_id"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / expected["input"]).read_bytes())
        return load_document(target)

    def check_variant(self, expected):
        document = self.stage_variant(expected)
        record = self.process(document)
        extraction = self.assert_record(
            record, document, expected["extraction"], expected["route"]
        )
        for marker in expected["required_issue_markers"]:
            self.assertTrue(any(marker in issue.lower() for issue in extraction["issues"]))
        return record

    def test_t07_complete_request_awaits_system_owner_not_manager_approval(self):
        record = self.check_source("O01")
        self.assertEqual(record["extraction"]["issues"], [])
        self.assertEqual(record["extraction"]["manager"], self.oracle["extraction"]["manager"])
        self.assertEqual(len(self.provider.calls), 1)

    def test_t07_trusted_prompt_states_extraction_contract_without_source_injection(self):
        prompt = self.load_prompt()
        self.assertIsInstance(prompt, str)
        for field in self.routing["instruction_contract"]["required_fields"]:
            self.assertIn(field, prompt)
        for directive in self.routing["instruction_contract"]["required_directives"]:
            self.assertIn(directive.lower(), prompt.lower())
        attack = load_document(ROOT / self.sources["O06"]["input"]).message
        self.assertNotIn(attack, prompt)

    def test_t08_missing_end_date_clarifies_before_production_risk_review(self):
        self.check_source("O10")

    def test_t09_relative_dates_remain_null_instead_of_using_export_timestamp(self):
        self.check_source("O11")

    def test_t10_conflicting_environment_preserves_both_source_alternatives(self):
        record = self.check_source("O04")
        quotes = " ".join(record["extraction"]["supporting_quotes"])
        self.assertIn("staging", quotes)
        self.assertIn("production", quotes)

    def test_t11_conflicting_manager_is_not_arbitrarily_last_value_wins(self):
        record = self.check_source("O20")
        quotes = " ".join(record["extraction"]["supporting_quotes"])
        self.assertIn("Priya Shah", quotes)
        self.assertIn("Elena Park", quotes)

    def test_t12_embedded_override_is_evidence_and_inspect_message_routing(self):
        record = self.check_source("O06")
        self.assertEqual(record["extraction"]["permission"], "read")
        self.assertTrue(
            any("SYSTEM OVERRIDE:" in quote for quote in record["extraction"]["supporting_quotes"])
        )
        # The provider receives the source as data, without a trusted-role rewrite.
        source = load_document(ROOT / self.sources["O06"]["input"])
        self.assertEqual(self.provider.calls[0]["message"], source.message)

    def test_t13_withdrawal_needs_only_resolved_ID_and_date_for_confirmation(self):
        self.check_source("O05")

    def test_t14_missing_access_details_and_manager_remain_null_with_issues(self):
        for oracle in ("O03", "O09"):
            with self.subTest(oracle=oracle):
                self.check_source(oracle)

    def test_t15_change_requests_use_new_permission_not_prior_permission(self):
        for oracle, permission in (("O07", "write"), ("O19", "read")):
            with self.subTest(oracle=oracle):
                record = self.check_source(oracle)
                self.assertEqual(record["extraction"]["kind"], "change")
                self.assertEqual(record["extraction"]["permission"], permission)

    def test_t16_explicit_corrections_replace_environment_and_access_dates(self):
        for oracle in ("O08", "O15"):
            with self.subTest(oracle=oracle):
                record = self.check_source(oracle)
                self.assertFalse(
                    any("conflict" in issue.lower() for issue in record["extraction"]["issues"])
                )

    def test_t17_filename_identity_does_not_replace_stated_request_identifier(self):
        record = self.check_source("O16")
        self.assertEqual(record["document_id"], "IT-016.json")
        self.assertEqual(record["extraction"]["request_id"], "IT-061")

    def test_t18_other_and_unresolved_request_kinds_route_to_clarification(self):
        self.check_source("O17")
        self.check_variant(self.routing["extra_inputs"]["null-kind"])

    def test_t19_reversed_interval_retains_stated_dates_and_requires_clarification(self):
        self.check_source("O14")

    def test_t20_production_write_or_admin_each_trigger_risk_then_owner_review(self):
        for oracle in ("O02", "O12", "O13"):
            with self.subTest(oracle=oracle):
                self.check_source(oracle)

    def test_t21_authored_paraphrase_uses_the_same_extraction_and_routing_path(self):
        self.check_source("O21")

    def test_t22_each_required_fact_and_withdrawal_override_rule_precedence(self):
        expected_cases = self.routing["rule_precedence_variants"]
        descriptors = read_json(MOCKS / "rule-precedence.json")["cases"]
        self.assertEqual(
            [case["name"] for case in descriptors], [case["name"] for case in expected_cases]
        )
        self.assertEqual(len(expected_cases), 25)
        for case in expected_cases:
            with self.subTest(case=case["name"]):
                self.check_variant(case)

    def test_t22_postchecks_work_even_when_model_issue_labels_are_omitted(self):
        for oracle in ("O05", "O06", "O09", "O10", "O14", "O16"):
            with self.subTest(oracle=oracle):
                provider = MockProvider(MOCKS / "s04-postchecks-manifest.json")
                self.check_source(oracle, provider)

    def test_t22_schema_validation_precedes_override_routing(self):
        provider = MockProvider(MOCKS / "s04-invalid-schema-manifest.json")
        document = load_document(ROOT / self.sources["O06"]["input"])
        record = self.process(document, provider)
        for field, value in self.routing["error_route"].items():
            self.assertEqual(record[field], value)
        self.assertIsNone(record["extraction"])
        self.assertIn("schema", record["error"].lower())

    def test_t22_completion_validation_precedes_override_routing(self):
        provider = MockProvider(MOCKS / "s04-incomplete-manifest.json")
        document = load_document(ROOT / self.sources["O06"]["input"])
        record = self.process(document, provider)
        for field, value in self.routing["error_route"].items():
            self.assertEqual(record[field], value)
        self.assertIsNone(record["extraction"])
        self.assertIn("incomplete", record["error"].lower())

    def test_t23_all_twenty_sources_and_input_variants_match_independent_expectations(self):
        for number in range(1, 21):
            with self.subTest(oracle=f"O{number:02}"):
                self.check_source(f"O{number:02}")
        for name in ("metadata", "two-hundred-words", "followup"):
            with self.subTest(variant=name):
                self.check_variant(self.routing["extra_inputs"][name])
        self.assertEqual(len(self.provider.calls), 23)
