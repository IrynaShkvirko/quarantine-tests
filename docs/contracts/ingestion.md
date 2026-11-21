# Ingestion contract

**Status: settled (M0-08, JUnit conventions finalized in M0-10).** Size and rate-limit numbers are proposed defaults to confirm in M1-01. The JUnit conventions table (§6) is final as of M0-10 (findings: `docs/spikes/rerun-attempts.md`).

Spec: `docs/architecture.md` §3.1–3.3, §8.1–8.2. Related: [ingestion-backend.md](../ingestion-backend.md), [ingestion-flow.md](../ingestion-flow.md).

**Source of truth.** This folder is the source of truth for the wire format. The FastAPI route built in M1-01 must produce the same schema, and M1-01's tests check the generated OpenAPI against `metadata.schema.json` and this document. If they disagree, fix the route, or change the contract here first.

Files in this folder:

| File | Purpose |
|------|---------|
| `ingestion.md` | This document |
| `metadata.schema.json` | JSON Schema (draft 2020-12) for the `metadata` part |
| `examples/metadata-*.json` | One metadata example per framework |
| `examples/junit-*.xml` | One JUnit example per framework: real output of the M0-10 spike reporters (`spikes/rerun-attempts/`) |

## 1. Request

```
POST /api/v1/ingest/runs
Authorization: Bearer <repo token>
Content-Type: multipart/form-data; boundary=...
```

One call per shard (§3.2). Parts:

| Part name | Count | Content type | Notes |
|-----------|-------|--------------|-------|
| `metadata` | exactly 1, **first part** | `application/json` | At most 64 KB, never gzipped. Validated against `metadata.schema.json` |
| `junit` | 1 to 20 | `application/xml` | One JUnit XML file per part |

Limits:

- Processing order: the token is checked from the header before the body is read (`401`, `429`). Then the `metadata` part is read (it must come first), checked for size and JSON depth, validated against the schema (`400`) and compared with the token's repository (`403`). Only then are `junit` parts streamed, decompressed and masked. A bad token or repository therefore never costs a JUnit read.
- Limits are enforced while streaming, and the upload is aborted at the first breach. A missing `Content-Length` does not skip them.
- Proposed defaults (all configurable through `FQ_*` settings; confirm in M1-01):

  | Limit | Setting | Default |
  |-------|---------|---------|
  | `metadata` part | `FQ_INGEST_MAX_METADATA_KB` | 64 KB, JSON nesting depth at most 2 |
  | Size of one `junit` part, as sent | `FQ_INGEST_MAX_PART_MB` | 20 MB |
  | Whole request | `FQ_INGEST_MAX_UPLOAD_MB` | 50 MB |
  | Decompressed size of one part | `FQ_INGEST_MAX_PART_DECOMPRESSED_MB` | 100 MB |
  | Decompressed size, all parts together | `FQ_INGEST_MAX_DECOMPRESSED_MB` | 200 MB |
  | `junit` parts per request | `FQ_INGEST_MAX_JUNIT_PARTS` | 20 |

- Gzip is allowed on `junit` parts only: set `Content-Encoding: gzip` on that part. A `Content-Encoding` on the `metadata` part is a `400`. Only a declared `gzip` is decompressed (no auto-detection, no other encodings). Exceeding a decompressed cap is a `413`; invalid gzip is a `400`.
- Unknown part names are ignored. A missing first `metadata` part, or a second one, is a `400`.
- A per-token budget on concurrent uploads or decompressed bytes is not part of this contract; M1-01 decides whether the request-count limits in §3a are enough.

Example (curl):

```bash
curl --fail-with-body --max-time 30 \
  -H "Authorization: Bearer $FQ_REPO_TOKEN" \
  -F 'metadata=@metadata.json;type=application/json' \
  -F 'junit=@junit.xml;type=application/xml' \
  https://fq.example.com/api/v1/ingest/runs
```

## 2. Responses

