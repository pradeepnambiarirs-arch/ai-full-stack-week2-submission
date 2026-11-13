"""Validate completed extraction responses before business-policy routing."""

from functools import lru_cache
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from access_intake.ingest import SourceDocument


DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "snapshot.schema.json"
DATE_FIELDS = ("request_date", "start_date", "end_date")


class ExtractionValidationError(ValueError):
    """A sanitized validation failure safe to place in an error record."""


@lru_cache(maxsize=8)
def _validator(schema_bytes: bytes) -> Draft202012Validator:
    """Cache by schema contents, so edits cannot leave a stale path-based cache."""
    try:
        schema = json.loads(schema_bytes.decode("utf-8"))
        Draft202012Validator.check_schema(schema)
    except (UnicodeDecodeError, json.JSONDecodeError, SchemaError):
        raise ExtractionValidationError(
            "invalid schema configuration; restore the supplied schema and retry extraction"
        ) from None
    return Draft202012Validator(schema)


def validate_shape(
    extraction: object, *, schema_path: str | Path = DEFAULT_SCHEMA_PATH
) -> None:
    """Apply the supplied schema without inferring missing or corrected facts."""
    try:
        schema_bytes = Path(schema_path).read_bytes()
    except OSError:
        raise ExtractionValidationError(
            "schema unavailable; check the schema path and read permissions, then retry extraction"
        ) from None

    validator = _validator(schema_bytes)
    try:
        validator.validate(extraction)
    except ValidationError:
        # jsonschema's exception can contain the rejected payload; do not echo it.
        raise ExtractionValidationError(
            "schema violation; check required fields, types and allowed values, then retry extraction"
        ) from None


def _reject_nonstandard_constant(_value: str) -> None:
    raise ExtractionValidationError(
        "invalid JSON constant; request a standard JSON extraction and retry"
    )


def _validated_extraction(
    document: SourceDocument, response: object, schema_path: str | Path
) -> dict:
    if not isinstance(response, dict):
        raise ExtractionValidationError(
            "invalid response envelope; request a complete structured response and retry extraction"
        )
    if response.get("refusal"):
        raise ExtractionValidationError(
            "provider refusal; inspect the message and provider configuration before retrying extraction"
        )
    if response.get("status") != "completed":
        raise ExtractionValidationError(
            "incomplete response; inspect provider completion and retry extraction"
        )
    if "message_status" in response and response["message_status"] != "completed":
        raise ExtractionValidationError(
            "incomplete output message; request a completed message and retry extraction"
        )

    output_text = response.get("output_text")
    if not isinstance(output_text, str):
        raise ExtractionValidationError(
            "missing or non-string output text; request JSON text and retry extraction"
        )
    try:
        extraction = json.loads(output_text, parse_constant=_reject_nonstandard_constant)
    except (json.JSONDecodeError, RecursionError):
        raise ExtractionValidationError(
            "invalid JSON output; request a complete JSON object and retry extraction"
        ) from None

    validate_shape(extraction, schema_path=schema_path)
    for field in DATE_FIELDS:
        value = extraction[field]
        # Calendar-validity policy remains open; enforce only the documented form.
        if value is not None and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
            raise ExtractionValidationError(
                f"invalid {field} date format; request YYYY-MM-DD or null and retry extraction"
            )
    if any(quote not in document.message for quote in extraction["supporting_quotes"]):
        raise ExtractionValidationError(
            "invalid supporting quote; use exact substrings of the decoded message and retry extraction"
        )
    return extraction


def validate_response(
    document: SourceDocument,
    response: object,
    *,
    response_source: str,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> dict:
    """Return validated facts or the policy error envelope with source provenance.

    The caller supplies response_source from its provider context, independent
    of untrusted response content. Successful results are not approved or
    assigned a business route here; the next step applies the review policy.
    """
    provenance = {
        "document_id": document.document_id,
        "source_sha256": document.source_sha256,
        "response_source": response_source,
    }
    try:
        extraction = _validated_extraction(document, response, schema_path)
    except ExtractionValidationError as error:
        return {
            **provenance,
            "extraction": None,
            "status": "error",
            "owner": "IT Service Desk",
            "next_action": "retry-extraction",
            "error": str(error),
        }
    return {**provenance, "extraction": extraction, "error": None}
