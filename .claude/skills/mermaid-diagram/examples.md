# Mermaid Examples — Flaky Test Quarantine System

Ready-to-use templates in the style of `docs/architecture.md`. Validate with `mmdc -i file.mmd -o file.svg` before committing.

---

## 1. Flowchart — CI pipeline with quarantine gate

```mermaid
flowchart TD
  A[Checkout commit] --> B[Fetch quarantine.yaml from default branch]
  B --> C[Run tests except quarantined, up to 2 reruns]
  C --> D{JUnit found and test count > 0?}
  D -- No --> X[Fail: runner crashed]
  D -- Yes --> E{Failures left after removing quarantined tests?}
  E -- No --> G([Build green])
  E -- Yes --> H([Build red])
  G --> U[Upload JUnit + metadata, always]
  H --> U
  X --> U
```

## 2. Sequence — ingestion and detection

```mermaid
sequenceDiagram
  autonumber
  participant CI as CI adapter
  participant API as Ingestion API
  participant DB as PostgreSQL
  participant W as Worker

  CI->>API: POST /api/v1/ingest/runs (repo token)
  API->>API: Verify token, validate, mask secrets
  API->>DB: INSERT raw_upload, enqueue parse job
  API-->>CI: 202 Accepted (upload_id)
  W->>DB: Dequeue parse job
  W->>W: Normalize JUnit, resolve owner and level
  W->>DB: Upsert tests, insert executions
  alt Fail and pass on same SHA + environment
    W->>DB: Insert flaky_event, recompute rate
  else Consistent result
    W->>DB: Update stats only
  end
```

## 3. Sequence — webhook with signature check

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant API as Webhook router
  participant Q as Job queue
  GH->>API: POST /api/v1/webhooks/github
  API->>API: HMAC check on raw body
  alt Signature invalid
    API-->>GH: 401
  else Valid
    API->>Q: Enqueue (dedupe on delivery ID)
    API-->>GH: 204
  end
```

## 4. State diagram — quarantine lifecycle (excerpt)

```mermaid
stateDiagram-v2
  [*] --> Healthy
  Healthy --> Candidate: threshold met
  Candidate --> PendingQuarantine: bot PR opened
  PendingQuarantine --> Quarantined: PR merged
  Quarantined --> Verifying: Jira Done and fix merged
  Verifying --> Quarantined: any failure
  Verifying --> Probation: all repetitions passed
  Probation --> Healthy: 7 clean days
  Probation --> Quarantined: flaky occurrence
```

## 5. ER diagram — core tables (excerpt)

```mermaid
erDiagram
  repositories ||--o{ tests : contains
  repositories ||--o{ ci_runs : has
  ci_runs ||--o{ test_executions : includes
  tests ||--o{ test_executions : has
  tests ||--o{ quarantine_records : has
  quarantine_records ||--o{ jira_issues : tracked_by

  tests {
    bigint id PK
    bigint repository_id FK
    text test_key "unique per repository"
    text level "unit, integration, api, e2e"
    text state
  }
  test_executions {
    bigint id PK
    bigint ci_run_id FK
    bigint test_id FK
    smallint run_attempt
    smallint attempt
    text outcome "passed, failed, error, skipped"
    timestamptz executed_at "partition key"
  }
```

## 6. Flowchart in C4 style — containers

Mermaid's native C4 renderer clips labels at this size; a styled flowchart reads better.

```mermaid
flowchart LR
  ci["Jenkins and GitHub Actions<br/>[External system]"]
  subgraph fqs["Flaky Test Quarantine System"]
    api["API service<br/>[FastAPI]"]
    worker["Worker<br/>[Procrastinate]"]
    db[("PostgreSQL")]
    grafana["Grafana"]
  end
  github["GitHub<br/>[External system]"]
  ci -->|"POST /ingest/runs"| api
  api --> db
  worker <--> db
  worker -->|bot PRs| github
  github -->|webhooks| api
  grafana -->|read-only views| db

  classDef ext fill:#999999,stroke:#6b6b6b,color:#fff
  classDef cont fill:#438dd5,stroke:#2e6295,color:#fff
  class ci,github ext
  class api,worker,db,grafana cont
```

## 7. Gantt — milestone plan

```mermaid
gantt
  dateFormat YYYY-MM-DD
  title Implementation milestones
  section Foundations
  M0 Foundations + spikes :m0, 2026-11-23, 10d
  section Build
  M1 Ingest and see       :m1, after m0, 9d
  M2 Detect (shadow)      :m2, after m1, 15d
  M3 Quarantine (enforce) :m3, after m2, 12d
```

## Tips

- One diagram, one idea. Split a 30-node flowchart into two.
- Label edges with the trigger or data, not "calls".
- Quote labels containing `()`, `:`, `/` or `#`.
- Keep architecture section numbers in the surrounding text so readers can cross-reference.