| Status | When | Body |
|--------|------|------|
| `202` | Accepted for processing, or a repeat of an earlier upload's idempotency key (returns the first `upload_id`; differing content is counted and alerted, see §3) | `{"upload_id": "<uuid>"}` |
| `400` | `metadata` is not the first part, is repeated, is gzipped or fails the schema or depth check; no `junit` part; too many `junit` parts; a part is not valid gzip. Malformed XML is **not** a `400`, see §4 | `{"problems": [{"part": "...", "path": "...", "message": "..."}]}` |
| `401` | Authentication problem with the token: missing, malformed or invalid (including a revoked or rotated-out token). Sent before the body is read | `{"detail": "unauthorized"}` plus `WWW-Authenticate: Bearer` |
| `403` | The token is valid but not permitted: `metadata.repository` differs from the token's repository. Checked before anything is stored or queued | `{"detail": "forbidden"}` |
| `413` | A part or the total is over the limit, or the decompressed size is over the cap | `{"detail": "payload too large", "limit": "part"}`; `limit` is `metadata`, `part`, `request`, `part_decompressed` or `decompressed`, never the configured value |
| `429` | Too many requests for this repo token (limits below) | `{"detail": "rate limited"}` plus header `Retry-After: <seconds>` |
| `409` | **Never returned.** Duplicates are accepted and ignored | n/a |

Examples:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"upload_id": "6f1c0d52-8a3e-4b7e-9a57-2f4b1f0f6a10"}
```

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "problems": [
    {"part": "metadata", "path": "/shard", "message": "does not match the required pattern"},
    {"part": "metadata", "path": "/commit_sha", "message": "does not match the required pattern"}
  ]
}
```

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"detail": "unauthorized"}
```

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"detail": "forbidden"}
```

```http
HTTP/1.1 413 Content Too Large
Content-Type: application/json

{"detail": "payload too large", "limit": "part_decompressed"}
```

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json

{"detail": "rate limited"}
```

Error bodies never echo the token, the `Authorization` header, submitted metadata values or text from the upload. Messages name the schema rule and the path only. FastAPI's default `422` validation response echoes the input, so M1-01 replaces it with this `400` body.

Client behavior (§8.3): an upload failure never fails the build. Retry up to 3 times with backoff, honor `Retry-After` on `429`, then warn and keep the JUnit file as a CI artifact. Do not retry `400`, `401`, `403` or `413`.

## 3. Idempotency

The key is:

```
(repository, ci_system, run_id, run_attempt, shard, job_kind, framework)
```

A second upload with the same key returns `202` with the **first** `upload_id`. The new payload is not stored or re-queued, even if its content differs (a differing payload is counted and alerted, see below).

Example: the same shard uploaded twice (for instance after a client retry whose first response was lost):

```
POST ... metadata: {repository: acme/shop-api, ci_system: github_actions, run_id: "11893422",
                    run_attempt: 2, shard: "2/4", job_kind: "blocking", framework: "pytest", ...}
→ 202 {"upload_id": "6f1c0d52-8a3e-4b7e-9a57-2f4b1f0f6a10"}

