# AI Evals World's Fair Support Flywheel

This repo is the local workshop app for building a trace-backed agent improvement
flywheel with Braintrust.

## Start Here

```bash
uv sync --extra dev
cp .env.example .env
uv run python scripts/seed_db.py
make ready
make chat-ui
```

Open <http://127.0.0.1:8765>.

Live model calls use Braintrust Gateway and require `BRAINTRUST_API_KEY` plus
`AGENT_DEFAULT_MODEL` in `.env`. Pick a Gateway-configured chat model that
supports tool/function calling; `make ready` runs a live support-agent tool-call
smoke before the workshop flow. `JUDGE_MODEL` is optional and falls back to
`AGENT_DEFAULT_MODEL`.

## Core Commands

```bash
make create-eval-dataset  # seed Braintrust eval dataset from evals/cases.jsonl
make eval              # run the eval from the Braintrust dataset
make configure-topics  # enable the workshop Topics facets
make push-scorers      # push hosted scorer definitions to Braintrust
make import-sample-traces  # import the shared sanitized trace bundle
make draft-cases       # optional: create review-draft dataset rows from traces
make ready             # check env, database, catalog hint, and live model tool calls
make ready-skip-model  # check local readiness without the live model call
make traces            # dynamically write production-like traces to Braintrust
make traces-reset      # reseed before writing production-like traces
make test              # unit and web smoke tests
```

The starter eval cases in `evals/cases.jsonl` use Braintrust dataset row shape:
`input`, optional `expected`, and `metadata`. `make eval` reads from the
Braintrust dataset named by `EVAL_DATASET`.

Seed data lives in `data/seed.json`. Eval and trace commands reuse an existing
valid local DB by default; use the reset commands when you want a clean seed.

To try a different model for one eval:

```bash
AGENT_DEFAULT_MODEL=gpt-4o bt eval evals/eval_support_agent.py --no-input
```

## Workshop Guide

- [WORKSHOP.md](WORKSHOP.md) is the single public workshop guide.
- [SUPPORT_WORKFLOW_ISSUE_FACET.md](SUPPORT_WORKFLOW_ISSUE_FACET.md) contains the custom Topics facet prompt.
