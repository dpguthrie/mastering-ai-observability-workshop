# Workshop Guide

This is the public participant guide for the AI Evals World's Fair Mastering AI Observability workshop. The only companion doc is [SUPPORT_WORKFLOW_ISSUE_FACET.md](SUPPORT_WORKFLOW_ISSUE_FACET.md), which
contains the custom Topics facet prompt.

## 0. Prepare Braintrust

1. Create or open a Braintrust organization.
2. Create a project named `AIE-Workshop`.
3. Add an AI provider key in Braintrust settings.
4. Create a Braintrust API key for your `.env` file.

Keep API keys private. Do not paste keys into chat, slides, or committed files.

## 1. Install Locally

Clone the repo and install dependencies:

```bash
git clone https://github.com/braintrustdata/mastering-ai-observability-workshop
cd mastering-ai-observability-workshop
uv sync --extra dev
```

Create and edit your environment file:

```bash
cp .env.example .env
```

Set at least:

```bash
BRAINTRUST_API_KEY=<your Braintrust API key>
BRAINTRUST_ORG_NAME=<your Braintrust org>
BRAINTRUST_PROJECT=AIE-Workshop
AGENT_DEFAULT_MODEL=<model available through Braintrust Gateway>
```

The model must support tool/function calling. `ADDITIONAL_MODELS` is optional
and only populates the local chat UI model picker.

`JUDGE_MODEL` is optional. If it is blank, LLM judge scorers reuse
`AGENT_DEFAULT_MODEL`. If you have access to a second Gateway model, set
`JUDGE_MODEL` to use a different model for scoring than generation.

The `make` commands below are the shortest path. Direct commands are included
for shells that do not have `make`; if you use a different project name, replace
`AIE-Workshop` in the direct commands.

Install the Braintrust CLI:

**On Mac/Linux**:

```bash
curl -fsSL https://bt.dev/cli/install.sh | bash
```

**On Windows**:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://github.com/braintrustdata/bt/releases/latest/download/bt-installer.ps1 | iex"
```

Initialize the CLI:

```bash
bt init
```

Select the org and project you created above.

## 2. Verify Setup

Seed the local SQLite database:

```bash
make seed

# or the direct command
uv run python scripts/seed_db.py
```

Run deterministic tool checks:

```bash
make smoke

# or the direct command
uv run python scripts/smoke_tools.py
```

Run the full readiness check:

```bash
make ready

# or the direct command
uv run python scripts/check_ready.py
```

Expected result: required checks print `OK`. A model catalog warning can be
acceptable for custom providers, but the live agent tool smoke should pass
before the workshop flow.

## 3. Try The Chat UI

Start the local UI:

```bash
make chat-ui

# or the direct command
uv run python scripts/run_chat_ui.py
```

Open <http://127.0.0.1:8765>. Choose a seeded customer, choose a model, and ask
one support question.

## 4. Run Baseline Evals

Run the starter Braintrust eval:

```bash
make eval

# or the direct command
bt eval evals/eval_support_agent.py --no-input
```

The starter agent is expected to fail some cases. The goal is to establish a
baseline before using traces and Topics to find improvement candidates.

To compare a different model for one eval:

```bash
AGENT_DEFAULT_MODEL=gpt-4o bt eval evals/eval_support_agent.py --no-input
```

## 5. Configure Signal Generation

Topics and online scoring are two ways to generate signal from traces:

- Topics groups repeated patterns across many conversations.
- Online scoring attaches scorer outputs to traces so you can filter, review,
  and measure behavior over time.

### Topics Automation

Use the Braintrust UI for the first-time Topics setup so you can see exactly
what is being configured:

1. Open Braintrust Topics for your project.
2. Enable the built-in facets `Task`, `Sentiment`, and `Issues`.
3. Create a custom facet using
   [SUPPORT_WORKFLOW_ISSUE_FACET.md](SUPPORT_WORKFLOW_ISSUE_FACET.md).
4. Use the facet name `Support workflow issue` unless the facilitator gives you
   a different name.
5. Set the Topics scope to conversation-level grouping if available:
   group by `metadata.conversation_id`.
6. Enable backfill/apply-to-existing-traces when importing shared traces.

The Topics CLI path is useful after the custom facet exists, or when you want a
repeatable setup command. It configures a short `30s` idle time so imported
traces begin processing quickly during the workshop:

```bash
make configure-topics
```

Direct command for attendees without `make`:

```bash
bt topics config enable \
  --env-file .env \
  --project "AIE-Workshop" \
  --facet Task \
  --facet Sentiment \
  --facet Issues \
  --facet "Support workflow issue" \
  --idle-time 30s \
  --topic-window 24h \
  --generation-cadence 1h \
  --relabel-overlap 1h \
  --no-input
