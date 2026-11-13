"""Load independent source documents without interpreting request facts."""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


class InputExportError(ValueError):
    """An input file cannot be read as a UTF-8 JSON message export."""


@dataclass(frozen=True)
class SourceDocument:
    """Keep original bytes authoritative for source identity and revision hashes."""

    document_id: str
    source_bytes: bytes
    source_sha256: str
    message: str
    export_metadata: dict


def load_document(path: str | Path) -> SourceDocument:
    """Load one export, retaining its filename and complete decoded message.

    Export metadata is available for display but never used to fill request
    facts. Errors identify the file and recovery action without echoing input
    content or the original exception's potentially sensitive details.
    """
    path = Path(path)
    try:
        source_bytes = path.read_bytes()
    except OSError:
        raise InputExportError(
            f"{path.name}: cannot read export; check the path and read permissions"
        ) from None

    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise InputExportError(
            f"{path.name}: invalid UTF-8; re-export the message as UTF-8 JSON"
        ) from None

    try:
        exported = json.loads(text)
    except json.JSONDecodeError:
        raise InputExportError(
            f"{path.name}: invalid JSON; correct the export syntax and retry"
        ) from None

    if not isinstance(exported, dict):
        raise InputExportError(
            f"{path.name}: export must be a JSON object with a message string"
        )
    if not isinstance(exported.get("message"), str):
        raise InputExportError(
            f"{path.name}: missing or non-string message; supply a message string"
        )

    return SourceDocument(
        document_id=path.name,
        source_bytes=source_bytes,
        source_sha256=source_sha256,
        message=exported["message"],
        export_metadata={key: value for key, value in exported.items() if key != "message"},
    )


def build_provider_request(document: SourceDocument, *, configuration: dict) -> dict:
    """Send message data plus provenance/settings, excluding display metadata."""
    return {
        "message": document.message,
        "source_sha256": document.source_sha256,
        "configuration": deepcopy(configuration),
    }
