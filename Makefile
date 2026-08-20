.PHONY: help install format lint check test test-coverage dev clean docker-up docker-down docker-logs docker-shell docker-restart

.DEFAULT_GOAL := help

VENV ?= .venv
PYTHON ?= python3
VENV_PYTHON := $(VENV)/bin/python
PIP ?= $(VENV_PYTHON) -m pip
PYTEST ?= $(VENV_PYTHON) -m pytest
RUFF ?= $(VENV_PYTHON) -m ruff
DOCKER_COMPOSE ?= docker compose
HA_SERVICE ?= homeassistant

help:
	@echo "SSD IMS - development commands"
	@echo ""
	@echo "Setup:"
	@echo "  install          Create .venv and install Python dependencies"
	@echo ""
	@echo "Quality:"
	@echo "  format           Format code with ruff"
	@echo "  lint             Run ruff checks"
	@echo "  check            Run formatting and lint checks (no auto-fix)"
	@echo "  test             Run test suite"
	@echo "  test-coverage    Run test suite with coverage report"
	@echo "  dev              Run format, lint and tests"
	@echo ""
	@echo "Docker:"
	@echo "  docker-up        Start Home Assistant container"
	@echo "  docker-down      Stop and remove containers"
	@echo "  docker-logs      Follow Home Assistant logs"
	@echo "  docker-shell     Open shell in Home Assistant container"
	@echo "  docker-restart   Restart Home Assistant container"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean            Remove caches and coverage files"

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

format:
	$(RUFF) format .

lint:
	$(RUFF) check . --fix

check:
	$(RUFF) format --check .
	$(RUFF) check .

test:
	$(PYTEST) tests/ -v --asyncio-mode=auto

test-coverage:
	$(PYTEST) tests/ -v --asyncio-mode=auto --cov=custom_components/ssd_ims --cov-report=term-missing --cov-report=html

dev: format lint test

docker-up:
	$(DOCKER_COMPOSE) up -d $(HA_SERVICE)

docker-down:
	$(DOCKER_COMPOSE) down

docker-logs:
	$(DOCKER_COMPOSE) logs -f $(HA_SERVICE)

docker-shell:
	$(DOCKER_COMPOSE) exec $(HA_SERVICE) /bin/sh

docker-restart:
	$(DOCKER_COMPOSE) restart $(HA_SERVICE)

clean:
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
