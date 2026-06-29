# Support Workflow Issue Facet

Create this as a Braintrust Topics custom facet from the UI, not with
`bt functions push`.

## Settings

- Name: `Support workflow issue`
- Description: `Extracts recurring support workflow, policy, data, and tool gaps from support traces.`
- Preprocessor: `Thread`
- Exclusion regex: `^NONE\.?$`
- Apply to existing traces: enable this when backfilling a recent simulator run

## Prompt

```text
Review this Trailhead Outfitters support conversation for one clear fixable customer-support workflow
issue that an operations or product team should track.

Your job is to output exactly one line:
- `NONE.`
- `<Short issue summary>. <1 sentence explanation>`

Do not force the output into a fixed taxonomy. Write the most specific recurring
workflow gap you can see in the conversation. Use concise phrases that could be
clustered with similar traces later, such as `Order lookup failure`,
`Unresolved carrier exception`, `Escalation lacks owner`, or
`Multi-issue context loss`.

Be highly selective. Most conversations should be `NONE.` A normal support task,
a normal policy explanation, a normal tool lookup, a standard eligibility
boundary, or an unsupported action that the assistant handles clearly is not a
workflow issue by itself.

Output an issue only when the conversation shows a concrete unresolved or
repeated gap that a team could plausibly improve through better tools, policies,
data, or agent instructions. The issue must be visible in the conversation, not
merely implied by the scenario.

Look for support issues such as:
- Tool/data failures where lookup, search, escalation, refund, return, shipment, or policy tools fail,
  return contradictory data, or cannot find records that should exist.
- Tool/data mismatch where tool results do not support the assistant's conclusion.
- Context loss across multiple customer issues or orders.
- Unresolved shipment exceptions where the assistant cannot summarize evidence, next owner, or next step.
- Escalation loops where the customer is asked to wait without a concrete next step, evidence summary,
  owner, or escalation path.
- Repeated customer friction caused by a missing workflow only when the assistant cannot offer a clear
  supported alternative, next step, or escalation.

Output `NONE.` when:
- The interaction is a normal resolved support request with no reusable workflow issue.
- The agent handles a return, refund, shipment, cancellation, or policy question cleanly with the
  available tools and gives a clear next step.
- The assistant clearly explains an expected unsupported action, standard identifier requirement,
  eligibility check, final-sale rule, hazmat/manual-review requirement, payment-hold state, account
  boundary, goodwill limit, or other normal policy/tool limitation.
- The customer asks for an exchange, replacement, reship, cancellation, address change, warranty repair,
  price match, coupon, payment change, subscription change, or account deletion, and the assistant
  clearly explains what it can do instead.
- The only signal is ordinary customer frustration without a support workflow, policy, data, or tool gap.
- The transcript is clipped, duplicated, or too ambiguous to identify one clear issue.
- The assistant already gives a clear next step and the remaining limitation is expected behavior.

Be conservative. Prefer `NONE.` over a weak label. Keep the explanation short,
factual, and privacy-preserving. Do not include names, order IDs, or customer IDs.
```
