"""Offline, saved-fixture test support; this is not an application provider."""

import http.client
import json
from pathlib import Path
import unittest
from unittest import mock
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
MOCKS = ROOT / "tests" / "mock_responses"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class OfflineFixtureTestCase(unittest.TestCase):
    """All current tests load saved replies and forbid network entry points.

    Run via the plan's shell command, which removes credentials before Python
    starts. This harness never inspects or copies the process environment.
    """

    def setUp(self):
        super().setUp()
        # Import the HTTP modules above before patching socket's class; SSL
        # initialization must not attempt to subclass a mocked socket type.
        for target in (
            "socket.socket",
            "socket.create_connection",
            "socket.getaddrinfo",
            "urllib.request.urlopen",
            "http.client.HTTPConnection.connect",
            "http.client.HTTPSConnection.connect",
        ):
            guard = mock.patch(
                target,
                side_effect=AssertionError("network access is forbidden in tests"),
            )
            blocked = guard.start()
            self.addCleanup(guard.stop)
            # Detect attempts even when application code catches the exception.
            self.addCleanup(blocked.assert_not_called)

        self.saved_response = read_json(MOCKS / "IT-001.complete.json")
        self.saved_extraction = json.loads(self.saved_response["output_text"])
        # The oracle is independent of the saved provider reply.
        self.oracle = read_json(ROOT / "tests" / "expected" / "source-facts.json")[
            "cases"
        ]["O01"]
