# AgentMesh developer commands.
.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help
help: ## Show this list
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[33m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: env
env: ## Create .env from the template if it does not exist
	@test -f .env || (cp .env.example .env && echo "Created .env - add your API keys.")

.PHONY: up
up: env ## Build and start the whole stack
	$(COMPOSE) up -d --build
	@echo "Waiting for the backend to report healthy..."
	@until curl -fsS http://localhost:8000/api/v1/health/live >/dev/null 2>&1; do sleep 2; done
	@$(MAKE) migrate
	@echo ""
	@echo "  UI          http://localhost:8080"
	@echo "  API docs    http://localhost:8000/docs"
	@echo "  MinIO       http://localhost:9001  (minioadmin / minioadmin)"

.PHONY: tools
tools: ## Start the optional tooling (Flower, OpenSearch Dashboards)
	$(COMPOSE) --profile tools up -d
	@echo "  Flower      http://localhost:5555"
	@echo "  Dashboards  http://localhost:5601"

.PHONY: down
down: ## Stop everything (volumes survive)
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop everything and delete the volumes
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail all logs
	$(COMPOSE) logs -f --tail=120

.PHONY: logs-worker
logs-worker: ## Tail the Celery worker
	$(COMPOSE) logs -f --tail=120 celery-worker

.PHONY: migrate
migrate: ## Apply database migrations
	$(COMPOSE) exec -T backend alembic upgrade head

.PHONY: revision
revision: ## Autogenerate a migration: make revision m="add x"
	$(COMPOSE) exec -T backend alembic revision --autogenerate -m "$(m)"

.PHONY: shell
shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend bash

.PHONY: psql
psql: ## Open psql against the app database
	$(COMPOSE) exec postgres psql -U agentmesh -d agentmesh

.PHONY: test
test: ## Run the backend test suite
	$(COMPOSE) exec -T backend python -m pytest -q

.PHONY: test-local
test-local: ## Run tests on the host (needs pip install -r backend/requirements-dev.txt)
	cd backend && python -m pytest -q

.PHONY: lint
lint: ## Ruff + format check
	cd backend && ruff check app tests && ruff format --check app tests

.PHONY: fmt
fmt: ## Autoformat
	cd backend && ruff check --fix app tests && ruff format app tests

.PHONY: seed
seed: ## Upload the sample document and index it
	bash scripts/seed.sh

.PHONY: smoke
smoke: ## End-to-end check against a running stack
	bash scripts/smoke.sh

.PHONY: reindex
reindex: ## Drop and recreate the OpenSearch indices (destructive)
	bash scripts/reindex.sh

.PHONY: scale-workers
scale-workers: ## Scale ingestion workers: make scale-workers n=4
	$(COMPOSE) up -d --scale celery-worker=$(or $(n),2)
