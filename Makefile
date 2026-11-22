.PHONY: setup lint typecheck test up down reset-db logs psql smoke integration

setup:
	uv sync --all-packages
	pnpm install
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .
	pnpm exec eslint .
	pnpm exec prettier --check .

typecheck:
	uv run mypy backend plugins/pytest-flaky-reporter ci/fq-cli
	pnpm -r typecheck

test:
	uv run pytest
	pnpm -r test

# Local environment (docker compose). Needs a .env: cp .env.example .env
up:
	docker compose up -d --build --wait
	@echo "api:     http://localhost:$${FQ_API_HOST_PORT:-8000}/healthz"
	@echo "grafana: http://localhost:$${GRAFANA_HOST_PORT:-3000}"

down:
	docker compose down

reset-db:
	docker compose down --volumes
	$(MAKE) up

logs:
	docker compose logs -f --tail=100

psql:
	docker compose exec db psql -U fq -d fq

smoke:
	scripts/dev-smoke.sh

# Integration tests against the running stack (`make up`); loads the host-side values from .env.
integration:
	set -a && . ./.env && set +a && uv run pytest -m integration
