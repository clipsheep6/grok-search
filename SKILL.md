---
name: grok-search
description: "Web search via Grok. For current/post-cutoff info, multi-source synthesis, deep research, event tracking, comparisons."
---

# Grok Search

Concurrent Grok web search over a grok2api proxy. One call = one search
primitive: fanout across models and/or angles, then return a compact answer
plus consensus-ranked sources.

Use it for current info, multi-source synthesis, comparisons, landscape scans,
and deep technical research. Do not use it for things you already know or for
reading one known URL directly.

## Run

```bash
cd /path/to/skills/grok-search
python3 scripts/grok_search.py "<query>" [options]
```

Rules:

- The main query must be quoted.
- Multi-angle mode uses repeated `--angle`, not extra bare words.
- Default = 2 heterogeneous runs in parallel; most lookups should start there.
- If you raise effective concurrency above 2, the launcher now auto-staggers request starts unless you override it.

Core options:

- `--deep` — 3-way fanout + breadth prompt
- `--fanout N` — override consensus run count outside angle mode
- `--preset comparison|controversy|recent-change|mechanism|deep-tech|tech-planning|discovery` — expand a common protocol into angles
- `--angle "<text>"` — distinct evidence path; repeatable
- `--angle-fanout N` — run each angle with N model passes; use with manual batching for high-value research
- `--no-base-query` — in angle mode, run only explicit angles; useful for discovery sweeps
- `--days N` — relative recency window
- `--focus "<text>"` — soft source/platform hint
- `--verify-urls` — mark final URLs as `live`, `dead`, or `unverified`
- `--json` — minimal machine-readable wrapper for chaining
- `--concurrency N` — override in-flight cap; otherwise config/fallback decides it
- `--stagger-ms N` — override launch staggering; default auto-enables when concurrency > 2
- `--deadline N` — shared wall-clock budget for fanout, degrade, and URL checks; slow work may be dropped or skipped when budget is spent

See `README.md` for extended examples and `references/api_reference.md` for the
full CLI contract.

## Choose the lightest protocol

- **Quick lookup** — default consensus only
- **Verified lookup** — default + `--verify-urls`
- **Deep research** — `--deep`, optionally `--verify-urls`, prefer `--json` if another tool will continue
- **Preset research** — use `--preset` as a starting protocol for common comparison, controversy, recent-change, mechanism, deep-tech, tech-planning, or discovery work
- **Custom multi-angle research** — use explicit `--angle` when the preset does not fit, or when context lets you prune a preset safely
- **Discovery sweeps** — prefer multiple small calls over one giant angle batch; for angle sweeps, `--no-base-query` is often the right default

If the question is time-sensitive, add `--days N`. If domain authority matters,
add `--focus`.

Preset rule: do not run a preset mechanically when the user context makes one
axis irrelevant. Preserve the useful protocol shape, then prune or split it into
explicit `--angle` calls. Compare by evidence quality, not just source count.

## Angle rules

Angles decide quality. Use them to split **evidence paths**, not to restate the
same question.

- Each angle must be self-contained and carry all constraints.
- Comparison questions must keep one direct-comparison angle, not just `A` and `B`.
- Good angle sets are usually 3-way, not 6-way.
- If many angles collapse to the same domains/claims, the base query is too vague.

Reliable angle patterns:

- **Comparison** — `A vs B direct`, `A limits`, `B limits`
- **Recent changes** — `announcement`, `migration/breaking changes`, `incidents`
- **Mechanism** — `mechanism`, `counterexample`, `boundary conditions`
- **Controversy** — `best support`, `best critique`, `primary-source reality`
- **Stakeholders** — buyer / operator / regulator / independent reviewer

Use `--preset tech-planning` for 5-look / 3-decide technology strategy work:
industry/trends, market/customers, competitors, self, and opportunities. After
retrieval, synthesize into target, strategy, and control points / execution.
The industry/trends look should sample technical signal sources, not just macro
trend language: academic papers, patents, standards, industry engineering blogs,
official roadmaps, X.com top experts, Hacker News/community discussion,
regulation, capital, and ecosystem shifts. The self look must use only
user-provided internal context.

