# CI Result Ingestion Flow — CI Job to Database

End-to-end path of test results from a CI job to the database and dashboards. Architecture: §8.3, §9.1, §13. Backend detail: `docs/ingestion-backend.md`.

```mermaid
sequenceDiagram
    box rgb(230, 245, 255) CI job - GitHub Actions or Jenkins
        participant Run as Test runner<br/>(pytest / Playwright / Jest)
        participant Rep as Reporter plugin
        participant Cli as fq-cli
    end

    box rgb(255, 243, 224) Backend - FastAPI
        participant API as Ingestion API
        participant Mask as Masking
    end

    box rgb(232, 245, 233) Async processing
        participant Q as Job queue
        participant W as Worker
    end

    box rgb(243, 232, 255) Data
        participant DB as PostgreSQL
        participant G as Grafana
    end

    Cli->>Cli: fq fetch-quarantine<br/>(quarantine.yaml from default branch)
    alt Fetch fails
        Cli-->>Cli: Use backend last-known-good list, warn in job summary<br/>(never the PR checkout's copy); fail the job if unavailable
    end

    Run->>Run: Run tests except quarantined, up to 2 reruns
    Run->>Rep: Each attempt's result
    Rep->>Rep: Write JUnit XML with fq.test_key,<br/>fq.attempt, fq.tags properties

    Cli->>Cli: fq gate (failures minus the fetched quarantined list)
    Note right of Cli: Decides green / red build; needs the backend<br/>only when the git fetch of the list failed

    Cli->>API: fq upload: POST /api/v1/ingest/runs<br/>(metadata + JUnit, Bearer repo token)

    activate API
    API->>API: Verify repo token (hashed, constant time)
    alt Rate limited
        API-->>Cli: 429 + Retry-After
        Cli-->>Cli: Wait Retry-After, retry (counts toward the 3 retries)
    end
    alt Invalid token
        API-->>Cli: 401
        Cli-->>Cli: Warn, keep JUnit as CI artifact,<br/>build result unchanged
    end
    API->>API: Read metadata (first part), schema, compare repository with token
    alt Repository differs from token
        API-->>Cli: 403
        Cli-->>Cli: Warn, keep artifact, build unchanged
    end
    API->>API: Stream JUnit parts, check sizes and decompressed size
    alt Too large or invalid
        API-->>Cli: 413 / 400
        Cli-->>Cli: Warn, keep artifact, build unchanged
    end
    API->>Mask: Parse with defusedxml, mask decoded text
    Mask-->>API: [MASKED:type] replacements<br/>(parse fails: upload failed, nothing stored)
    API->>DB: INSERT raw_uploads (idempotent on repository, ci_system, run_id,<br/>run_attempt, shard, job_kind, framework)
    API->>Q: Defer parse_upload
    API-->>Cli: 202 { upload_id }
    deactivate API

    alt Network error or 5xx
        Cli->>API: Retry up to 3 times with backoff
        Note right of Cli: Upload never fails the build
    end

    Q->>W: parse_upload(upload_id)
    activate W
    W->>W: Parse XML safely (defusedxml, limits)
    alt Parse error
        W->>DB: raw_uploads.status = failed + summary
    end
    W->>W: Normalize: test keys, attempts, tags, skips
    W->>DB: Upsert ci_run (merge shards), tests, executions
    W->>Q: Enqueue detection (ownership → classify → evidence)
    deactivate W

    Q->>W: Detection tasks (M2)
    W->>DB: flaky_events, rates, shadow decisions
    G->>DB: Read reporting.* views
    G-->>G: Test inventory, Flaky tests, Shadow mode dashboards
```

## Key Properties

| Property | How it's guaranteed |
|----------|---------------------|
| CI depends on the backend only as a fallback | The gate runs locally from the default-branch `quarantine.yaml` fetched with git (never the PR checkout's copy). Only if that fetch fails does `fq` read the backend's last-known-good list, and the job fails if both are unavailable. Upload errors only warn |
| No duplicate data | Idempotency key on raw uploads; upserts on runs and tests |
| No secrets stored | Masking before any write, raw upload included |
| Safe parsing | `defusedxml`, size and decompression caps, parsing in the worker |
| Shards and re-runs | One `ci_run` per run ID; `run_attempt` stored per execution |
