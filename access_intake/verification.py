"""Reproducible local checks; external submission is never inferred from tests."""
import hashlib
import json
from pathlib import Path
import platform
import re
import sqlite3

from access_intake.accuracy import compare_records
from access_intake.artifacts import atomic, check_export
from access_intake.validation import validate_shape

ROOT = Path(__file__).resolve().parents[1]


def write_verification(store, out, *, expected_path=ROOT/'tests/expected/source-facts.json',
                       observations_path=None, test_run_path=ROOT/'planning/test-run.txt'):
    out = Path(out)
    folder = out.parent
    checks = []

    def check(name, comparison, operation):
        try:
            passed = bool(operation())
        except (OSError, ValueError, KeyError, TypeError):
            passed = False
        checks.append(dict(assertion=name, comparison=comparison, passed=passed))

    def consistent():
        check_export(folder)
        return True

    check('export publication', 'Manifest hashes match files; queue and extraction rows agree without duplicate identities.', consistent)
    try:
        records = [json.loads(line) for line in (folder/'extractions.jsonl').read_text().splitlines()]
    except (OSError, ValueError):
        records = []
    expected = json.loads(Path(expected_path).read_text())['cases']
    current = [{k:v for k,v in row.items() if k not in ('pending','previous_version','desired_source_sha256')} for row in store.queue()]
    check('current database snapshot', 'Exactly the database current rows, with no pending desired source revisions.',
          lambda: records == current and not store.pending())

    def envelopes():
        required = {'document_id','source_sha256','extraction','status','owner','next_action','error','response_source'}
        for record in records:
            if not required <= record.keys():
                return False
            revision = store.revision(record['revision_id'])
            if hashlib.sha256(revision['source']).hexdigest() != record['source_sha256']:
                return False
            if record['extraction'] is None:
                if not (record['status']=='error' and record['owner']=='IT Service Desk' and
                        record['next_action']=='retry-extraction' and record['error'] and record.get('retry_command')):
                    return False
            else:
                validate_shape(record['extraction'], schema_path=store.schema_snapshot(revision))
                if record['error'] is not None:
                    return False
            if not record['response_source'] or not record.get('configuration') or not record.get('policy_version'):
                return False
        return bool(records)

    check('envelope, schema and saved source provenance', 'Required envelope fields; original-byte hashes; schema-valid successes or actionable null-extraction failures; producing settings/policy retained.', envelopes)
    comparison = compare_records(records, expected)
    check('independent source expectations', 'Exactly the independently authored source cases; all 12 scalar facts and routes match, with quote/issue/hash integrity and no unreviewed discrepancies.',
          lambda: set(r['document_id'] for r in records) == {Path(c['input']).name for c in expected.values()} and
          comparison['matches']==comparison['denominator'] and comparison['route_matches']==comparison['documents'] and
          not any(comparison[k] for k in ('factual_errors','manual_review','integrity_errors','missing_documents','extraction_errors')))

    def redacted_request():
        evidence = json.loads((folder/'request-evidence.json').read_text())
        return (evidence['request']['headers']['Authorization']=='[REDACTED]' and
                bool(evidence['request']['body']['model']) and bool(evidence['response_handling']) and
                'no provider response' in evidence['observation'])

    check('redacted request evidence', 'Implemented adapter capture shows a model/configuration, redacted authorization and response handling; capture-only is distinct from a response.', redacted_request)
    simulated = json.loads(Path(observations_path).read_text()) if observations_path else None
    result = dict(passed=all(c['passed'] for c in checks), checks=checks, comparison=comparison,
                  external_pending=['R-121','R-122','R-123'], simulated_events=simulated['events'] if simulated else [])
    lines = ['# Verification evidence', '',
        'These are proposed local assessments for human review. External submission is pending. No live model calls were made for the committed evidence.', '',
        '## Configuration and origin', '',
        f'Runtime: Python {platform.python_version()}, SQLite {sqlite3.sqlite_version}; local Linux disk, single host. Mock baseline model: fixture-v1; workers=4, rpm=0 unless a test states otherwise. Provider-adapter tests use saved HTTP responses and an injected credential supplier, never API_KEY or the network. Workload tests use workers=2 per operator, two operators, rpm=0.', '',
        'Every exported observation includes its response_source, configuration and policy version. The request example uses a separately labeled capture-only OpenAI configuration; it did not produce the mock records.', '',
        '```json', json.dumps([{k:r.get(k) for k in ('document_id','response_source','configuration','policy_version')} for r in records], indent=2), '```', '',
        '## Commands and actual artifact assertions', '',
        'Run from the repository root with the README environment active. The test command removes API_KEY before Python starts. Tests load saved mock replies and independent source oracles.', '',
        '```bash',
        'env -u API_KEY python3 -m unittest discover -s tests -v > planning/test-run.txt 2>&1',
        'env -u API_KEY python3 -m access_intake intake materials/requests tests/inputs/IT-021.json --db var/intake.sqlite --config config.mock.json',
        'env -u API_KEY python3 -m access_intake export --db var/intake.sqlite --out deliverables',
        'env -u API_KEY python3 -m access_intake accuracy --actual deliverables/extractions.jsonl --expected tests/expected/source-facts.json --out deliverables/accuracy.md',
        'env -u API_KEY python3 -m access_intake verify --db var/intake.sqlite --out deliverables/verification.md', '```', '',
        'The following assertions were executed by this verifier, rather than inferred from test fixtures. Exact-match disagreement fails this local comparison even when a purpose paraphrase might be factually faithful; review those misses separately.', '',
        '| Assertion | Intended comparison | Observed local result |', '|---|---|---|']
    for c in checks:
        lines.append(f"| {c['assertion']} | {c['comparison']} | {'PASS' if c['passed'] else 'FAIL'} |")
    lines += ['', 'Comparison counters (response origins: '+', '.join(comparison['origins'])+'):','', '```json',json.dumps(comparison,indent=2),'```']
    if test_run_path and Path(test_run_path).exists():
        log = Path(test_run_path).read_text()
        lines += ['', '## Saved suite observations', '',
            f'Evidence file: `{test_run_path}` (SHA-256 `{hashlib.sha256(log.encode()).hexdigest()}`). The verifier reads this saved evidence; it does not itself rerun the suite. Per-test names and results are in that file. This is mock/offline verification, with case-specific settings in the test source.', '', '```text']
        lines += [line for line in log.splitlines() if re.search(r'^Ran \d+ tests|^OK$|^FAILED|MOCK workload=',line)]
        lines += ['```']
    else:
        lines += ['', 'No saved full-suite run was supplied; artifact checks alone do not establish suite completion.']
    lines += ['', '## Failed observations and repairs', '',
        'Step-first failures remain in planning/sNN-tests-first.txt; later successful runs are in planning/sNN-implementation.txt. S07 had four naturally already-passing new tests; its missing operations failed and were implemented. The S05 before-repair run (planning/s05-before-repair.txt) records the WAL transaction initialization failure; journal setup was moved outside the transaction, then all 53 tests passed. S11 first failed on missing workload template support, handover text and lockfile; its repaired run passed all 83 tests. S12 first failed because verification module/command were missing; the final saved run records the implemented rerun. None of those earlier failures is rewritten as an earlier pass.']
    if simulated:
        lines += ['', '**The following are simulated mock report-rendering events, not actual application or suite results. They do not affect the actual checks above.**', '',
            'Configuration: '+json.dumps(simulated['configuration'])+'; origin: '+simulated['origin']+'.', '',
            '| Phase | Assertion | Expected | Observed | Result |','|---|---|---|---|---|']
        for event in simulated['events']:
            lines.append('| '+' | '.join(str(event[k]) for k in ('phase','assertion','expected','observed'))+f" | {'PASS' if event['passed'] else 'FAIL'} |")
    lines += ['', '## Operating limits and recovery', '',
        'Supported boundary: operators share a local SQLite database on a single host. Two overlapping processes, claim limits, publication rollback, stale-worker fencing, partial queue visibility and expired-lease resumption are tested. SQLite WAL and BEGIN IMMEDIATE serialize short writes; provider calls run outside transactions. The workload check covers 400 and 2,000 mock messages, with recorded timings, not a live throughput SLA. No multi-host/network filesystem or power-loss durability claim is made.', '',
        'Use queue/show/history to locate completed, pending and failed records. After interruption, resume requeues expired leases from stored source/configuration; completed results remain. Defaults: 120-second lease, heartbeat at most every 10 seconds. Use the recorded retry command for failures; no hidden model retries occur. A 429 creates shared cooldown. Source, model/prompt/schema or supported policy changes create refreshed versions; previous attempts remain in history. During refresh, older current results are labeled as previous while desired work is pending. A failed refresh publishes an error, preserving the older success in history.', '',
        'Live provider availability, live extraction accuracy, API_KEY environment bridge execution, arbitrary policy-prose interpretation, subtle injection detection beyond the documented patterns and real-service throttling remain unverified. Impossible calendar dates remain open for policy clarification; only YYYY-MM-DD form is enforced. Mock tests validate pipeline behavior and authored response handling, not general language-model factual reliability.', '',
        '## Submission preparation', '',
        'The local verification-manifest.json hashes the required outputs after report generation. It is an artifact inventory, not proof of external submission. Inspect the final git commit trailer and Entire checkpoint for coding-session pairing (R-121); enabled capture alone is insufficient. Compare the final commit with the remote default branch after an authorized push (R-122). Inspect Classroom for only the root repository URL (R-123). These three checks remain pending; this command neither pushes nor submits.', '']
    atomic(out, ('\n'.join(lines)+'\n').encode())
    names=('extractions.jsonl','queue.json','accuracy.md','request-evidence.json',out.name)
    inventory={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() if (folder/name).is_file() else None for name in names}
    atomic(folder/'verification-manifest.json', (json.dumps({'files':inventory,'local_checks_passed':result['passed'],'external_pending':result['external_pending']},indent=2)+'\n').encode())
    return result
