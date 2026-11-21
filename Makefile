.PHONY: setup lint typecheck test up down

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

up:
	@echo "filled in by M0-05" && exit 1

down:
	@echo "filled in by M0-05" && exit 1
