# Verification evidence

These are proposed local assessments for human review. External submission is pending. No live model calls were made for the committed evidence.

## Configuration and origin

Runtime: Python 3.12.3, SQLite 3.45.1; local Linux disk, single host. Mock baseline model: fixture-v1; workers=4, rpm=0 unless a test states otherwise. Provider-adapter tests use saved HTTP responses and an injected credential supplier, never API_KEY or the network. Workload tests use workers=2 per operator, two operators, rpm=0.

Every exported observation includes its response_source, configuration and policy version. The request example uses a separately labeled capture-only OpenAI configuration; it did not produce the mock records.

```json
[
  {
    "document_id": "IT-001.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-002.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-003.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-004.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-005.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-006.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-007.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-008.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-009.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-010.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-011.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-012.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-013.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-014.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-015.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-016.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-017.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-018.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-019.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-020.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  },
  {
    "document_id": "IT-021.json",
    "response_source": "mock",
    "configuration": {
      "mock_manifest": "/home/user/ai-full-stack-week2-submission/tests/mock_responses/s04-manifest.json",
      "model": "fixture-v1",
      "provider": "mock"
    },
    "policy_version": "087f3e9bad4ae522410d7ed82bd90e77db7f2cf7f515908c6e765dd3fb6d135d"
  }
]
```

## Commands and actual artifact assertions

Run from the repository root with the README environment active. The test command removes API_KEY before Python starts. Tests load saved mock replies and independent source oracles.

```bash
env -u API_KEY python3 -m unittest discover -s tests -v > planning/test-run.txt 2>&1
env -u API_KEY python3 -m access_intake intake materials/requests tests/inputs/IT-021.json --db var/intake.sqlite --config config.mock.json
env -u API_KEY python3 -m access_intake export --db var/intake.sqlite --out deliverables
env -u API_KEY python3 -m access_intake accuracy --actual deliverables/extractions.jsonl --expected tests/expected/source-facts.json --out deliverables/accuracy.md
env -u API_KEY python3 -m access_intake verify --db var/intake.sqlite --out deliverables/verification.md
```

The following assertions were executed by this verifier, rather than inferred from test fixtures. Exact-match disagreement fails this local comparison even when a purpose paraphrase might be factually faithful; review those misses separately.

| Assertion | Intended comparison | Observed local result |
|---|---|---|
| export publication | Manifest hashes match files; queue and extraction rows agree without duplicate identities. | PASS |
| current database snapshot | Exactly the database current rows, with no pending desired source revisions. | PASS |
| envelope, schema and saved source provenance | Required envelope fields; original-byte hashes; schema-valid successes or actionable null-extraction failures; producing settings/policy retained. | PASS |
| independent source expectations | Exactly the independently authored source cases; all 12 scalar facts and routes match, with quote/issue/hash integrity and no unreviewed discrepancies. | PASS |
| redacted request evidence | Implemented adapter capture shows a model/configuration, redacted authorization and response handling; capture-only is distinct from a response. | PASS |

Comparison counters (response origins: mock):

```json
{
  "matches": 252,
  "denominator": 252,
  "whole_record_matches": 21,
  "route_matches": 21,
  "documents": 21,
  "factual_errors": [],
  "manual_review": [],
  "route_errors": [],
  "integrity_errors": [],
  "missing_documents": [],
  "extraction_errors": [],
  "field_matches": {
    "request_id": 21,
    "request_date": 21,
    "kind": 21,
    "requester": 21,
    "team": 21,
    "system": 21,
    "environment": 21,
    "permission": 21,
    "business_purpose": 21,
    "start_date": 21,
    "end_date": 21,
    "manager": 21
  },
  "origins": [
    "mock"
  ]
}
```

## Saved suite observations

Evidence file: `/home/user/ai-full-stack-week2-submission/planning/test-run.txt` (SHA-256 `f96160a750738fd7a79320b00743080e37fa2c82343efa0a35467912eb11d976`). The verifier reads this saved evidence; it does not itself rerun the suite. Per-test names and results are in that file. This is mock/offline verification, with case-specific settings in the test source.

```text
test_t28_global_claim_limit_is_shared_between_processes (test_workers.WorkersS06.test_t28_global_claim_limit_is_shared_between_processes) ... MOCK workload=400 workers=2 operators=2 rpm=0 model=fixture-v1 elapsed_seconds=8.103
MOCK workload=2000 workers=2 operators=2 rpm=0 model=fixture-v1 elapsed_seconds=70.058
Ran 86 tests in 84.031s
OK
```

## Failed observations and repairs

Step-first failures remain in planning/sNN-tests-first.txt; later successful runs are in planning/sNN-implementation.txt. S07 had four naturally already-passing new tests; its missing operations failed and were implemented. The S05 before-repair run (planning/s05-before-repair.txt) records the WAL transaction initialization failure; journal setup was moved outside the transaction, then all 53 tests passed. S11 first failed on missing workload template support, handover text and lockfile; its repaired run passed all 83 tests. S12 first failed because verification module/command were missing; the final saved run records the implemented rerun. None of those earlier failures is rewritten as an earlier pass.

## Operating limits and recovery

Supported boundary: operators share a local SQLite database on a single host. Two overlapping processes, claim limits, publication rollback, stale-worker fencing, partial queue visibility and expired-lease resumption are tested. SQLite WAL and BEGIN IMMEDIATE serialize short writes; provider calls run outside transactions. The workload check covers 400 and 2,000 mock messages, with recorded timings, not a live throughput SLA. No multi-host/network filesystem or power-loss durability claim is made.

Use queue/show/history to locate completed, pending and failed records. After interruption, resume requeues expired leases from stored source/configuration; completed results remain. Defaults: 120-second lease, heartbeat at most every 10 seconds. Use the recorded retry command for failures; no hidden model retries occur. A 429 creates shared cooldown. Source, model/prompt/schema or supported policy changes create refreshed versions; previous attempts remain in history. During refresh, older current results are labeled as previous while desired work is pending. A failed refresh publishes an error, preserving the older success in history.

Live provider availability, live extraction accuracy, API_KEY environment bridge execution, arbitrary policy-prose interpretation, subtle injection detection beyond the documented patterns and real-service throttling remain unverified. Impossible calendar dates remain open for policy clarification; only YYYY-MM-DD form is enforced. Mock tests validate pipeline behavior and authored response handling, not general language-model factual reliability.

## Submission preparation

The local verification-manifest.json hashes the required outputs after report generation. It is an artifact inventory, not proof of external submission. Inspect the final git commit trailer and Entire checkpoint for coding-session pairing (R-121); enabled capture alone is insufficient. Compare the final commit with the remote default branch after an authorized push (R-122). Inspect Classroom for only the root repository URL (R-123). These three checks remain pending; this command neither pushes nor submits.

