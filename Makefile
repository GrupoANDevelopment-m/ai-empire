# AI Empire — Makefile
# Common development tasks

.PHONY: help install test test-unit test-integration test-load lint format clean build push run chat ui status verify

help:
	@echo "AI Empire — Make targets:"
	@echo "  install         - Run ./install.sh"
	@echo "  test            - Run all tests"
	@echo "  test-unit       - Run unit tests only"
	@echo "  test-integration- Run integration tests"
	@echo "  test-load       - Run load tests"
	@echo "  lint            - Run linters (ruff, mypy, shellcheck)"
	@echo "  format          - Format code (black, isort)"
	@echo "  verify          - Verify all skills"
	@echo "  chat            - Start interactive chat"
	@echo "  ui              - Start web UI"
	@echo "  status          - Show system status"
	@echo "  clean           - Clean build artifacts"
	@echo "  build           - Build Docker images"
	@echo "  push            - Push to registry"
	@echo "  migrate         - Run DB migrations"
	@echo "  seed            - Seed DB with default data"

install:
	./install.sh

test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short

test-load:
	pytest tests/load/ -v --tb=short -s

lint:
	ruff check empire/ orchestrator/ web/ tests/
	mypy empire/ --ignore-missing-imports
	shellcheck scripts/*.sh

format:
	black empire/ orchestrator/ web/ tests/
	isort empire/ orchestrator/ web/ tests/

verify:
	./scripts/verify_skills.sh

chat:
	./empire chat

ui:
	./empire ui
	@echo "Open http://localhost:8080"

status:
	./empire status

migrate:
	cd db && alembic upgrade head

seed:
	psql "$$DATABASE_URL" -f db/seeds/initial_data.sql

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info

build:
	docker compose -f docker-compose.production.yml build

push:
	docker compose -f docker-compose.production.yml push
