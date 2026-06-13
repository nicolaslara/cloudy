# cloudy — repo-level task runner. Each target delegates into backend/ (uv)
# or frontend/ (pnpm). POSIX make; no GNU-only features.

.PHONY: dev dev-backend dev-frontend db test lint typecheck create-db fmt check-length

dev:
	@echo "Run in two terminals:"
	@echo "  make dev-backend   # FastAPI with reload (http://localhost:8400)"
	@echo "  make dev-frontend  # Vite dev server with /api proxy (http://localhost:5273/app/)"
	@echo "First time: make db && make create-db"

dev-backend:
	cd backend && uv run cloudy serve --reload

dev-frontend:
	cd frontend && pnpm dev

db:
	docker compose up -d postgres

create-db:
	cd backend && uv run cloudy create-db

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

lint:
	cd backend && uv run ruff check .
	cd frontend && pnpm lint

typecheck:
	cd backend && uv run mypy .
	cd frontend && pnpm typecheck

fmt:
	cd backend && uv run ruff format .
	cd frontend && pnpm run --if-present format

check-length:
	sh scripts/check-file-length.sh