If no internal context is provided, do not run the self axis. Use four explicit
external angles instead: industry/trends, market/customers, competitors, and
opportunities. Then list the missing self-fit questions separately in synthesis.
For high-value planning, prefer manual batches with `--angle-fanout 2` over one
large run. Example: batch industry/trends + competitors, then market/customers +
opportunities, then self fit if internal context is available.

## Full-coverage deep tech insight

Use this when the goal is a deep read of one technology across the whole
evidence field. This is one protocol with four axes:

- **Academic** — papers, benchmarks, surveys, arXiv, paper-linked repos
- **Industry** — official docs, launch posts, engineering blogs, case studies, postmortems
- **Social signal** — X.com, Hacker News, Reddit, practitioner discussion
- **Adoption / reality** — GitHub issues/PRs, RFCs/design docs, integration code, migration guides, example apps, deploy notes, operator writeups, incident threads, repro repos

Use the social axis to discover signals and disputes, not to conclude on its
own. Use the adoption/reality axis to inspect the actual technical path, not
just buzz or ecosystem lists.

Recommended shape:

- Discovery pass = 2-4 explicit axes, often with `--no-base-query`
- Synthesis pass = add a base query only when a cross-axis backbone is useful
- Synthesize by decision dimension, not by source type

Default synthesis dimensions:

- `capability`
- `reliability`
- `operability`
- `cost`
- `ecosystem / adoption`
- `failure modes`
- `open questions`

Two common endgames:

- **Report mode** — keep breadth, contradictions, caveats, and source provenance
- **Action mode** — collapse evidence into `adopt / pilot / defer / avoid / monitor` decisions

## Trust and stop rules

`×N` means a URL was cited by N runs. It is a salience signal, not an authority
score. Always prioritize primary, authoritative, and fresh sources over raw `×N`.

Interpret signals this way:

- `consensus: high` — strong overlap; if a primary source exists, stop searching and read it directly
- `consensus: mixed` — useful result, but verify key URLs and check for missing primary sources
- `consensus: low` — unresolved / fast-moving / branch-worthy; do not collapse too early

Interpret URL status this way:

- `live` — resolved successfully
- `dead` — clearly broken
- `unverified` — not confirmed within budget; neither trust nor discard automatically

Escalate or stop:

- If many final URLs are `dead` or `unverified`, narrow the query/focus before spending more budget.
- If angle mode yields mostly `×1` URLs and no stable primary sources, tighten scope.
- If social claims do not survive academic / industry / adoption cross-checks, keep them as signals, not findings.
- If academic excitement is strong but adoption evidence is weak, label the technology frontier / emerging, not production-proven.
- If industry claims are strong but GitHub / operator / migration evidence is weak or negative, treat the vendor narrative as incomplete.

## Research loop

Use this loop for multi-step research:

1. **Broad** — start with one well-shaped query
2. **Split** — identify 2-4 real branches or evidence axes
3. **Drill** — run `--deep` or targeted angles per branch
4. **Cross-check** — prioritize primary/authoritative/fresh sources
5. **Synthesize** — report mode for completeness, action mode for technical direction

Typical task → protocol mapping:

- Official fact check → default + `--focus "official docs"` + `--verify-urls`
- Recent changes → default + `--days N`; add timeline angles only if one pass is too collapsed
- Comparison / vendor choice → base + one direct-comparison angle + 1-2 limits angles
- Unfamiliar landscape → broad first, then deep-drill top 2-4 branches
- Controversy / disagreement → support / critique / primary-reality angles
- Root cause / mechanism → mechanism / counterexample / boundary angles
- Full technical insight on one technology → academic / industry / social / adoption axes

Output is self-labeling. A `✗` or `M/N runs` line means partial failure: the
answer may still be useful, but coverage is thinner.

In `--json` angle or preset mode, `planned_angles` records the actual expanded
evidence paths, base-query policy, preset name, and per-angle fanout. Use it for
replay and A/B evaluation; do not treat it as an automatic research plan.

For A/B or live quality checks, judge both objective and subjective quality:
wall time, ok runs, retries, unique and multi-cited sources, primary-source
presence, decision coverage, noise, contradiction handling, and whether the
answer supports the next Agent action.
