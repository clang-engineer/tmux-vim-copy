PYTHON ?= python3

.PHONY: test lint

test:
	$(PYTHON) -m unittest discover -s tests -v

lint:
	$(PYTHON) -c 'from pathlib import Path; paths = sorted(p for p in Path(".").rglob("*.py") if ".git" not in p.parts); [compile(p.read_bytes(), str(p), "exec") for p in paths]'
