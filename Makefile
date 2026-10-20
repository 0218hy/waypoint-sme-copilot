# Waypoint: see README.md. Every target runs from the repo root.
PY      := .venv/bin/python
UV      ?= uv
NPM     ?= npm
PORT    ?= 8000
# .env (copied from .env.example) is read by serve, dev, demo and evidence; a variable already set in the shell
# wins. It goes through python-dotenv's CLI, already installed with uvicorn[standard].
DOTENV  := $(if $(wildcard .env),$(PY) -m dotenv -f .env run --no-override --,)

.PHONY: setup contracts web test test-all lint typecheck verify-log demo serve dev mailpit eval evidence data clean

setup:            ## Python deps (uv) + web deps (npm) + web build
	$(UV) sync
	cd web && $(NPM) ci && $(NPM) run build

contracts:        ## Regenerate widget JSON Schemas and TS types from agent/widgets.py
	$(PY) -m tools.export_contracts
	cd web && $(NPM) run contracts

web:              ## Build the web app into web/dist
	cd web && $(NPM) run build

test:             ## Python tests (fast) + web tests
	$(PY) -m pytest -m "not slow" -q
	cd web && $(NPM) run test -- --run

test-all:         ## Including slow tests
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check agent app tools rules sim mock_webank eval tests
	cd web && $(NPM) run lint

typecheck:        ## mypy --strict on tools and rules; mypy on agent and app; tsc on the web app
	$(PY) -m mypy
	$(PY) -m mypy agent app --ignore-missing-imports
	cd web && $(NPM) run typecheck

demo:             ## Seeded end-to-end run of the six demo moments (writes results/demo/)
	$(DOTENV) $(PY) -m sim.demo

serve:            ## Built web app + API at http://127.0.0.1:$(PORT) (another PORT needs WAYPOINT_BASE_URL to match); emails go to Mailpit if it's running
	$(DOTENV) $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port $(PORT)

dev:              ## API with reload + Vite dev server on 5173 (run `make mailpit` in another terminal)
	$(DOTENV) $(PY) -m uvicorn app.main:app --reload --host 127.0.0.1 --port $(PORT) & \
	cd web && $(NPM) run dev

mailpit:          ## Local Mailpit (SMTP 1025, inbox http://127.0.0.1:8025)
	docker run --rm -p 127.0.0.1:1025:1025 -p 127.0.0.1:8025:8025 axllent/mailpit:v1.31.6

eval:             ## Evaluations that can run without outside people or a model (writes results/)
	$(PY) -m eval.run_all

evidence:         ## eval + demo + audit verify, console output kept in results/logs/sandbox-run.log
	$(DOTENV) $(PY) -m eval.sandbox_log

data:             ## Re-fetch public data (data/public/SOURCES.md)
	$(PY) -m data.public.fetch

clean:
	rm -rf var .pytest_cache .mypy_cache .ruff_cache web/dist