```

If your CLI session is not already scoped to the correct org, add
`--org "<your Braintrust org>"` to the command.

If your custom facet name differs:

```bash
make configure-topics TOPICS_SUPPORT_FACET="Support Workflow Issues"
```

### Scorer Definitions

Push the workshop scorer definitions into Braintrust:

```bash
make push-scorers
```

This creates four code-based scorers and two LLM judge scorers:

- `Tool calls succeeded`: production-log-safe, does not need `expected`
- `Required tools called`: eval-oriented, needs `expected.must_use`
- `Forbidden tools avoided`: eval-oriented, needs `expected.must_not_use`
- `Required evidence mentioned`: eval-oriented, needs `expected.must_mention`
- `Support resolution`: strict binary LLM judge with chain-of-thought enabled
- `Communication quality`: strict binary LLM judge with chain-of-thought enabled

Pushing scorers only creates the scorer definitions. It does not enable online
scoring automation.

The LLM judges follow the workshop best practices: binary PASS/FAIL scoring,
harsh rubrics, explicit few-shot examples, and an optional separate scoring
model via `JUDGE_MODEL`.

Direct scorer push command for Mac/Linux:

```bash
PYTHONPATH=.:src \
UV_CACHE_DIR=.uv-cache \
UV_PROJECT_ENVIRONMENT=.workshop_private/push-venv \
uv run --python 3.13 --extra dev bt functions push evals/braintrust_functions.py \
  --if-exists replace \
  --no-input \
  --env-file .env \
  --project "AIE-Workshop"
```

If your CLI session is not already scoped to the correct org, add
`--org "<your Braintrust org>"` to the `bt functions push` command.

PowerShell equivalent:

```powershell
$env:PYTHONPATH = ".;src"
$env:UV_CACHE_DIR = ".uv-cache"
$env:UV_PROJECT_ENVIRONMENT = ".workshop_private/push-venv"
uv run --python 3.13 --extra dev bt functions push evals/braintrust_functions.py --if-exists replace --no-input --env-file .env --project "AIE-Workshop"
```

### Online Scoring Automation

Configure online scoring automation in the Braintrust UI during the workshop so
attendees can see the selected scorers and sampling rate:

1. Open Automations.
2. Create an online scoring automation for project logs.
3. Select `Tool calls succeeded` for the first demo.
4. Choose the sampling rate and save the automation.

Use `100%` only for code-based scorers on the small workshop dataset. Keep LLM
judge sampling at `0%` until you intentionally want judges to run on new traces.
If `Support resolution` or `Communication quality` has a sampling rate above
`0%`, each sampled trace runs an LLM judge and can incur model compute cost.

Do not enable `Required tools called`, `Forbidden tools avoided`, or `Required
evidence mentioned` on raw production-like logs unless those traces include
expected behavior fields. They are primarily useful in evals and curated
datasets.

## 6. Import Shared Traces

The workshop uses a shared sanitized trace bundle so everyone starts from the
same production-like data. The bundle contains agent, model, and tool spans. It
does not include prior Topics automation spans, generated topic labels, scores,
or comments.

Import the bundle:

```bash
make import-sample-traces
```

Direct commands for Mac/Linux:

```bash
mkdir -p .workshop_private/imported-traces
curl -L "https://aiewf-braintrust-workshop-bucket.s3.us-east-1.amazonaws.com/workshop/aiewf-sample-traces.tar.gz" \
  -o .workshop_private/imported-traces/aiewf-sample-traces.tar.gz
tar -xzf .workshop_private/imported-traces/aiewf-sample-traces.tar.gz \
  -C .workshop_private/imported-traces
bt sync push "project_logs:AIE-Workshop" \
  --in ".workshop_private/imported-traces/aiewf-sample-traces/data" \
  --env-file .env \
  --project "AIE-Workshop" \
  --fresh \
  --no-input
