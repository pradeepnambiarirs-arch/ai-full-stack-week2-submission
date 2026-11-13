# Northstar access-request intake

A Python CLI prepares access requests for human review. It never grants access or treats a named manager as approval. Security Review examines risk and forwards its recommendation to the human system owner. The supplied company and requests are fictional.

## Setup and offline verification

Supported runtime: Python 3.11+ on Linux, SQLite on local disk. Tested with Python 3.12.3. Run commands from this repository root. Create an environment and install the exact hashed dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --require-hashes -r requirements.lock
```

On a minimal managed image without ensurepip, use the installed `uv`: `python3 -m venv --without-pip .venv`, then `uv pip install --python .venv/bin/python --require-hashes -r requirements.lock`. Activate `.venv` for the remaining commands. The offline clean-install test uses `uv`; have it available on PATH before running that test.

Prepare the wheelhouse once during setup (this download is not performed by tests), then run the entire suite without a model key or network access:

```bash
python3 -m pip download --require-hashes -r requirements.lock --dest .wheelhouse
# If the minimal environment has no pip, use the system pip for the download.
env -u API_KEY python3 -m unittest discover -s tests -v
```

Tests use saved responses under `tests/mock_responses/`, independent expectations in `tests/expected/`, temporary databases and network-denial guards, including the CLI subprocesses. No test executes the environment credential loader or calls a real model. The clean-install check uses only `.wheelhouse` with `--no-index` and `--require-hashes`. Wheelhouse binaries and runtime databases are ignored by Git.

## Intake and handover

Reproduce the committed mock outputs for the 20 supplied exports plus the authored paraphrase:

```bash
python3 -m access_intake intake materials/requests tests/inputs/IT-021.json --db var/intake.sqlite --config config.mock.json
python3 -m access_intake queue --db var/intake.sqlite
python3 -m access_intake show IT-016.json --db var/intake.sqlite
python3 -m access_intake history IT-016.json --db var/intake.sqlite
python3 -m access_intake export --db var/intake.sqlite --out deliverables
python3 -m access_intake accuracy --actual deliverables/extractions.jsonl --expected tests/expected/source-facts.json --out deliverables/accuracy.md
python3 -m access_intake verify --db var/intake.sqlite --out deliverables/verification.md
```

Each record identifies its source filename, original-byte SHA-256, producing settings and policy version. Export metadata is retained for display; only `message` supplies business facts. A filename is the document identity even if the message states a different request ID. Missing/conflicting facts remain null with issues. Explicit corrections replace earlier values; relative dates remain unresolved. Impossible calendar dates remain an open policy question; the validator currently enforces only the documented YYYY-MM-DD form.

Inspect completed work from another shell while intake runs: `python3 -m access_intake queue --db var/intake.sqlite --watch`. `--iterations 2 --interval 0.5` gives a bounded watch. New documents show pending state; a refresh labels the previous result as the earlier version while new work is pending. Each terminal result is published immediately, not at the end of the batch.

After a stop, deployment or outage, run `python3 -m access_intake resume --db var/intake.sqlite`. Expired claims are recorded as interrupted and requeued from stored source/configuration snapshots. Completed work is retained. Leases default to 120 seconds with renewal at most every 10 seconds; a dead worker may require waiting for lease expiry. SIGINT stops new claims and allows current calls to finish; forced termination is recovered on resume. A remote request accepted just before a crash can be billed twice after recovery; local publication is guarded by claim tokens and desired source generation.

Errors have status `error`, owner `IT Service Desk`, next action `retry-extraction`, null extraction and a sanitized explanation. Inspect `show` and `history`, then copy the failed record's retry_command, or run:

```bash
python3 -m access_intake retry --db var/intake.sqlite --document-id IT-010.json --attempt-id 123
```

Replace 123 with the actual failed attempt ID. No automatic model retries occur. Refusal, malformed/truncated output, timeouts, HTTP errors and rate limits remain visible. A 429 establishes a shared cooldown (numeric Retry-After bounded to 300 seconds, default 30). Explicit retry creates a distinct attempt; successful attempts require `--force`. Stale-source retries are refused: inspect the desired source and refresh/reimport it. A failed retry stays current while earlier success remains in history. Correct unreadable/invalid exports and reimport them; unreadable files are reported without inventing a source hash. Duplicate basenames within a batch are rejected and other noncolliding inputs continue.

## Provider configuration, updates and shared operation

`config.mock.json` selects reproducible fixtures. Unknown mock source/configuration combinations fail visibly; the mock does not infer access facts or fall back to a real provider. `workload-manifest.json` explicitly binds source hashes to authored template parameters for the workload checks.

The implemented real provider is OpenAI Responses with strict structured output, using `config.example.json`. Its supported example model is `gpt-5.4-mini-2026-03-17`. Supply **API_KEY** only through the environment in your deployment/session settings; never put it in a file, command argument or log. Do not use a mock database to imply live results:

```bash
python3 -m access_intake intake materials/requests --db var/live.sqlite --config config.example.json
```

This command makes real provider calls and may incur cost. It is optional, requires account/model access, and was not run for the committed observations. Model, HTTPS endpoint, reasoning effort, output-token limit, timeout, worker count and request rate are configurable. The adapter disables redirect forwarding and hidden HTTP retries. Request evidence redacts authorization, labels capture-only examples, and records implemented refusal/completion/schema handling. Provider/model identity is recorded on real results; injected test transports are labeled mock. The API_KEY environment bridge is inspected statically in tests, not executed.

A later batch adds or updates documents; omission does not withdraw old requests. Original-byte changes create source revisions. Successful unchanged reruns reuse current results; failed attempts remain errors until explicit retry. Refresh source-derived results after changing model/request settings, prompt/schema contents or policy:

```bash
python3 -m access_intake refresh --db var/intake.sqlite --config config.mock.json
python3 -m access_intake refresh --db var/intake.sqlite --policy policy.example.json
```

The supported JSON policy option `staging_read_requires_security` can require risk review for otherwise complete staging/read requests. Default false implements the supplied office policy. Other policy extensions require code and source-grounded tests; the CLI does not interpret arbitrary new prose rules. Policy source bytes/options, prompt/schema bytes and effective extraction settings are fingerprinted. Changed policy re-extracts and reroutes affected records. Worker/rate/timeout knobs alone do not invalidate existing successful facts. Source versions, outcomes and producing settings are retained without automatic deletion; history is separate from current JSON outputs.

Regional operators must connect to a **single host** (for example through SSH) and use the same local database path. SQLite WAL supports readers during processing and serializes short write transactions; provider calls hold no database transaction. Claims and current-pointer publication use BEGIN IMMEDIATE, bounded busy handling and foreign keys. Global in-flight claims and request pacing are shared through the database. Different desired generations and lease tokens fence stale workers. Multiple hosts sharing the database over NFS/SMB are outside the supported deployment boundary. Use consistent worker/rate limits across operators. The ordinary 200–400-message day and 2,000-message burst are workload context, not an invented latency SLA.

Exports are static snapshots. A complete generation under `deliverables/.generations/` is selected by CURRENT; the live interface is the database CLI. Flat extraction/queue files share a manifest and export lock. Arbitrary readers can observe a flat pair mid-copy, so verify the manifest or read the selected complete generation; re-export repairs an interrupted copy. Final export refuses pending desired work. Runtime databases and source snapshots remain under `var/`; back them up using SQLite-aware tools rather than copying an open WAL database alone.

## Evidence and limits

`deliverables/accuracy.md` specifies the source-derived expectations for all 21 examples, exact-match denominators, factual discrepancies, purpose wording review and mock/provider origin. A mock's 252/252 field agreement proves fixture/pipeline consistency, not general extraction accuracy. Business-purpose wording differences require human factual review; the evaluator does not infer semantic equivalence. The request evidence example builds the implemented real-provider request without making a provider call and did not produce the mock extraction records.

`planning/sNN-tests-first.txt` and `planning/sNN-implementation.txt` retain step checks; earlier already-passing tests are not made to fail artificially. The operating-context tests cover partial visibility, overlapping processes, leases, late responses, retries and refreshes. The workload test measures 400/2,000 mock messages with two operators; its timings/configuration are in the saved run, not a live-provider throughput claim. Clean installation is checked offline with hashed local wheels. Provider availability, live accuracy, multi-host operation, arbitrary policy prose, power-loss durability and real-service rate behavior remain unverified. Final session-capture pairing, default-branch push and Classroom submission require the facilitator's external instructions; a local passing suite does not establish them.
