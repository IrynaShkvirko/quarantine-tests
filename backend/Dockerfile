# Build from the repo root: docker build -f backend/Dockerfile .
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv
# No bytecode compilation: it adds ~22 MB, and the image budget is 300 MB.
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# Only manifests: the dependency layer is cached until uv.lock or a pyproject changes.
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/
COPY plugins/pytest-flaky-reporter/pyproject.toml plugins/pytest-flaky-reporter/
COPY ci/fq-cli/pyproject.toml ci/fq-cli/
RUN uv sync --frozen --no-dev --package fq-backend --no-install-workspace

FROM python:3.12-slim AS runtime
RUN groupadd --system --gid 10001 fq \
    && useradd --system --uid 10001 --gid fq --no-create-home --shell /usr/sbin/nologin fq
COPY --from=builder /app/.venv /app/.venv
COPY backend/ /app/backend/
WORKDIR /app/backend
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER fq
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
ENTRYPOINT ["/app/backend/docker-entrypoint.sh"]
CMD ["api"]