```

If your CLI session is not already scoped to the correct org, add
`--org "<your Braintrust org>"` to the `bt sync push` command.

PowerShell equivalents:

```powershell
New-Item -ItemType Directory -Force .workshop_private/imported-traces
curl.exe -L "https://aiewf-braintrust-workshop-bucket.s3.us-east-1.amazonaws.com/workshop/aiewf-sample-traces.tar.gz" -o .workshop_private/imported-traces/aiewf-sample-traces.tar.gz
tar -xzf .workshop_private/imported-traces/aiewf-sample-traces.tar.gz -C .workshop_private/imported-traces
bt sync push "project_logs:AIE-Workshop" --in ".workshop_private/imported-traces/aiewf-sample-traces/data" --env-file .env --project "AIE-Workshop" --fresh --no-input
```

The default `TRACE_BUNDLE_URL` is set in `.env.example` and in the Makefile. If
the facilitator provides a replacement bundle, override it inline:

```bash
make import-sample-traces TRACE_BUNDLE_URL="<provided aiewf-sample-traces.tar.gz URL>"
```

The compressed download is about 2 MB. The uncompressed JSONL uploaded to
Braintrust is about 27 MB and contains roughly 1,000 traces.

After the push completes, open Braintrust Logs and confirm the imported traces
appear in your project.

## 7. Inspect Logs And Scores

In Braintrust Logs, open a representative trace and inspect:

- ordered conversation turns
- model calls
- tool calls and tool outputs
- metadata such as `conversation_id`, `customer_id`, `surface`, and `turn_count`
- scorer outputs if online scoring has been enabled

Useful CLI commands:

```bash
bt view logs --project "AIE-Workshop"
bt view logs --project "AIE-Workshop" --search refund
bt view trace --url "<trace-url>"
```

## 8. Use Topics And Scores

Open Topics and inspect the built-in facets plus the custom support workflow
facet. Look for repeated patterns such as:

- delayed shipment refund pressure
- final-sale return boundary
- manual-review risk boundary
- multi-issue context loss
- delivered-not-received evidence gap
- missing or insufficient support workflow

If online scoring is enabled, compare Topics with score signals. Topics help you
find clusters of behavior; scores help you filter for concrete pass/fail or
quality signals on individual traces.

Useful CLI commands:

```bash
bt topics status --project "AIE-Workshop"
bt topics poke --project "AIE-Workshop"
bt topics open --project "AIE-Workshop"
```

Pick one representative topic and state the improvement hypothesis in plain
English.

## 9. Turn A Pattern Into An Eval

Starter eval cases live in `evals/cases.jsonl`. Each row has the same top-level
shape as a Braintrust dataset row:

- `input`: the customer message, or an array of `{role, content}` messages
- `expected`: optional scorer expectations such as `must_use`, `must_not_use`,
  and `must_mention`
- `metadata`: execution and reporting context such as `customer_id`, `case_id`,
  and `quality_pattern`

For the local eval, `metadata.customer_id` selects the authenticated seeded
customer for the agent run.

The eval invokes scorers from `evals/scorers.py`:

- `required_tools_called`
- `forbidden_tools_avoided`
- `tool_calls_succeeded`
- `required_evidence_mentioned`
- `support_resolution`
- `communication_quality`

To promote a trace pattern into eval coverage:

1. Confirm the source trace is representative and not noise.
2. Write the expected tool-use requirements.
3. Decide which unsupported actions should be forbidden.
4. Add or update a case in `evals/cases.jsonl`.
5. Create the Braintrust dataset from the local cases:

```bash
make create-eval-dataset
```

This uses `bt datasets create` and does not require row ids. If you already
created the dataset during a dry run, use a different `EVAL_DATASET` name or
delete the old dataset first.

6. Add a custom scorer only if the scorers pushed in step 5 do not cover the
   behavior.
7. Rerun `make eval`.

## 10. Improve The Agent

Open `src/aiewf_support/agent.py`. Change only what the trace-backed hypothesis
justifies, then rerun:

```bash
make eval
```

Compare before/after scores and inspect at least one trace to make sure the
agent changed for the right reason.

## Optional: Generate Fresh Traces

The shared bundle is the recommended live workshop path. Generate fresh traces
only if the bundle is unavailable or you want extra local simulator data:

```bash
make traces
```

Useful simulator arguments:

```bash
uv run python scripts/run_production_sim.py --count 100 --max-turns 5 --concurrency 5
uv run python scripts/run_production_sim.py --help
```

## 11. Run The Automated Flywheel

Braintrust publishes an agent-auto-improvement skill for coding agents:

https://github.com/braintrustdata/braintrust-skills/tree/main

This is the culmination of the workshop. Everything above was the manual loop:
inspect traces, use Topics to find a repeated pattern, turn the pattern into
eval coverage, and make a narrow agent change. The automated flywheel asks a
coding agent to perform that same loop with the Braintrust skill as its
operating instructions.

Facilitator framing:

```text
We just walked the loop by hand. Now we are going to hand the loop to a coding
agent, but not as magic. The agent still has to ground itself in Braintrust
traces, create or update eval coverage, make a narrow change, and prove the
change with eval results.
```

Use the flywheel after you have at least one trace-backed improvement target
from Logs, Topics, or an eval failure. Do not ask the coding agent to improve
the whole app at once.

The skill repo is agent-agnostic: the same `SKILL.md` can be used by multiple
coding agents. Prefer a local project install during the workshop so attendees
can inspect or remove it later.

Shared install path:

```bash
git clone https://github.com/braintrustdata/braintrust-skills
cd braintrust-skills
./install.sh --link
```

For Codex, you can also use the Braintrust CLI helper:

```bash
bt setup skills --local --agent codex
```

For Claude Code, from the cloned `braintrust-skills` repo:

```bash
./install.sh --link --agent claude
```

Then invoke it directly if your Claude Code setup supports skill invocation:

```text
/agent-auto-improvement
```

For Cursor, install into `.agents/skills`, then add a Cursor rule that points at
the skill:

```md
Use the Braintrust agent-auto-improvement skill at:
.agents/skills/agent-auto-improvement/SKILL.md

