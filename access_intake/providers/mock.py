"""Read explicitly registered responses from local fixtures, without model access."""

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from threading import Lock


class MockFixtureNotFound(LookupError):
    """No saved response matches the requested source/configuration/call."""


def _configuration_key(configuration: dict) -> str:
    """Match public JSON processing settings independently of key order."""
    return json.dumps(configuration, sort_keys=True, separators=(",", ":"), allow_nan=False)


class MockProvider:
    """Replay a manifest's exact source/configuration sequences.

    Response paths are relative to the manifest directory. Each instance has
    independent counters and an in-memory call log, including unsuccessful
    lookups. Configuration must contain only public processing settings;
    this provider neither obtains credentials nor falls back to a live model.
    """

    def __init__(self, manifest_path: str | Path):
        path = Path(manifest_path).resolve()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("version") != 1:
            raise ValueError("unsupported mock manifest version")

        self._responses: dict[tuple[str, str, int], Path] = {}
        for entry in manifest["responses"]:
            key = (
                entry["source_sha256"],
                _configuration_key(entry["configuration"]),
                entry["call_index"],
            )
            if key in self._responses:
                raise ValueError("duplicate mock manifest response registration")
            response_path = (path.parent / entry["response_file"]).resolve()
            if not response_path.is_relative_to(path.parent):
                raise ValueError("mock response must be inside the manifest directory")
            self._responses[key] = response_path

        self._counts: Counter[tuple[str, str]] = Counter()
        self._calls: list[dict] = []
        self._lock = Lock()

    @property
    def calls(self) -> list[dict]:
        """Return a snapshot so callers cannot rewrite recorded requests."""
        with self._lock:
            return deepcopy(self._calls)

    def extract(self, message: str, *, source_sha256: str, configuration: dict) -> dict:
        """Return the next registered envelope, or fail visibly without guessing."""
        settings = deepcopy(configuration)
        sequence = (source_sha256, _configuration_key(settings))
        with self._lock:
            self._counts[sequence] += 1
            call_index = self._counts[sequence]
            self._calls.append(
                {
                    "message": message,
                    "source_sha256": source_sha256,
                    "configuration": settings,
                    "call_index": call_index,
                }
            )
            response_path = self._responses.get((*sequence, call_index))

        if response_path is None:
            raise MockFixtureNotFound(
                "mock-fixture-not-found: register a response for this source, "
                "configuration and call index in the mock manifest"
            )

        try:
            # Reload each envelope; a caller's mutations cannot alter future replies.
            return json.loads(response_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise MockFixtureNotFound(
                "mock-fixture-not-found: registered response file is missing"
            ) from None
