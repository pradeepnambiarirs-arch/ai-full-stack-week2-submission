"""Fixture-backed starter checks; these do not establish application behavior."""
import hashlib
import json
import unittest

from support import OfflineFixtureTestCase, ROOT


class SuppliedFiles(OfflineFixtureTestCase):
    def test_each_request_export_has_message_text_and_a_hash(self):
        exports = sorted((ROOT / "materials" / "requests").glob("*.json"))
        self.assertEqual(len(exports), 20)
        for path in exports:
            raw = path.read_bytes()
            self.assertIsInstance(json.loads(raw.decode("utf-8"))["message"], str, path.name)
            self.assertEqual(len(hashlib.sha256(raw).hexdigest()), 64)
        source = json.loads((ROOT / self.oracle["input"]).read_text(encoding="utf-8"))
        self.assertEqual(
            self.saved_extraction["request_id"], self.oracle["extraction"]["request_id"]
        )
        for quote in self.saved_extraction["supporting_quotes"]:
            self.assertIn(quote, source["message"])

    def test_the_schema_names_the_fields_it_requires(self):
        schema = json.loads((ROOT / "snapshot.schema.json").read_text(encoding="utf-8"))
        self.assertIn("request_id", schema["required"])
        # Check this saved fixture's keys, not an unimplemented validator.
        self.assertEqual(set(self.saved_extraction), set(schema["required"]))


class MockResponse(OfflineFixtureTestCase):
    def test_a_mock_reply_is_read_with_no_key_and_no_network(self):
        self.assertEqual(self.saved_response["response_source"], "mock")
        self.assertEqual(self.saved_response["status"], "completed")
        self.assertEqual(self.saved_extraction, self.oracle["extraction"])


if __name__ == "__main__":
    unittest.main()
