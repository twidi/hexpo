PROJECT_NAME := "hexpo_game"
PROJECT_ROOT := "src/$(PROJECT_NAME)"

BOLD := \033[1m
RESET := \033[0m

default: help

.PHONY : help
help:  ## Show this help
	@echo "$(BOLD)$(PROJECT_NAME) project Makefile $(RESET)"
	@echo "Please use 'make $(BOLD)target$(RESET)' where $(BOLD)target$(RESET) is one of:"
	@grep -h ':\s\+##' Makefile | column -t -s# | awk -F ":" '{ print "  $(BOLD)" $$1 "$(RESET)" $$2 }'

.PHONY: install
install:  ## Install the project in the current environment, with its dependencies
	@echo "$(BOLD)Installing $(PROJECT_NAME)$(RESET)"
	@pip install .

.PHONY: dev
dev:  ## Install the project in the current environment, with its dependencies, including the ones needed in a development environment
	@echo "$(BOLD)Installing (or upgrading) $(PROJECT_NAME) in dev mode (with all dependencies)$(RESET)"
	@pip install --upgrade pip setuptools
	@pip install --upgrade --upgrade-strategy eager -e .[dev,lint,tests]
	@$(MAKE) full-clean

.PHONY: dist
dist:  ## Build the package
dist: clean
	@echo "$(BOLD)Building package$(RESET)"
	@python setup.py sdist bdist_wheel

.PHONY: clean
clean:  ## Clean python build related directories and files
	@echo "$(BOLD)Cleaning$(RESET)"
	@rm -rf build dist $(PROJECT_ROOT).egg-info

.PHONY: full-clean
full-clean:  ## Like "clean" but will clean some other generated directories or files
full-clean: clean
	@echo "$(BOLD)Full cleaning$(RESET)"
	find ./ -type d  \( -name '__pycache__' -or -name '.pytest_cache' -or -name '.mypy_cache'  \) -print0 | xargs -tr0 rm -r

.PHONY: tests test
test / tests:  ## Run tests for the whole project.
test: tests  # we allow "test" and "tests"
tests:
	@echo "$(BOLD)Running tests$(RESET)"
	@## we ignore error 5 from pytest meaning there is no test to run
	@pytest || ( ERR=$$?; if [ $${ERR} -eq 5 ]; then (exit 0); else (exit $${ERR}); fi )

.PHONY: tests-nocov
test-nocov / tests-nocov:  ## Run tests for the whole project without coverage.
test-nocov: tests-nocov  # we allow "test-nocov" and "tests-nocov"
tests-nocov:
	@echo "$(BOLD)Running tests (without coverage)$(RESET)"
	@## we ignore error 5 from pytest meaning there is no test to run
	@pytest --no-cov || ( ERR=$$?; if [ $${ERR} -eq 5 ]; then (exit 0); else (exit $${ERR}); fi )

.PHONY: lint
lint:  ## Run all linters (check-isort, check-black, mypy, flake8, pylint)
lint: check-isort check-black flake8 pylint mypy

.PHONY: check checks
check / checks:  ## Run all checkers (lint, tests)
check: checks
checks: lint tests

.PHONY: mypy
mypy:  ## Run the mypy tool
	@echo "$(BOLD)Running mypy$(RESET)"
	@mypy $(PROJECT_ROOT)

.PHONY: check-isort
check-isort:  ## Run the isort tool in check mode only (won't modify files)
	@echo "$(BOLD)Checking isort(RESET)"
	@isort $(PROJECT_ROOT) --check-only 2>&1

.PHONY: check-black
check-black:  ## Run the black tool in check mode only (won't modify files)
	@echo "$(BOLD)Checking black$(RESET)"
	@black --target-version py39 --check  $(PROJECT_ROOT) 2>&1

.PHONY: flake8
flake8:  ## Run the flake8 tool
	@echo "$(BOLD)Running flake8 in $(PROJECT_ROOT)$(RESET)"
	@flake8 $(PROJECT_ROOT)

.PHONY: pylint
pylint:  ## Run the pylint tool
	@echo "$(BOLD)Running pylint$(RESET)"
	@pylint $(PROJECT_ROOT)

.PHONY: pretty
pretty:  ## Run all code beautifiers (isort, black)
pretty: isort black

.PHONY: isort
isort:  ## Run the isort tool and update files that need to
	@echo "$(BOLD)Running isort$(RESET)"
	@isort $(PROJECT_ROOT) --atomic

.PHONY: black
black:  ## Run the black tool and update files that need to
	@echo "$(BOLD)Running black$(RESET)"
	@black --target-version py39 $(PROJECT_ROOT)
