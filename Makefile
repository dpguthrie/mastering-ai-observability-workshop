-include .env

BT_ORG ?= $(BRAINTRUST_ORG_NAME)
BT_ORG_FLAG = $(if $(BT_ORG),--org "$(BT_ORG)",)
BT_PROJECT ?= $(if $(BRAINTRUST_PROJECT),$(BRAINTRUST_PROJECT),AIE-Workshop)
TRACE_PULL_DIR ?=
TRACE_BUNDLE_URL ?= https://aiewf-braintrust-workshop-bucket.s3.us-east-1.amazonaws.com/workshop/aiewf-sample-traces.tar.gz
TRACE_BUNDLE_DIR ?= .workshop_private/aiewf-sample-traces
TRACE_BUNDLE_ARCHIVE ?= .workshop_private/aiewf-sample-traces.tar.gz
TRACE_IMPORT_DIR ?= .workshop_private/imported-traces
TRACE_IMPORT_NAME ?= aiewf-sample-traces
EVAL_DATASET ?= support-agent-eval-cases
DRAFT_DATASET ?= support-flywheel-draft-cases
PIPELINE_LIMIT ?= 50
PIPELINE_WINDOW ?= 24h
PIPELINE_SOURCE_FILTER ?=
PIPELINE_SOURCE_FILTER_FLAG = $(if $(PIPELINE_SOURCE_FILTER),--source-filter "$(PIPELINE_SOURCE_FILTER)",)
TOPICS_SUPPORT_FACET ?= Support workflow issue
TOPICS_IDLE_TIME ?= 30s
TOPICS_WINDOW ?= 24h
TOPICS_GENERATION_CADENCE ?= 1h

.PHONY: setup seed smoke ready ready-skip-model chat-ui eval eval-reviewed create-eval-dataset push-scorers draft-cases traces traces-reset configure-topics prepare-trace-bundle download-sample-traces import-sample-traces test lint clean

setup:
	uv sync --extra dev

seed:
	uv run python scripts/seed_db.py

smoke:
	uv run python scripts/smoke_tools.py

ready:
	uv run python scripts/check_ready.py

ready-skip-model:
	uv run python scripts/check_ready.py --skip-model

chat-ui:
	uv run python scripts/run_chat_ui.py

eval:
	EVAL_DATASET="$(EVAL_DATASET)" bt eval evals/eval_support_agent.py --no-input

eval-reviewed:
	AIEWF_EVAL_DATASET="$(DRAFT_DATASET)" AIEWF_EVAL_REVIEW_STATUS=approved bt eval evals/eval_support_agent.py --no-input

create-eval-dataset:
	bt datasets create "$(EVAL_DATASET)" --file evals/cases.jsonl --env-file .env $(BT_ORG_FLAG) --project "$(BT_PROJECT)" --no-input

push-scorers:
	uv run bt functions push evals/braintrust_functions.py --if-exists replace --no-input --env-file .env $(BT_ORG_FLAG)

draft-cases:
	bt datasets pipeline run pipelines/trace_to_eval_drafts.py --env-file .env $(BT_ORG_FLAG) --project "$(BT_PROJECT)" --source-project "$(BT_PROJECT)" --target-project "$(BT_PROJECT)" --target-dataset "$(DRAFT_DATASET)" --window "$(PIPELINE_WINDOW)" --limit "$(PIPELINE_LIMIT)" $(PIPELINE_SOURCE_FILTER_FLAG) --no-input

traces:
	uv run python scripts/run_production_sim.py

traces-reset:
	uv run python scripts/run_production_sim.py --reset-db

configure-topics:
	bt topics config enable --env-file .env $(BT_ORG_FLAG) --project "$(BT_PROJECT)" --facet Task --facet Sentiment --facet Issues --facet "$(TOPICS_SUPPORT_FACET)" --idle-time "$(TOPICS_IDLE_TIME)" --topic-window "$(TOPICS_WINDOW)" --generation-cadence "$(TOPICS_GENERATION_CADENCE)" --relabel-overlap 1h --no-input

prepare-trace-bundle:
	@test -n "$(TRACE_PULL_DIR)" || (echo 'Set TRACE_PULL_DIR to a bt sync pull output directory'; exit 2)
	uv run python scripts/prepare_trace_bundle.py --input "$(TRACE_PULL_DIR)" --output "$(TRACE_BUNDLE_DIR)" --archive "$(TRACE_BUNDLE_ARCHIVE)"

download-sample-traces:
	@test -n "$(TRACE_BUNDLE_URL)" || (echo 'Set TRACE_BUNDLE_URL to the hosted aiewf-sample-traces.tar.gz URL'; exit 2)
	rm -rf "$(TRACE_IMPORT_DIR)"
	mkdir -p "$(TRACE_IMPORT_DIR)"
	curl -L "$(TRACE_BUNDLE_URL)" -o "$(TRACE_IMPORT_DIR)/aiewf-sample-traces.tar.gz"
	tar -xzf "$(TRACE_IMPORT_DIR)/aiewf-sample-traces.tar.gz" -C "$(TRACE_IMPORT_DIR)"

import-sample-traces: download-sample-traces
	bt sync push "project_logs:$(BT_PROJECT)" --in "$(TRACE_IMPORT_DIR)/$(TRACE_IMPORT_NAME)/data" --env-file .env $(BT_ORG_FLAG) --project "$(BT_PROJECT)" --no-input

test:
	uv run pytest

lint:
	uv run ruff check .

clean:
	rm -f data/*.db .workshop_private/*.db exports/*.jsonl
	rm -rf evals/results
	rm -rf .bt evals/.bt .pytest_cache .ruff_cache src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
