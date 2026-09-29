# Refundry
PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

.DEFAULT_GOAL := help

help:  ## list every target
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	 | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## create the venv and install everything
	python3 -m venv .venv
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements-dev.txt
	@test -f .env || cp .env.example .env
	@echo "installed. next:  make run"

seed:  ## reset the database
	$(PY) scripts/seed.py

run:  ## start all 15 services (7 MCP, 7 agents, 1 gateway)
	$(PY) scripts/run_all.py

demo:  ## file the sample claim; stops to ask you to approve
	$(PY) -m refundry.cli demo

demo-yes:  ## same, approving without prompting
	$(PY) -m refundry.cli demo --yes

trail:  ## replay the protocol traffic for the sample case
	$(PY) -m refundry.cli trail

cards:  ## every Agent Card and MCP server, as discovery returns them
	$(PY) -m refundry.cli cards

doctor:  ## check all fifteen services separately
	$(PY) -m refundry.cli doctor

jev:  ## what the System One layer decided, and how sure it was
	$(PY) -m refundry.cli jev

test:  ## unit tests, plus integration if the network is up
	$(PY) -m pytest

test-unit:  ## unit tests only, no network needed
	$(PY) -m pytest -m "not live"

lint:  ## ruff over the package
	.venv/bin/ruff check refundry scripts tests

fmt:  ## ruff --fix
	.venv/bin/ruff check --fix refundry scripts tests

clean:  ## drop the database and caches
	rm -rf data/*.db data/*.db-wal data/*.db-shm .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

.PHONY: help install seed run demo demo-yes trail cards doctor jev test test-unit lint fmt clean
