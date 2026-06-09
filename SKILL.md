---
name: grok-search
description: "Web search via Grok. For current/post-cutoff info, multi-source synthesis, deep research, event tracking, comparisons."
---

# Grok Search

Use when the answer needs current web/X evidence, multi-source synthesis,
comparisons, event tracking, or deep technical research. Do not use for known
facts or for reading one known URL directly.

One call is a search primitive: fanout across models and/or evidence angles,
then return a compact answer plus consensus-ranked sources. The Agent owns
planning, pruning, follow-up reads, and synthesis.

## Run

```bash
cd /path/to/skills/grok-search
python3 scripts/grok_search.py "<query>" [options]
```

Common flags:

- `--deep` — 3-way breadth fanout
- `--preset comparison|controversy|recent-change|mechanism|deep-tech|tech-planning|discovery`
- `--angle "<text>"` — repeat for explicit evidence paths
- `--days N` — recency window
- `--focus "<text>"` — soft source/platform hint
- `--verify-urls` — best-effort final URL status
- `--json` — machine-readable wrapper; angle/preset mode includes `planned_angles`

Advanced research controls:

- `--no-base-query` — angle mode without the extra backbone query; good for discovery
- `--angle-fanout N` — extra passes per angle; use only for high-value manual batches

The script already does internal consensus sampling by default. External callers
usually do not need to set `--fanout`; prefer better query shaping, primary-source
focus, or evidence angles first.

Runtime/debug controls such as `--deadline`, `--concurrency`, `--stagger-ms`,
`--model`, `--max-tokens`, `--sources-limit`, and `--dump-raw` exist, but they
are not default planning tools. Use them only when the environment, debugging,
or a live evaluation requires them.

Hard CLI rules:

- Quote the main query.
- Default is 2-run consensus; do not tune sampling knobs unless evidence is too
  thin or the run is part of an evaluation.
- Use either `--preset` or explicit `--angle`, not both. If explicit `--angle`
  is present, the script ignores `--preset`.

Result handling rules:

- Treat stdout as the result channel. In `--json` mode, parse stdout as JSON.
- Treat stderr as diagnostics/progress. A `transient error ... retry` line is not
  a failed search if the command exits 0 and stdout contains a valid result.
- Do not switch to built-in fetch/search just because stderr contains retry,
  503, TLS fallback, or URL verification warnings.
- Fallback to another search tool only after a non-zero exit, empty/unparseable
  stdout, or a result with no successful runs and no usable sources.

See `README.md` for extended tactics and `references/api_reference.md` for the
full CLI contract.

## Choose Protocol

Start at the cheapest tier that can answer. Escalate only after evidence is too
thin, conflicted, or the user explicitly asks for depth.

- Fast: default 2-run consensus. Use for quick facts, official checks, and first
  passes.
- Balanced: one preset or 2-3 explicit angles, usually with `--no-base-query`
  for discovery. Use when the question has real evidence paths.
- Deep: add `--deep` only for landscape scans, branch drills after a weak first
  pass, or explicitly high-value deep research.

Scenario defaults:

- Official fact check: fast + `--focus "official docs"` + `--verify-urls`;
  avoid angles unless the fact has separate independent branches.
- Recent change: `--preset recent-change --days N`; do not add `--deep` on the
  first pass.
- Comparison: `--preset comparison` or explicit `A vs B`, `A limits`, `B limits`;
  keep head-to-head.
- Discovery: small explicit angle batches with `--no-base-query`; no `--deep`
  unless the first pass is too thin.
- Tech planning without internal context: explicit 4 external angles, batched
  1-2 at a time, with `--no-base-query`; no `--deep` on the first pass.

Preset rule: preset is a starting protocol, not an execution obligation. Preserve
the useful shape and judge evidence quality over source count. If pruning any
preset axis, switch from `--preset` to explicit `--angle` commands.

## Use Strategy

Search is a loop, not a one-shot report generator:

1. Start broad with one well-shaped query.
2. Split only when real evidence branches appear.
3. Drill into 2-4 branches; avoid spraying many near-duplicate angles.
4. Stop when primary sources settle the question.
5. Re-search only if the current evidence still cannot support the next decision.

## Angle Rules

- Make each angle self-contained.
- Keep comparison head-to-head: include one direct `A vs B` angle.
- Good angle sets are usually 2-4 paths; distrust 6+ unless manually batched.
- If angles return the same domains/claims, narrow the query.

Reliable patterns:

- Comparison: `A vs B direct`, `A limits`, `B limits`
- Recent change: `announcements`, `migration/breaking changes`, `incidents`
- Mechanism: `mechanism`, `counterexample`, `boundary conditions`
- Controversy: `best support`, `best critique`, `primary-source reality`
- Stakeholders: buyer, operator, regulator, independent reviewer

## Tech Planning

`--preset tech-planning` implements 5-look / 3-decide:

- Look: industry/trends, market/customers, competitors, self, opportunities
- Decide: target, strategy, control points / execution

Industry/trends should include technical signals: papers, patents, standards,
engineering blogs, official roadmaps, X experts, HN/community, regulation,
capital, ecosystem shifts.

Self axis rule:

- If internal context is provided, run self fit against that context only.
- If no internal context is provided, do not run self. Use explicit 4 angles:
  industry/trends, market/customers, competitors, opportunities. In synthesis,
  list missing self-fit questions instead.

For high-value planning, manually batch 1-2 angles at a time. Use
`--deep` or `--angle-fanout 2` only after the first pass proves too thin, or when
the user explicitly wants depth over speed.

## Deep Tech Insight

For a full technical read, use 4 evidence axes:

- Academic: papers, benchmarks, surveys, arXiv, paper-linked repos
- Industry: official docs, launch posts, engineering blogs, case studies, postmortems
- Social signal: X, HN, Reddit, practitioner disputes and links
- Adoption/reality: GitHub issues/PRs, RFCs/design docs, integration code,
  migration guides, examples, operator writeups, incidents

Social discovers signals; it does not conclude alone. Synthesize by decision
dimension: capability, reliability, operability, cost, ecosystem/adoption,
failure modes, open questions.

## Trust And Stop

`×N` is salience, not authority. Prefer primary, authoritative, fresh sources
over repeated secondary links.

- `consensus: high`: if a primary source exists, stop searching and read it.
- `consensus: mixed`: inspect primary sources before concluding.
- `consensus: low`: unresolved/fast-moving; split or narrow.
- Many `dead`/`unverified` URLs: narrow query/focus before spending more.
- Mostly `×1` with no primary source: tighten scope, do not add more angles.
- Social claims unsupported by academic/industry/adoption axes remain signals.
- Strong vendor narrative with weak GitHub/operator evidence is incomplete.

## Quality Check

For A/B or live evaluation, record objective and subjective quality:

- Objective: wall time, ok runs, retries/503, unique sources, multi-cited
  sources, primary-source count.
- Subjective: source authority, decision coverage, contradiction handling,
  noise, hallucination risk, and whether the answer supports the next Agent
  action.
