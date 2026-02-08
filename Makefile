# Makefile for AudioScribe

.PHONY: help install install-dev test test-coverage lint format clean run build upload

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo '$(BLUE)AudioScribe - Available Commands$(NC)'
	@echo ''
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ''
	
install: ## Install the package
	@echo '$(BLUE)Installing AudioScribe...$(NC)'
	pip install -e .
	@echo '$(GREEN)✓ Installation complete$(NC)'

install-dev: ## Install development dependencies
	@echo '$(BLUE)Installing development dependencies...$(NC)'
	pip install -e ".[dev]"
	@echo '$(GREEN)✓ Development environment ready$(NC)'

requirements: ## Install requirements
	@echo '$(BLUE)Installing requirements...$(NC)'
	pip install -r requirements.txt
	@echo '$(GREEN)✓ Requirements installed$(NC)'

test: ## Run tests
	@echo '$(BLUE)Running tests...$(NC)'
	pytest tests/ -v
	@echo '$(GREEN)✓ Tests complete$(NC)'

test-coverage: ## Run tests with coverage report
	@echo '$(BLUE)Running tests with coverage...$(NC)'
	pytest tests/ --cov=core --cov-report=term-missing --cov-report=html
	@echo '$(GREEN)✓ Coverage report generated in htmlcov/$(NC)'

test-unit: ## Run unit tests only
	@echo '$(BLUE)Running unit tests...$(NC)'
	pytest tests/ -v -m "unit"

test-integration: ## Run integration tests only
	@echo '$(BLUE)Running integration tests...$(NC)'
	pytest tests/ -v -m "integration"

lint: ## Run linting
	@echo '$(BLUE)Running linting...$(NC)'
	flake8 core/ tests/ --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 core/ tests/ --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
	@echo '$(GREEN)✓ Linting complete$(NC)'

format: ## Format code with black and isort
	@echo '$(BLUE)Formatting code...$(NC)'
	black core/ tests/ --line-length=100
	isort core/ tests/ --profile=black
	@echo '$(GREEN)✓ Code formatted$(NC)'

format-check: ## Check code formatting
	@echo '$(BLUE)Checking code formatting...$(NC)'
	black --check core/ tests/ --line-length=100
	isort --check-only core/ tests/ --profile=black

mypy: ## Run type checking with mypy
	@echo '$(BLUE)Running type checking...$(NC)'
	mypy core/ tests/ --ignore-missing-imports
	@echo '$(GREEN)✓ Type checking complete$(NC)'

clean: ## Clean up build artifacts
	@echo '$(BLUE)Cleaning up...$(NC)'
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo '$(GREEN)✓ Cleanup complete$(NC)'

run: ## Run the transcriber with keyboard listener
	@echo '$(BLUE)Starting AudioScribe...$(NC)'
	python main.py
	
run-timeout: ## Run with timeout (5 seconds)
	@echo '$(BLUE)Starting AudioScribe (5s timeout)...$(NC)'
	python main.py --timeout 5

run-file: ## Transcribe a file (usage: make run-file FILE=path/to/file.wav)
	@echo '$(BLUE)Transcribing file: $(FILE)$(NC)'
	python main.py --file "$(FILE)"

run-example: ## Run example usage script
	@echo '$(BLUE)Running example usage...$(NC)'
	python example_usage.py

docker-build: ## Build Docker image
	@echo '$(BLUE)Building Docker image...$(NC)'
	docker-compose build
	@echo '$(GREEN)✓ Docker image built$(NC)'

docker-up: ## Start Docker container
	@echo '$(BLUE)Starting Docker container...$(NC)'
	docker-compose up

docker-down: ## Stop Docker container
	@echo '$(BLUE)Stopping Docker container...$(NC)'
	docker-compose down

docker-dev: ## Start development container
	@echo '$(BLUE)Starting development container...$(NC)'
	docker-compose -f docker-compose.yml --profile dev up

build: ## Build distribution packages
	@echo '$(BLUE)Building distribution packages...$(NC)'
	python -m build
	@echo '$(GREEN)✓ Build complete$(NC)'

upload: ## Upload to PyPI (make sure you have proper credentials)
	@echo '$(BLUE)Uploading to PyPI...$(NC)'
	python -m twine upload dist/*
	@echo '$(GREEN)✓ Upload complete$(NC)'

check: lint mypy test ## Run all checks (lint, mypy, test)

all: clean format lint mypy test ## Run everything: clean, format, lint, mypy, test

init: ## Initialize development environment
	@echo '$(BLUE)Initializing development environment...$(NC)'
	pip install -e ".[dev]"
	pre-commit install
	@echo '$(GREEN)✓ Development environment initialized$(NC)'

example-config: ## Create example config file
	@echo '$(BLUE)Creating example config.yaml...$(NC)'
	cp config/defaults.yaml config.yaml.example
	@echo '$(GREEN)✓ Example config created$(NC)'

env-file: ## Create .env file from example
	@echo '$(BLUE)Creating .env file...$(NC)'
	cp env.example .env
	@echo '$(YELLOW)⚠ Please edit .env with your API keys$(NC)'
	@echo '$(GREEN)✓ .env file created$(NC)'

docs: ## Generate documentation
	@echo '$(BLUE)Generating documentation...$(NC)'
	@echo '$(YELLOW)⚠ Sphinx documentation not set up yet$(NC)'

version: ## Show version information
	@echo '$(BLUE)AudioScribe v2.0.0$(NC)'
	@python --version
	@pip list | grep -E "(litellm|sounddevice|keyboard)"

update-deps: ## Update dependencies
	@echo '$(BLUE)Updating dependencies...$(NC)'
	pip install --upgrade -r requirements.txt
	@echo '$(GREEN)✓ Dependencies updated$(NC)'

freeze: ## Freeze current dependencies
	@echo '$(BLUE)Freezing dependencies...$(NC)'
	pip freeze > requirements-freeze.txt
	@echo '$(GREEN)✓ Dependencies frozen to requirements-freeze.txt$(NC)'
