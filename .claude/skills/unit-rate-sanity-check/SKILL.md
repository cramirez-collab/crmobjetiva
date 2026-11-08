---
name: unit-rate-sanity-check
description: "Revisa coherencia interna de precios unitarios, cantidades, unidades, rendimientos e indirectos. Úsala antes de emitir presupuesto; no estima precios de mercado."
---

# Unit rate sanity check

An estimate is nearly finished and you want a second pair of eyes on whether the rates and
quantities hang together — before the bid goes in, not after.

## Inputs to collect

Ask the user for any of these you do not already have. Never invent project facts, dates,
costs or clause references to fill a gap.

- `{{basis_notes}}`
- `{{labour_rates}}`
- `{{line_items_with_quantities_and_rates}}`
- `{{price_basis}}`
- `{{project_type}}`
- `{{region}}`

## Instructions

```text
You are a chief estimator reviewing a colleague's bid for {{project_type}} in
{{region}}.

The line items are:
{{line_items_with_quantities_and_rates}}

Basis of the estimate: {{basis_notes}}
Labour rates used: {{labour_rates}}
Price date and escalation assumption: {{price_basis}}

Review it for internal consistency only. Do not tell me whether the rates are market
correct in this region, because you cannot know that.

Instead tell me:
1. Any line where the quantity and the rate do not make sense together.
2. Any code or item that looks missing for this scope and project type.
3. Where the arithmetic is inconsistent between similar lines.
4. The three figures I should check against my own data before submitting.

Present findings as a table: line, what looks wrong, why, what to check.
```

## What good output looks like

- Catches missing scope and unit mismatches rather than inventing market prices.
- Flags its own uncertainty explicitly instead of sounding authoritative about your region.
- Produces a checklist you can run through in 20 minutes, with the owner named for each check.

## Follow-ups

- "Rank those findings by how much money they could move in either direction."
- "Draft the questions I should ask the estimator who prepared this."
- "Which of these would a competitor be most likely to catch, and use against us?"

## Guardrails

Never treat the model as a pricing service: it does not know current market rates, and it will
produce a confident number if asked. Keep bid pricing out of consumer tier tools, and verify every
quantity and rate against your own data before submission.

---

*Part of the construction agent skills library — CC BY 4.0. Verify anything that leaves your
company: a named person owns every output.*

---

Adaptación para Claude: conserva el flujo fuente y responde en el idioma del usuario. Skill original de Constructelligence; licencia CC BY 4.0. Fuente: https://github.com/constructelligence-lab/construction-agent-skills/tree/f05ffdf70b650582a4a12181d6fedcc9b3ae56f1/skills/unit-rate-sanity-check · Licencia: https://creativecommons.org/licenses/by/4.0/
