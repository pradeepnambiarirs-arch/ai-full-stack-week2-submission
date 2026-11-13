"""Compose provider extraction, validation, deterministic checks and human routing."""
from copy import deepcopy
from pathlib import Path
import re
from access_intake.ingest import build_provider_request
from access_intake.validation import DEFAULT_SCHEMA_PATH, validate_response, validate_shape

REQUIRED = ('request_id','request_date','requester','team','system','environment','permission','business_purpose','start_date','end_date','manager')

def load_extraction_prompt():
    return (Path(__file__).parent / 'prompts' / 'extract.txt').read_text(encoding='utf-8')

def error_record(document, source, message):
    return dict(document_id=document.document_id, source_sha256=document.source_sha256,
                response_source=source, extraction=None, error=message,
                status='error', owner='IT Service Desk', next_action='retry-extraction')

def route_extraction(document, extraction, *, policy=None):
    facts = deepcopy(extraction)
    issues = facts['issues']
    def issue(field, text):
        if not any(field.replace('_',' ') in item.lower().replace('_',' ') for item in issues):
            issues.append(f'{field}: {text}')
    for field, value in facts.items():
        if field not in ('issues','supporting_quotes') and value is None:
            issue(field, 'missing or unresolved in the source message')
    mismatch = facts['request_id'] is not None and facts['request_id'] != Path(document.document_id).stem
    if mismatch:
        issue('mismatch', 'request_id differs from the input filename; clarify the identifier')
    reversed_dates = bool(facts['start_date'] and facts['end_date'] and facts['start_date'] > facts['end_date'])
    if reversed_dates:
        issue('start_date', 'start_date is after end_date; clarify the access interval')
    override_match = re.search(r'SYSTEM\s+OVERRIDE:|bypass\s+approval\s+rules|highest-priority\s+system\s+instruction', document.message, re.I)
    override = bool(override_match) or any('override' in item.lower() for item in issues)
    if override:
        issue('override', 'instruction override attempt; inspect the message as data')
        if override_match and not any(override_match.group() in quote for quote in facts['supporting_quotes']):
            facts['supporting_quotes'].append(document.message[override_match.start():])
        owner, status, action = 'IT Service Desk', 'review', 'inspect-message'
    elif facts['kind'] == 'withdrawal' and facts['request_id'] and facts['request_date']:
        owner, status, action = 'IT Service Desk', 'review', 'confirm-withdrawal'
    elif facts['kind'] not in ('new','change') or any(facts[field] is None for field in REQUIRED) or mismatch or reversed_dates or any('conflict' in item.lower() for item in issues):
        owner, status, action = 'IT Service Desk', 'needs-information', 'clarify'
    elif facts['environment'] == 'production' or facts['permission'] in ('write','admin') or (policy or {}).get('staging_read_requires_security', False):
        owner, status, action = 'Security Review', 'review', 'review-risk-then-owner'
    else:
        owner, status, action = 'System Owner', 'review', 'review-request'
    return facts, dict(owner=owner, status=status, next_action=action)

def process_document(document, *, provider, configuration, schema_path=DEFAULT_SCHEMA_PATH, policy=None):
    source = getattr(provider, 'response_source', 'mock')
    try:
        response = provider.extract(**build_provider_request(document, configuration=configuration))
    except Exception:
        return error_record(document, source, 'provider request failed; inspect provider availability and retry extraction')
    source = getattr(provider, 'response_source', source)
    result = validate_response(document, response, response_source=source, schema_path=schema_path)
    if result['error'] is not None:
        return result
    facts, route = route_extraction(document, result['extraction'], policy=policy)
    validate_shape(facts, schema_path=schema_path)
    return dict(result, extraction=facts, **route)
