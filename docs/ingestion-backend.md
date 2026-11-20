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

    CI->>MW: POST /api/v1/ingest/runs<br/>(multipart: metadata + JUnit parts, Bearer repo token)
    MW->>MW: request_id, rate limit per token
    Note right of MW: 429 + Retry-After when over limit
    MW->>Auth: next

    Auth->>Auth: sha256(token) lookup, hmac.compare_digest
    Note right of Auth: request.state.repo = Repository
    Auth->>V: next

    V->>V: Stream parts, enforce size limits
    Note right of V: per part and total ≤ FQ_INGEST_MAX_UPLOAD_MB,<br/>gzip parts decompressed with a cap
    V->>V: Metadata → pydantic (extra=forbid)
    Note right of V: metadata.repository must equal token's repo (403)
    V->>M: next

    M->>M: Mask secrets in failure messages and stack traces
    Note right of M: masking_rules.yaml → [MASKED:type]
    M->>R: masked payload

    R->>DB: INSERT raw_uploads ON CONFLICT (idempotency key) DO NOTHING
    Note right of DB: key = repo, ci_system, run_id,<br/>run_attempt, shard, job_kind, framework
    DB-->>R: upload_id (new or existing)
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
| Middleware | Too many requests for this repo token | 429 |
| `require_repo_token` | Missing, malformed or unknown token | 401 |
| Validation | Metadata repository differs from the token's repository | 403 |
| Validation | Part or total size over limit, or decompressed size over cap | 413 |
| Validation | Metadata schema error, missing JUnit part, not XML / gzip | 400 |
| Route | Same idempotency key already stored | 202 with the first `upload_id` |
| Any | Unexpected error | 500, generic body, details in logs with `request_id` |

Parsing errors (bad XML structure, XXE attempts) are found by the worker, not the route: the upload is marked `failed` and `GET /api/v1/ingest/runs/{upload_id}` shows the summary.

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
        bigint repository_id FK
        jsonb metadata "validated"
        bytea payload "masked"
        text status "queued, parsed, failed"
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