POST ... same key
→ 202 {"upload_id": "6f1c0d52-8a3e-4b7e-9a57-2f4b1f0f6a10"}
```

Any change to a key field is a different upload. For example `run_attempt: 3` (a CI re-run) or `shard: "3/4"` creates a new upload, and `job_kind: "quarantine"` for the same run does too.

`shard` is always sent. Unsharded jobs send `1/1`.

**Duplicates with different content raise an alert.** The backend stores `payload_sha256` with each upload: a SHA-256 over the masked, decompressed `junit` parts only, in part order. The `metadata` part is excluded, so a retry that regenerates timestamps is not a mismatch, and hashing after decompression means a retry that re-gzips the file (new gzip header time) is not one either. A duplicate whose hash differs from the first is still answered `202` with the first `upload_id` and its payload is not stored, but it also:

- increments `raw_uploads.duplicate_mismatches` and sets `last_duplicate_mismatch_at` on the first upload (spec §10);
- logs `ingest_duplicate_payload_mismatch` with `upload_id` and `repo` (never the content);
- increments the Prometheus counter `fq_ingest_duplicate_mismatch_total{repo}` for ops metrics.

The Grafana system-health alert (spec §12) reads the database column through a `reporting` view, so it works with Grafana's existing Postgres data source.

A duplicate with an identical hash is silent. Identical hashes are the normal client-retry case.

## 3a. Rate limits

Proposed defaults, per repo token unless noted, all configurable. Retry clients must honor `Retry-After`.

| Route | Limit | Why |
|-------|-------|-----|
| `POST /ingest/runs` | 120 requests/min, burst 40 | A run uploads once per shard, so a 20-shard run bursts 20 calls at once. 10/min would 429 normal runs |
| `GET /ingest/runs/{upload_id}` | 60 requests/min | Pollers check about once a second at most; status is cheap |
| Failed authentication (401) | 10 per minute per source IP | Slows token guessing. Per-token limits don't help here |

`429` is sent before the body is read.

The per-IP limit counts only requests with a bad token, and only those are refused once it is reached (with `429` instead of `401`). A request with a valid token is never refused by it, so a misbehaving job on a shared runner or Jenkins agent IP cannot lock other repos out. The source IP is taken only from the configured trusted ingress hop, never from a client-supplied `X-Forwarded-For`.

## 4. Status

```
GET /api/v1/ingest/runs/{upload_id}
Authorization: Bearer <repo token>
```

| Status | Meaning |
|--------|---------|
| `200` | Body below |
| `401` | Token authentication problem: missing, malformed or invalid. Includes `WWW-Authenticate: Bearer` |
| `429` | Rate limited (60/min per token, §3a), with `Retry-After` |
| `404` | Unknown `upload_id`, an `upload_id` that is not a UUID, or an upload that belongs to another repo. All return the same body, so ids can't be probed |

```json
{"upload_id": "6f1c0d52-8a3e-4b7e-9a57-2f4b1f0f6a10", "status": "queued", "error": null}
```

`upload_id` is a random UUID (v4) stored in `raw_uploads.upload_id`. The internal sequential `id` is never exposed.

`status` is one of:

| Value | Meaning |
|-------|---------|
| `queued` | Stored (masked), waiting for the worker |
| `parsed` | Normalized and merged into the run |
| `failed` | The upload could not be masked or parsed. `error` holds a short summary (`raw_uploads.error_summary`) |

```json
{"upload_id": "6f1c0d52-8a3e-4b7e-9a57-2f4b1f0f6a10", "status": "failed", "error": "junit part 1: not well-formed XML at line 12"}
```

`error` is `null` unless `status` is `failed`, and then holds a fixed-template summary (reason and line number only, never content from the file).

**Everything that is not a successfully parsed upload ends as `failed`.** Malformed XML, a DOCTYPE or entity (rejected by `defusedxml`), invalid UTF-8 or a document that is not JUnit all give `202` at upload time and `status: failed` here. The route returns `400` only for the problems listed in §2.

**Masking runs on decoded text.** XML escaping hides secrets from text rules (`password="x"` arrives as `password=&quot;x&quot;`, a PEM block in an attribute arrives with `&#10;` for newlines). So the route parses each `junit` part with `defusedxml` (DTDs forbidden, the size caps above) only to mask: it applies the rules to entity-decoded text and attribute values, then stores the re-serialized, masked XML. The worker does the full JUnit normalization later (§8.3). If that masking parse fails, the route cannot prove the content is masked, so it fails closed: nothing from the part is stored, the upload is recorded as `failed` with an error summary, and the response is still `202`.

## 5. Metadata

Defined by `metadata.schema.json`; field meanings are in §8.2 of the spec. Summary of the rules the schema enforces:

- Required: `repository`, `ci_system`, `pipeline`, `run_id`, `run_attempt`, `shard`, `job_kind`, `commit_sha`, `branch`, `event`, `environment`, `framework`, `started_at`, `finished_at`. Optional: `run_url`, `runner`.
- `ci_system`: `github_actions`, `jenkins`.
- `event`: `push`, `pull_request`, `nightly`, `quarantine`, `stress`.
- `job_kind`: `blocking`, `quarantine`, `stress`.
- `framework`: `pytest`, `playwright`, `jest`.
- `shard`: `^[1-9]\d{0,3}/[1-9]\d{0,3}$` (the server also checks index ≤ total). `commit_sha`: 7–40 hex characters. `started_at`, `finished_at`: RFC 3339.
- `run_id` is a string, `run_attempt` an integer starting at 1.
- String fields have length caps and reject control characters (C0, DEL, C1), line and paragraph separators and bidirectional-override characters; `run_url` must be `https://`; `run_attempt` is 1–1000.
- Unknown fields are rejected, so typos fail loudly instead of being dropped.

Note: the `format` keywords (`date-time`, `uri`) are annotations in draft 2020-12 unless the validator enables format checking. The timestamps also carry a `pattern`, so they are enforced either way; the backend should still enable format checking for `run_url`.

## 6. JUnit conventions

All three plugins must follow this table. The backend reads the `fq.*` properties first and falls back to the framework's own fields only where noted.

