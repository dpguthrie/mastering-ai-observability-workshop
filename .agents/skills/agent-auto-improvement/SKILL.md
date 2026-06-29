---
description: 'Improve any Braintrust-instrumented agent by turning production traces into an offline eval loop: mine bad traces, build a failure taxonomy, capture cases in a remote Braintrust dataset, write scorers and an eval file, iterate on prompts/tools, and only then push online scorers. Use when the user wants to write evals for their agent, fix recurring production failures, or set up an auto-improvement loop for an LLM app.'
metadata:
    github-path: skills/agent-auto-improvement
    github-ref: refs/heads/main
    github-repo: https://github.com/braintrustdata/braintrust-skills
    github-tree-sha: 8d7b1ae3e5ba7b30894960a8d1c1270f9064af3d
name: agent-auto-improvement
---
# Agent auto-improvement with Braintrust evals

## Goal

Use real production traces to improve a specific behavior of an agent or LLM app. The source of truth is traced production data and a remote Braintrust dataset, not hand-written examples or hardcoded local JSON.

The loop is:

1. Pick one narrow, scoreable behavior to improve.
2. Inspect bad production traces.
3. Categorize what is wrong into a failure taxonomy.
4. Capture those cases in a remote Braintrust dataset.
5. Write scorers that codify the taxonomy.
6. Run an offline eval against the dataset.
7. Improve the system prompt, tool definitions, or runtime logic.
8. Rerun the eval and compare experiments.
9. Only after the offline loop is healthy, add online scorers and automations.

## Prerequisites

- The app is instrumented with the Braintrust SDK and logging traces to a project. If not, run `bt setup instrument` first.
- The `bt` CLI is installed and authenticated (`bt setup`, or `BRAINTRUST_API_KEY` in CI).
- SQL reference: `https://www.braintrust.dev/docs/reference/sql` (also prefetched at `.bt/skills/docs/reference/sql.md` if `bt setup skills` ran).

## Workflow

### 1. Pick the target behavior and verify context

Do not try to eval "the whole agent" at once. Pick one decision point that is observable in traces and cheap to replay offline, for example:

- the first tool call the agent makes for a request
- the arguments passed to one specific tool
- a routing or classification decision
- the final response for a single-turn task

Find where that behavior lives in the repo: the system prompt, the tool schema/description, and the runtime code that executes it. These are the files the loop will improve.

Then confirm `bt` points at the right org and project, and capture the project ID — SQL table functions like `project_logs(...)` require IDs, not names:

```bash
bt status --json
bt projects list --json
```

### 2. Inspect bad production traces

Start with trace-derived evidence, not prompt intuition. Query for failures with `bt sql`, scoped to the spans that capture the target behavior. Every query needs a time-range filter on `created` (the query linter blocks unscoped queries), and queries that project large fields like `input`/`output` need `LIMIT 100` or less:

```bash
# Errors on a specific tool's spans
bt sql "SELECT id, root_span_id, input, output, error \
  FROM project_logs('<project-id>') \
  WHERE created > now() - interval 30 day \
    AND span_attributes.name = '<tool-or-span-name>' AND error IS NOT NULL \
  LIMIT 100" --json

# Low-scoring or negative-feedback traces
bt sql "SELECT id, root_span_id, input, output, scores \
  FROM project_logs('<project-id>') \
  WHERE created > now() - interval 30 day AND scores['<score-name>'] < 0.5 \
  LIMIT 100" --json

# Slow spans (duration in seconds)
bt sql "SELECT id, root_span_id, metrics.duration AS duration \
  FROM project_logs('<project-id>') \
  WHERE created > now() - interval 30 day AND metrics.duration > 20 \
  ORDER BY duration DESC LIMIT 100" --json
```

If the project has no scores and the `error` field is never set, failures are usually latent in span contents instead: search tool span `output` payloads for failure signatures (non-zero exit codes, "not found", rejection messages), and look for behavioral patterns like retry loops, repeated identical calls, or a cheaper tool that should have been used. Aggregate by `span_attributes.name` first to see where the volume is.

