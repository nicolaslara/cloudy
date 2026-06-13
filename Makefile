# cloudy — repo-level task runner. Each target delegates into backend/ (uv)
# or frontend/ (pnpm). POSIX make; no GNU-only features.

.PHONY: dev dev-backend dev-frontend db test test-e2e lint typecheck migrate create-db fmt check-length coverage ci

dev:
	@echo "Run in two terminals:"
	@echo "  make dev-backend   # FastAPI with reload (http://localhost:8400)"
	@echo "  make dev-frontend  # Vite dev server with /api proxy (http://localhost:5273)"
	@echo "First time: make db && make migrate"

dev-backend:
	cd backend && uv run cloudy serve --reload

dev-frontend:
	cd frontend && pnpm dev

db:
	docker compose up -d postgres

migrate:
	cd backend && uv run cloudy migrate

create-db: migrate  # deprecated alias

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

test-e2e:
	cd frontend && pnpm test:e2e

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && pnpm lint

typecheck:
	cd backend && uv run mypy .
	cd frontend && pnpm typecheck

fmt:
	cd backend && uv run ruff format .
	cd frontend && pnpm run --if-present format

check-length:
	sh scripts/check-file-length.sh

ci:  # run the GitHub Actions workflow locally (needs act + docker)
	act push --container-architecture linux/arm64

coverage:  # informational, no threshold (policy: WORKING.md Verification)
	cd backend && uv run pytest --cov=cloudy --cov-report=term-missing
	cd frontend && pnpm vitest run --coverage
