"""FastAPI application. Only ``/healthz`` until M0-06 adds the real skeleton."""

from fastapi import FastAPI

app = FastAPI(title="Flaky Test Quarantine")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