Use `bt view trace --object-ref project_logs:<project-id> --trace-id <root-span-id>` to read full traces, and `bt view span --id <row-id>` for full payloads. Read enough individual failures to understand them concretely before generalizing.

### 3. Build a failure taxonomy

Group what you saw into named categories, and separate them into three buckets:

- **Hard failures** the system should prevent: wrong tool chosen, malformed or over-broad arguments, ignoring available context, violating an explicit instruction, wrong output format.
- **Soft inefficiencies** that are undesirable but not wrong: a working-but-wasteful query, an unnecessarily verbose answer, an avoidable retry.
- **Non-quality failures** to exclude: network errors, backend outages, upstream bugs. These are real but not fixable by prompt or tool changes.

Focus the loop on hard failures first. Write the taxonomy down (category id, description, how to detect it) — it becomes the spec for your scorers.

### 4. Capture cases in a remote dataset

Turn real failing traces into a remote dataset using a dataset pipeline. Each row should contain everything needed to replay the decision offline:

- `input`: the captured context at the decision point (prior messages, available state)
- `expected` (optional): a known-good output, if one exists
- `metadata`: the baseline production output and its failure categories, plus the source trace id

```typescript pipeline.ts
import { DatasetPipeline } from "braintrust";

DatasetPipeline({
  source: {
    projectName: "<project-name>",
    filter:
      "span_attributes.name = '<tool-or-span-name>' AND error IS NOT NULL",
    scope: "span",
  },
  transform: ({ id, input, output, metadata, trace }) => ({
    input,
    metadata: {
      source_span_id: id,
      baseline_output: output,
      baseline_categories: categorize(output),
    },
  }),
  target: {
    projectName: "<project-name>",
    datasetName: "<agent>-<behavior>-offline",
  },
});
```

```bash
bt datasets pipeline run ./pipeline.ts --limit 200 --window 30d
```

The pipeline runner needs `tsx` (or `vite-node`) installed as a local dev dependency for TypeScript pipelines; pass `--runner tsx` if auto-detection fails.

Implement `categorize` from the taxonomy in step 3 — it is shared between the pipeline and the scorers. Refresh the dataset (rerun the pipeline) whenever it feels stale, too small, or skewed toward one category. Then verify the dataset actually contains the failures you want to attack:

```bash
bt datasets view <agent>-<behavior>-offline --limit 50
bt sql "SELECT metadata.primary_category AS cat, count(1) AS n \
  FROM dataset('<dataset-id>') \
  WHERE created > now() - interval 1 day \
  GROUP BY cat ORDER BY n DESC" --json
```

### 5. Write scorers that codify the taxonomy

Prefer deterministic code scorers for hard categories — they are free, fast, and stable across runs. Use LLM-as-a-judge (e.g. from `autoevals`) only for qualities a deterministic check cannot capture, and keep judges few and focused.

The scorer set that makes this loop work:

- **Hard quality** (north star): binary, `1` only when the output has zero hard failure categories.
- **Issue count**: how many hard categories the output still triggers; gives gradient between 0 and 1.
- **Beats baseline**: whether the generated output has fewer issues than the captured production baseline in `metadata.baseline_output`.
- **Avoids primary issue**: whether the output avoids the case's main captured failure category.
- **Soft efficiency**: weighted `[0,1]` score over the soft-inefficiency categories.

```typescript scorers.ts
import { categorize, HARD_CATEGORIES } from "./categorize";

export function hardQuality({ output }) {
  const issues = categorize(output).filter((c) => HARD_CATEGORIES.has(c));
  return {
    name: "hard_quality",
    score: issues.length === 0 ? 1 : 0,
    metadata: { issues },
  };
}
```

Unit-test the categorizer against known-bad and known-good outputs before trusting eval scores built on it.

### 6. Write the offline eval

The task function replays the captured context against the current system and returns the target behavior's output (for tool-call behaviors, capture the first relevant tool call rather than running the tool):

