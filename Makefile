# Commands use the project environment and run from the repository root.
PYTHON := .venv/bin/python
.PHONY: setup api web bootstrap train test check types
setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt
	cd frontend && npm ci
api:
	.venv/bin/uvicorn hf_followup.api.main:app --app-dir src --reload --host 127.0.0.1
web:
	cd frontend && npm run dev
bootstrap:
	$(PYTHON) scripts/bootstrap_demo.py
train:
	$(PYTHON) scripts/train.py
test:
	$(PYTHON) -m pytest
check:
	.venv/bin/ruff check src scripts tests agent_starter.py
	$(PYTHON) -m pytest
	cd frontend && npm run check && npm run build
types:
	$(PYTHON) scripts/export_openapi.py
	cd frontend && npm run generate:types