When asked to improve this agent from traces, follow that skill before making
code or prompt changes.
```

For opencode, from the cloned `braintrust-skills` repo:

```bash
./install.sh --link --agent opencode
```

For Pi, use the same `.agents/skills` install path if Pi reads that directory.
If it does not, copy or reference this file in Pi's custom instructions or skill
mechanism:

```text
.agents/skills/agent-auto-improvement/SKILL.md
```

The important requirement is that the coding agent reads the Braintrust
agent-auto-improvement skill before it starts inspecting traces or changing
code.

If you want to give the coding agent a review queue, create draft dataset rows
from recent traces:

```bash
make draft-cases
```

This runs `pipelines/trace_to_eval_drafts.py`, which is a small Braintrust
dataset pipeline:

1. Source recent traces from the `AIE-Workshop` project.
2. Transform each trace into one draft dataset row with `input`, `expected`,
   and `metadata`.
3. Write the rows to the `support-flywheel-draft-cases` dataset.

These rows intentionally contain the visible conversation and empty
expected-behavior fields. They are starting points for review, not ground truth.

Useful overrides:

```bash
make draft-cases PIPELINE_LIMIT=25 PIPELINE_WINDOW=3d
make draft-cases DRAFT_DATASET="support-delay-draft-cases"
```

Use a narrow request that names the Braintrust project and the behavior to
improve:

```text
Use the Braintrust agent-auto-improvement skill to improve the support agent
from recent Braintrust traces.

Project: AIE-Workshop
Target behavior: shipment-delay support responses

Inspect recent traces, identify repeated failures, create or update focused eval
coverage, and propose the smallest prompt/tool/runtime change that improves the
eval. Do not promote raw production traces directly to ground truth; keep a
human review step for expected behavior.
```

The coding agent should produce a reviewable change, not just an explanation.
Watch for this sequence:

1. It confirms Braintrust access and the target project.
2. It inspects recent traces or Topics output for the target behavior.
3. It names the repeated failure pattern with trace evidence.
4. It adds or updates focused eval coverage.
5. It makes the smallest prompt, tool, or runtime change that addresses the
   pattern.
6. It reruns evals and summarizes before/after results.

Close the workshop by comparing the manual loop to the automated loop. The key
point is that automation speeds up the iteration, but the quality bar still
comes from trace evidence, reviewed expected behavior, and repeatable evals.