```typescript first-step.eval.ts
import { Eval, initDataset } from "braintrust";
import {
  hardQuality,
  issueCount,
  beatsBaseline,
  softEfficiency,
} from "./scorers";

Eval("<project-name>", {
  experimentName: process.env.EVAL_EXPERIMENT,
  data: initDataset({
    project: "<project-name>",
    dataset: "<agent>-<behavior>-offline",
    useOutputAsExpected: false,
  }),
  task: async (input) => runAgentDecision(input),
  scores: [hardQuality, issueCount, beatsBaseline, softEfficiency],
});
```

`runAgentDecision` must call the same prompt, tools, and model configuration as production — import them from the app code rather than copying them, so prompt improvements are picked up automatically.

Two practical replay issues:

- Captured message histories often start mid-conversation. Normalize them before sending to the model: drop `tool_result` blocks whose matching `tool_use` was trimmed away, and start the history on a user message. Otherwise the provider API rejects the request.
- If no model provider key is available, route the task's LLM calls through the Braintrust AI proxy with `BRAINTRUST_API_KEY`.

### 7. Run the eval

Bounded smoke run first, full run once it is directionally better:

```bash
bt eval --first 20 first-step.eval.ts   # bounded, non-final
bt eval first-step.eval.ts              # full dataset, final
```

Note the experiment name printed in the summary, then resolve its ID — `experiment(...)` requires the ID, not the name:

```bash
bt experiments list --json
bt sql "SELECT root_span_id, scores \
  FROM experiment('<experiment-id>') \
  WHERE created > now() - interval 1 day \
    AND span_attributes.type = 'score' AND scores['hard_quality'] < 1" --json
```

### 8. Read the scores correctly

Priority order:

1. Keep the task producing the target behavior at all (it must not stop calling the tool, answering, etc.).
2. Reduce the hard issue count.
3. Raise the binary hard-quality rate.
4. Then tighten soft efficiency.

Do not trade away the hard score to optimize the soft score.

### 9. Improve the system, not the case

Prefer fixes that generalize across many traces:

- **System prompt**: tighten guidance for the target behavior; add concrete bad-vs-better examples drawn from real failures; resolve the ambiguities the taxonomy exposed.
- **Tool definitions**: improve tool descriptions, schemas, and parameter docs so the model cannot misread them.
- **Runtime**: validate, normalize, or reject bad outputs in code when the contract should be strict rather than suggested.
- **Categorizer/scorers**: keep them aligned with the guidance — when you add a prompt rule, add or adjust the category that detects violations of it.

If a fix only helps one or two dataset rows, it is overfitting; push on repeated categories instead.

### 10. Iterate

After every meaningful change:

1. Rerun the bounded eval.
2. Compare against the previous best experiment (the run summary shows the diff; the experiment comparison UI shows per-case regressions).
3. If directionally better, rerun the full dataset. The full dataset is the real check.

When new production failures appear later: refresh the dataset from the pipeline, rerun, keep iterating.

### 11. Graduate to online scoring

Only after the offline loop is healthy:

1. Push the same scorer logic as project scorers with `bt functions push`, keeping it aligned with the offline categorizer.
2. Configure online scoring or automations on production logs so regressions surface as scored traces.
3. Feed newly flagged traces back into the dataset via the pipeline.

Until then, the offline eval is the primary optimization surface.

## Guardrails

- Do not invent placeholder cases or fabricate expected outputs; every dataset row must come from a real trace or an explicitly user-provided example.
- Do not assume the current dataset is representative; inspect it and refresh it.
- Do not optimize around one or two traces. Push on repeated categories.
- Do not let scorer logic drift from prompt guidance — they encode the same contract.
- Do not eval against live mutable data as the primary loop; the remote dataset is the frozen surface.
- Do not start with LLM judges when a deterministic check exists for the same category.

## Expected outcome

A good iteration improves the target behavior across many real traced cases by:

- reducing hard failure categories
- increasing the clean-output rate
- beating the captured production baselines
- trimming soft inefficiencies without sacrificing hard quality

If a change improves the bounded run but regresses the full dataset, keep iterating — the full dataset is the real check.
