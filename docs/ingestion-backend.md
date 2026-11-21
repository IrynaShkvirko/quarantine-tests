# CI Result Ingestion — Backend Flow (API → Database)

How one upload from a CI job becomes stored test results. Architecture: §8.1–8.3, §10, §13. Contract: `docs/contracts/ingestion.md`.

## Request Lifecycle

```mermaid
sequenceDiagram
    participant CI as fq-cli (CI job)
    participant MW as Middleware
    participant Auth as require_repo_token
    participant V as Upload validation
    participant M as Secret masking
    participant R as Ingestion route
    participant DB as PostgreSQL
    participant Q as Job queue

    CI->>MW: POST /api/v1/ingest/runs<br/>(multipart: metadata first, then JUnit parts, Bearer repo token)
    MW->>MW: request_id, rate limit per token, per-IP limit on bad tokens
    Note right of MW: 429 + Retry-After when over limit (before the body is read)
    MW->>Auth: next

    Auth->>Auth: sha256(token) lookup, hmac.compare_digest
    Note right of Auth: request.state.repo = Repository, else 401 + WWW-Authenticate
    Auth->>V: next

    V->>V: Read first part = metadata (≤ 64 KB, depth ≤ 2)
    V->>V: Metadata → pydantic (extra=forbid)
    Note right of V: metadata.repository must equal token's repo (403)
    V->>V: Stream JUnit parts, enforce size limits
    Note right of V: FQ_INGEST_MAX_PART_MB, FQ_INGEST_MAX_UPLOAD_MB,<br/>decompressed caps per part and total
    V->>M: next

    M->>M: defusedxml parse, mask decoded text and attributes, re-serialize
    Note right of M: masking_rules.yaml → [MASKED:type]<br/>parse fails → nothing stored, upload failed
    M->>R: masked payload

    R->>DB: INSERT raw_uploads ON CONFLICT (idempotency key)<br/>DO UPDATE duplicate_mismatches when payload_sha256 differs<br/>RETURNING upload_id, inserted flag
    Note right of DB: key = repo, ci_system, run_id,<br/>run_attempt, shard, job_kind, framework
    DB-->>R: first upload_id (new or existing)
    R->>Q: defer parse_upload(upload_id) if new
    R-->>CI: 202 { upload_id }
```

## Request Enrichment

```mermaid
flowchart LR
    A["Raw HTTP request"] -->|middleware| B["+ request_id"]
    B -->|require_repo_token| C["+ repository"]
    C -->|validation| D["Metadata model + bounded JUnit bytes"]
    D -->|masking| E["Masked payload"]
    E -->|route| F["raw_uploads row"]
    F -->|defer| G[("Procrastinate job")]
```

## Error Responses

| Step | Cause | Status |
|------|-------|--------|
| Middleware | Too many requests for this repo token, or too many bad-token requests from this IP (trusted ingress hop) | 429 |
| `require_repo_token` | Missing, malformed, unknown or revoked token | 401 with `WWW-Authenticate: Bearer` |
| Validation | Metadata repository differs from the token's repository | 403 |
| Validation | Metadata, part or total size over limit, or decompressed size over cap | 413 |
| Validation | Metadata not first, repeated, gzipped, too deep or schema error; missing JUnit part; too many parts; invalid gzip (malformed XML is not a 400; see below) | 400 |
| Masking | JUnit part cannot be parsed for masking | 202, upload `failed`, nothing from the part stored |
| Route | Same idempotency key already stored | 202 with the first `upload_id`; a different `payload_sha256` increments `duplicate_mismatches` and alerts |
| Any | Unexpected error | 500, generic body, details in logs with `request_id` |

Parsing errors (bad XML structure, XXE attempts) never give a 400: the masking parse or the worker marks the upload `failed` and `GET /api/v1/ingest/runs/{upload_id}` shows the summary.

## After the Response (worker)

```mermaid
flowchart TD
    J[parse_upload upload_id] --> P[defusedxml parse with limits]
    P -->|invalid| F[raw_uploads.status = failed + error summary]
    P --> N[Normalize per framework: test keys, attempts, tags, skips]
    N --> U[Upsert ci_run by repo + ci_system + run_id, merge shards]
    U --> T[Upsert tests, insert test_executions with run_attempt and attempt]
    T --> S[raw_uploads.status = parsed]
    S --> D[Enqueue detection: resolve_ownership → classify_run → detect_evidence]
```

## Stored Data

```mermaid
erDiagram
    REPOSITORIES ||--o{ RAW_UPLOADS : receives
    REPOSITORIES ||--o{ CI_RUNS : has
    REPOSITORIES ||--o{ TESTS : contains
    CI_RUNS ||--o{ TEST_EXECUTIONS : includes
    TESTS ||--o{ TEST_EXECUTIONS : has

    RAW_UPLOADS {
        bigint id PK
        uuid upload_id UK "random, exposed in the API"
        bigint repository_id FK
        jsonb metadata "validated"
        bytea payload "masked, null when failed before masking"
        text status "queued, parsed, failed"
        text error_summary "set when failed"
        text payload_sha256 "masked junit parts"
        int duplicate_mismatches
        timestamptz last_duplicate_mismatch_at
        timestamptz received_at
    }
    CI_RUNS {
        bigint id PK
        bigint repository_id FK
        text run_id "unique with repo and ci_system"
        text commit_sha
        text branch
        text event "push, pull_request, nightly, quarantine, stress"
        text environment
        boolean is_environmental
    }
    TESTS {
        bigint id PK
        bigint repository_id FK
        text test_key "unique per repository"
        text framework
        text level
        timestamptz last_seen_at
    }
    TEST_EXECUTIONS {
        bigint id PK
        bigint ci_run_id FK
        bigint test_id FK
        smallint run_attempt "CI re-run"
        smallint attempt "framework rerun"
        text outcome "passed, failed, error, skipped"
        int duration_ms
        text message_excerpt "masked"
        timestamptz executed_at "partition key"
    }
```
