PY ?= python
PYTHONPATH := src
export PYTHONPATH

.PHONY: help install test lint format build clean gen-ops check

help:
	@echo "make install   - editable install with dev extras"
	@echo "make test      - run unittest suite (no network)"
	@echo "make lint      - ruff check"
	@echo "make format    - ruff format"
	@echo "make build     - build sdist + wheel"
	@echo "make gen-ops   - regenerate src/alimail/operations.json from official docs"
	@echo "make check     - live read-only permission self check (needs credentials)"
	@echo "make clean     - remove build artefacts and caches"

install:
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m unittest discover -s tests -v

lint:
	$(PY) -m ruff check .

format:
	$(PY) -m ruff format .

build: clean
	$(PY) -m build

gen-ops:
	$(PY) scripts/gen_operations.py

check:
	$(PY) -m alimail check

clean:
	rm -rf build dist .pytest_cache .ruff_cache
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
