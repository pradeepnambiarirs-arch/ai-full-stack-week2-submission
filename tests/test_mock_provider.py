"""S01 / T01: tests first for a manifest-backed mock provider (R-105).

The proposed application API is MockProvider(manifest_path).extract(message,
source_sha256=..., configuration=...). It returns the saved response envelope.
Calls are logged in order with message, source_sha256, configuration and a
one-based call_index per source/configuration pair. Missing exact matches raise
MockFixtureNotFound with the saved error code. No provider implementation is
supplied by this test module; the import is deliberately inside setUp so the
existing fixture-backed checks still run before the expected missing-feature
errors are reported.
"""

import hashlib
import json

from support import MOCKS, ROOT, OfflineFixtureTestCase, read_json


class MockProviderT01(OfflineFixtureTestCase):
    def setUp(self):
        super().setUp()
        self.source_bytes = (ROOT / self.oracle["input"]).read_bytes()
        self.message = json.loads(self.source_bytes.decode("utf-8"))["message"]
        self.source_sha256 = hashlib.sha256(self.source_bytes).hexdigest()
        self.configuration = {"provider": "mock", "model": "fixture-v1"}
        self.missing = read_json(MOCKS / "fixture-not-found.json")

        from access_intake.providers.mock import MockFixtureNotFound, MockProvider

        self.missing_error = MockFixtureNotFound
        self.provider_class = MockProvider
        self.provider = MockProvider(MOCKS / "manifest.json")

    def extract(self, provider=None, **overrides):
        request = {
            "source_sha256": self.source_sha256,
            "configuration": self.configuration,
        }
        request.update(overrides)
        return (provider or self.provider).extract(self.message, **request)

    def test_t01_returns_saved_completed_facts_and_logs_request(self):
        response = self.extract()

        self.assertEqual(response["response_source"], "mock")
        self.assertEqual(response["status"], "completed")
        self.assertEqual(json.loads(response["output_text"]), self.oracle["extraction"])
        self.assertEqual(len(self.provider.calls), 1)
        call = self.provider.calls[0]
        self.assertEqual(call["message"], self.message)
        self.assertEqual(call["source_sha256"], self.source_sha256)
        self.assertEqual(call["configuration"], self.configuration)
        self.assertEqual(call["call_index"], 1)

    def test_t01_manifest_sequence_is_deterministic_between_instances(self):
        other = self.provider_class(MOCKS / "manifest.json")

        for provider in (self.provider, other):
            for _ in range(2):
                response = self.extract(provider)
                self.assertEqual(
                    json.loads(response["output_text"]), self.oracle["extraction"]
                )
            self.assertEqual(len(provider.calls), 2)
            self.assertEqual([call["call_index"] for call in provider.calls], [1, 2])
        self.assertEqual(self.provider.calls, other.calls)

    def test_t01_unknown_hash_does_not_fall_back_to_same_request_id(self):
        # JSON whitespace changes the raw source hash but not the message/ID.
        unknown_hash = hashlib.sha256(self.source_bytes + b" ").hexdigest()
        with self.assertRaisesRegex(self.missing_error, self.missing["error_code"]):
            self.extract(source_sha256=unknown_hash)

        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.provider.calls[0]["source_sha256"], unknown_hash)

    def test_t01_unregistered_configuration_has_a_visible_error(self):
        unmatched = {"provider": "mock", "model": "fixture-v2"}
        with self.assertRaisesRegex(self.missing_error, self.missing["error_code"]):
            self.extract(configuration=unmatched)

        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.provider.calls[0]["configuration"], unmatched)

    def test_t01_exhausted_sequence_does_not_silently_replay_last_reply(self):
        for _ in range(2):
            response = self.extract()
            self.assertEqual(json.loads(response["output_text"]), self.oracle["extraction"])

        with self.assertRaisesRegex(self.missing_error, self.missing["error_code"]):
            self.extract()

        self.assertEqual(len(self.provider.calls), 3)
        self.assertEqual([call["call_index"] for call in self.provider.calls], [1, 2, 3])