| Topic | Convention | Status |
|-------|-----------|--------|
| Test identity | Keep `classname` and `name` as the plugin writes them, and always write a `file` attribute (repo-relative, `/` separators); none of the three frameworks writes `file` in its native JUnit output. Add `<property name="fq.test_key" value="...">` with the full §3.1 key (`{framework}::{file_path}::{test_name}[{params}]`). The backend uses `fq.test_key` and never parses `classname`. Name parts in `fq.test_key`: pytest `Class::test[param]` (the `<testcase name>` is only `test[param]`, the class is in `classname`); Playwright and Jest `describe > describe > title`, joined with ` > `. | **Final** |
| Attempts | One `<testcase>` per attempt, each with `<property name="fq.attempt" value="N">` (1 = first try). A failed attempt carries its own `<failure message="...">`, so a flaky test is a failure on attempt 1 followed by a row with no failure. `time` is that attempt's own duration. A test that is not retried has one `<testcase>` with `fq.attempt` 1. Rows for different tests may interleave (Jest reruns failed tests after the rest of the block); a test's own attempts appear in increasing `fq.attempt` order, and the backend orders by `fq.attempt`, never by row position. Native rerun elements (`<rerunFailure>`, `<flakyFailure>`) are not used: none of the three frameworks writes them. | **Final** |
| Tags | `<property name="fq.tags" value="critical,demo_flaky">`: comma-separated, no spaces, no empty entries. Omit the property when there are no tags. | Final |
| Skips | `<skipped message="reason"/>` carrying the reason, plus `<property name="fq.skip_marker" value="skip">` where the value is one of `skip`, `xfail`, `fixme`, `it.skip`. Skips with no reason use an empty `message`. | Final |

Rules that apply to every row:

- Properties go in a `<properties>` element inside the `<testcase>`.
- `fq.*` property names are reserved. The backend ignores unknown `fq.*` names (forward compatibility) and warns on them.
- Skip markers per framework: pytest `skip`/`xfail`, Playwright `fixme`/`skip`, Jest `it.skip`/`skip`.
- `message` on `<failure>` and `<skipped>` is the first line of the error only, at most 1000 characters, with no environment, header or stack content. Assertion messages can contain repr'd local values, so the backend still masks, but plugins must not rely on that.
- Plugins write XML through one escaper that strips characters illegal in XML 1.0 (`\x00-\x08`, `\x0B`, `\x0C`, `\x0E-\x1F`, lone surrogates) and writes `\n`, `\r`, `\t` in attributes as numeric references. One illegal character makes the upload `failed` (§4), so the shard's results would be lost.
- `fq.test_key` is an opaque string of at most 1000 characters, scoped to the token's repository. Its framework prefix must equal `metadata.framework`. `fq.attempt` is a positive integer of at most 10.
- Failure and error text is masked by the backend at ingestion. Plugins must still not add secrets or environment dumps to messages.
- The XML is parsed by the worker with `defusedxml`. Any DOCTYPE or entity makes the upload `failed` (§4), not a `400`.

Decided in M0-10: one `<testcase>` per attempt with `fq.attempt`, for all three frameworks. Native output can't be used as is: pytest writes a row per attempt but leaves `<failure>` off the failed reruns, and Playwright and Jest collapse retries into one row. Each plugin therefore ships a reporter that writes this format. Edge cases and per-framework effort: `docs/spikes/rerun-attempts.md`. How the backend treats a row without `fq.attempt` (reject, or flag as "attempt data unavailable", never a first-try pass) is decided in M1 (spike edge case 1).

## 7. Examples

| Framework | Metadata | JUnit |
|-----------|----------|-------|
| pytest | [metadata-pytest.json](examples/metadata-pytest.json) | [junit-pytest.xml](examples/junit-pytest.xml) |
| Playwright | [metadata-playwright.json](examples/metadata-playwright.json) | [junit-playwright.xml](examples/junit-playwright.xml) |
| Jest | [metadata-jest.json](examples/metadata-jest.json) | [junit-jest.xml](examples/junit-jest.xml) |

The JUnit files are real output of the M0-10 spike reporters, for the same cases in each framework: a stable test, fails-then-passes, fails-twice-then-passes, always-fails, a parametrized flaky test and a nested test. They follow the §6 table. The sample projects have no tagged or skipped tests, so the tags and skips rows are not exercised here; M1-06, M5-01 and M5-02 add those cases to their plugin tests.
