"""S02 / T02–T04: test source ingestion before implementing it.

Proposed API: access_intake.ingest.load_document(path) returns a document with
document_id, source_bytes, source_sha256, message and export_metadata. Its
build_provider_request(document, configuration=...) produces only message,
source_sha256 and configuration kwargs for the existing provider interface.
InputExportError reports invalid exports with their filename. No routing or
response-validation implementation is required by these tests.
"""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from access_intake.providers.mock import MockProvider
from support import MOCKS, ROOT, OfflineFixtureTestCase, read_json


class SourceIngestionS02(OfflineFixtureTestCase):
    def setUp(self):
        super().setUp()
        self.expected_cases = read_json(
            ROOT / "tests" / "expected" / "source-facts.json"
        )["cases"]
        self.configuration = {"provider": "mock", "model": "fixture-v1"}
        self.provider = MockProvider(MOCKS / "s02-manifest.json")
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.staging = Path(self.temporary_directory.name)

        from access_intake.ingest import (
            InputExportError,
            build_provider_request,
            load_document,
        )

        self.input_error = InputExportError
        self.build_request = build_provider_request
        self.load_document = load_document

    def stage(self, fixture: str, group: str, basename: str = "IT-001.json") -> Path:
        """Preserve the original bytes under the intended input filename."""
        path = self.staging / group / basename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / "tests" / "inputs" / fixture).read_bytes())
        return path

    def assert_ingested_source(self, document, path):
        raw = path.read_bytes()
        exported = json.loads(raw.decode("utf-8"))
        self.assertEqual(document.document_id, path.name)
        self.assertEqual(document.source_bytes, raw)
        self.assertEqual(document.source_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(document.message, exported["message"])
        self.assertEqual(
            document.export_metadata,
            {name: value for name, value in exported.items() if name != "message"},
        )

    def assert_raw_fixture_response(self, document, oracle_name):
        request = self.build_request(document, configuration=self.configuration)
        self.assertEqual(
            request,
            {
                "message": document.message,
                "source_sha256": document.source_sha256,
                "configuration": self.configuration,
            },
        )
        response = self.provider.extract(**request)
        self.assertEqual(response["response_source"], "mock")
        self.assertEqual(response["status"], "completed")
        facts = json.loads(response["output_text"])
        self.assertEqual(facts, self.expected_cases[oracle_name]["extraction"])
        return facts

    def test_t02_loads_all_twenty_exports_with_original_bytes_and_filenames(self):
        inputs = sorted((ROOT / "materials" / "requests").glob("*.json"))
        self.assertEqual(len(inputs), 20)
        for number, path in enumerate(inputs, 1):
            with self.subTest(document=path.name):
                document = self.load_document(path)
                self.assert_ingested_source(document, path)
                self.assert_raw_fixture_response(document, f"O{number:02}")
        self.assertEqual(len(self.provider.calls), 20)

    def test_t02_same_request_id_in_two_filenames_stays_two_documents(self):
        original_path = ROOT / "materials" / "requests" / "IT-001.json"
        followup_path = self.stage(
            "IT-001-followup.json", "followup", "IT-001-followup.json"
        )
        original = self.load_document(original_path)
        followup = self.load_document(followup_path)

        self.assert_ingested_source(original, original_path)
        self.assert_ingested_source(followup, followup_path)
        self.assertEqual(original.document_id, "IT-001.json")
        self.assertEqual(followup.document_id, "IT-001-followup.json")
        self.assertNotEqual(original.document_id, followup.document_id)
        self.assertEqual(original.source_sha256, followup.source_sha256)
        for document in (original, followup):
            facts = self.assert_raw_fixture_response(document, "O01")
            self.assertEqual(facts["request_id"], self.oracle["extraction"]["request_id"])
        self.assertEqual(len(self.provider.calls), 2)
        # Mismatch issues and queue routing are deliberately left for S04.

    def test_t02_whitespace_changes_source_hash_without_changing_message(self):
        original_path = ROOT / "materials" / "requests" / "IT-001.json"
        changed_path = self.stage("IT-001.whitespace.json", "whitespace")
        original = self.load_document(original_path)
        changed = self.load_document(changed_path)

        self.assert_ingested_source(original, original_path)
        self.assert_ingested_source(changed, changed_path)
        self.assertEqual(original.document_id, changed.document_id)
        self.assertNotEqual(original.source_bytes, changed.source_bytes)
        self.assertNotEqual(original.source_sha256, changed.source_sha256)
        self.assertEqual(original.message, changed.message)
        self.assertEqual(original.export_metadata, changed.export_metadata)
        for document in (original, changed):
            self.assert_raw_fixture_response(document, "O01")

    def test_t02_invalid_export_shape_is_rejected_before_provider_use(self):
        for name in (
            "invalid-utf8.json",
            "invalid-json.json",
            "missing-message.json",
            "non-string-message.json",
        ):
            with self.subTest(fixture=name):
                path = ROOT / "tests" / "inputs" / "invalid" / name
                with self.assertRaises(self.input_error) as caught:
                    self.load_document(path)
                self.assertIn(path.name, str(caught.exception))
        self.assertEqual(self.provider.calls, [])

    def test_t03_metadata_is_retained_for_display_but_not_sent_as_facts(self):
        original_path = ROOT / "materials" / "requests" / "IT-001.json"
        altered_path = self.stage("IT-001.metadata.json", "metadata")
        original = self.load_document(original_path)
        altered = self.load_document(altered_path)

        self.assert_ingested_source(altered, altered_path)
        self.assertEqual(original.message, altered.message)
        self.assertEqual(altered.export_metadata["exported_at"], "2030-01-01T00:00:00Z")
        self.assertEqual(altered.export_metadata["subject"], "Approved production admin")
        self.assertNotEqual(original.source_sha256, altered.source_sha256)
        for document in (original, altered):
            facts = self.assert_raw_fixture_response(document, "O01")
            self.assertEqual(
                facts["request_date"], self.oracle["extraction"]["request_date"]
            )
            self.assertEqual(self.provider.calls[-1]["message"], original.message)

    def test_t04_two_hundred_word_message_preserves_the_final_manager_fact(self):
        path = self.stage("IT-001.200-words.json", "two-hundred-words")
        document = self.load_document(path)

        self.assert_ingested_source(document, path)
        self.assertEqual(len(document.message.split()), 200)
        self.assertTrue(document.message.endswith("My manager is Priya Shah."))
        facts = self.assert_raw_fixture_response(document, "O01")
        self.assertEqual(facts["manager"], self.oracle["extraction"]["manager"])
        self.assertEqual(self.provider.calls[0]["message"], document.message)
