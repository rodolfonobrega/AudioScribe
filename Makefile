# Makefile for AudioScribe

.PHONY: help install install-dev requirements test test-coverage test-unit test-integration lint format format-check mypy clean run run-timeout run-file docker-build docker-up docker-down build upload check all init example-config env-file docs version update-deps freeze electron-dev test-electron-e2e test-electron-physical-hotkey electron-build electron-build-win electron-build-mac electron-build-linux electron-package-engine electron-all

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

clean: ## Clean up build artifacts and temporary files
	@echo '$(BLUE)Cleaning up...$(NC)'
	python -c "import os, shutil; from pathlib import Path; root = Path('.'); [shutil.rmtree(d, ignore_errors=True) for d in [root/'build', root/'dist', root/'electron'/'dist', root/'electron'/'dist_old', root/'electron'/'bin', root/'tmp-audio-runtime', root/'scratch', root/'.pytest_cache', root/'.mypy_cache', root/'htmlcov'] if d.exists()]; [shutil.rmtree(p, ignore_errors=True) for p in root.glob('**/__pycache__')]; [os.remove(p) for ext in ['*.pyc', '*.pyo', '*.log', '*.tmp'] for p in root.glob(f'**/{ext}') if p.is_file()]"
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
	cp config/defaults.yaml config/defaults.example.yaml
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

# =================================================================
# Electron / Desktop App
# =================================================================

ELECTRON_DIR := electron
ENGINE_BIN := $(ELECTRON_DIR)/bin/audioscribe_engine.exe

electron-dev: ## Run Electron app in development mode (spawns python main.py)
	@echo '$(BLUE)Starting Electron app (dev mode)...$(NC)'
	cd $(ELECTRON_DIR) && npx electron .

test-electron-e2e: ## Run hermetic end-to-end Electron UI tests
	cd $(ELECTRON_DIR) && npm.cmd run test:e2e

test-electron-physical-hotkey: ## Inject F9 through the Windows native hotkey path
	cd $(ELECTRON_DIR) && npm.cmd run test:e2e:physical-hotkey

test-electron-hotkey: ## Test Electron hotkey & IPC in isolated standalone test script
	@echo '$(BLUE)Running standalone Electron hotkey test...$(NC)'
	npx electron standalone_tests/06_electron_hotkey_test.js

debug-keys: ## Run raw key event debugger to see exact key names pressed
	@echo '$(BLUE)Running raw key event debugger...$(NC)'
	python standalone_tests/debug_keys.py

test-ctrl-win: ## Test direct Ctrl+Win manual modifier tracking in Python
	@echo '$(BLUE)Running direct Ctrl+Win manual modifier tracker...$(NC)'
	python standalone_tests/test_ctrl_win_listener.py

interactive-test: ## Run interactive step-by-step test for Ctrl+Win hotkey + audio recording + STT transcription
	@echo '$(BLUE)Running interactive step-by-step hotkey and audio test...$(NC)'
	python standalone_tests/interactive_full_test.py

electron-package-engine: ## Build Python engine into standalone .exe (PyInstaller)
	@echo '$(BLUE)Packaging Python engine with scripts/build_engine.py...$(NC)'
	python scripts/build_engine.py
	@echo '$(GREEN)Engine packaged: $(ENGINE_BIN)$(NC)'


electron-build: electron-package-engine electron-build-win ## Build Electron app (default: Windows)

electron-build-win: ## Build Electron app for Windows (.exe installer)
	@echo '$(BLUE)Building Electron app for Windows...$(NC)'
	cd $(ELECTRON_DIR) && npx electron-builder --win --publish never
	@echo '$(GREEN)Windows build complete: $(ELECTRON_DIR)/dist/$(NC)'

electron-build-mac: ## Build Electron app for macOS (.dmg + .zip)
	@echo '$(BLUE)Building Electron app for macOS...$(NC)'
	cd $(ELECTRON_DIR) && npx electron-builder --mac --publish never
	@echo '$(GREEN)macOS build complete: $(ELECTRON_DIR)/dist/$(NC)'

electron-build-linux: ## Build Electron app for Linux (.AppImage + .tar.gz)
	@echo '$(BLUE)Building Electron app for Linux...$(NC)'
	cd $(ELECTRON_DIR) && npx electron-builder --linux --publish never
	@echo '$(GREEN)Linux build complete: $(ELECTRON_DIR)/dist/$(NC)'

electron-all: electron-build-win electron-build-mac electron-build-linux ## Build Electron app for all platforms
	@echo '$(GREEN)All platform builds complete$(NC)'

update-deps: ## Update dependencies
	@echo '$(BLUE)Updating dependencies...$(NC)'
	pip install --upgrade -r requirements.txt
	@echo '$(GREEN)✓ Dependencies updated$(NC)'

freeze: ## Freeze current dependencies
	@echo '$(BLUE)Freezing dependencies...$(NC)'
	pip freeze > requirements-freeze.txt
	@echo '$(GREEN)✓ Dependencies frozen to requirements-freeze.txt$(NC)'
