# Reference — config, flags, errors

Operational reference (on-demand). For design/internals see `README.md`; for
agent usage see `SKILL.md`.

## Config

Loaded from `config.json` (skill dir) or `~/.grok/config.json`:

```json
{ "api_key": "sk-...", "base_url": "https://host/proxy/grok",
  "verify_ssl": false, "disable_proxy": true,
  "concurrency": 5, "stagger_ms": 1000,
  "models": {
    "default": ["grok-4.3-high", "grok-4.20-multi-agent-low"],
    "deep":    ["grok-4.3-high", "grok-4.20-multi-agent-medium", "grok-4.20-multi-agent-low"],
    "degrade": "grok-4.3-high"
  } }
```

- `base_url` is auto-suffixed with `/v1`.
- `disable_proxy:true` — ignore HTTP(S)_PROXY env vars.
- `verify_ssl:false` — skip TLS verification (self-hosted proxies).
- `concurrency` — default global in-flight cap when CLI `--concurrency` is omitted.
- `stagger_ms` — delay between launching upstream requests; defaults to `1000` when effective concurrency is > 2, unless overridden to `0`.
- `models` — the tier ladder; `--model M` overrides it. Unknown fields ignored.

Validated models: `grok-4.3-*` = fast lane (~8-13s, cheap); multi-agent = more
depth/breadth. Avoid `multi-agent-xhigh` (slow, no gain), `0309-non-reasoning`
(~43s), `build`.

## All flags

| Flag | Effect |
|------|--------|
| `query` | one required query string; quote multi-word queries |
| `--deep` | breadth extraction + wider fanout |
| `--fanout N` | concurrent runs in consensus mode (default 2; `--deep` 3) |
| `--angle T` | distinct angle, repeatable; angle mode = base query + each angle |
| `--no-base-query` | in angle mode, skip the extra base query and run only explicit angles |
| `--days N` | recency window (from now) |
| `--focus T` | soft source/platform hint |
| `--sources-limit N` | max URLs printed (30) |
| `--concurrency N` | global in-flight cap (CLI overrides config; fallback 4) |
| `--stagger-ms N` | delay between launching upstream requests; auto-default `1000` when effective concurrency > 2 |
| `--deadline N` | wall-clock ceiling for the whole search, including degrade fallback (180) |
| `--model M` | force one model |
| `--verify-urls` | best-effort check of the final emitted URLs only (`live` / `dead` / `unverified`); shares the same deadline budget |
| `--json` | emit a minimal machine-readable wrapper instead of markdown |
| `--dump-raw FILE` | write raw responses |
| `--max-tokens N` | override per-tier token ceiling |

## Output signals

- `consensus: high` — strong overlap across successful runs
- `consensus: mixed` — partial overlap; inspect primary sources before concluding
- `consensus: low` — low overlap; treat as unresolved / fast-moving / branch-worthy
- URL status:
  - `live` — resolved successfully
  - `dead` — clearly broken / missing
  - `unverified` — not confirmed within the current budget; not the same as `dead`

## Minimal JSON shape

When `--json` is enabled, the script emits a script-owned wrapper with:

- `query`
- `tier`
- `summary`
- `runs.total`
- `runs.ok`
- `consensus.level`
- `consensus.divergence`
- `consensus.unique_sources`
- `consensus.multi_cited_sources`
- `sources[]` with `url`, `count`, `status`

## Errors

| Symptom | Meaning / action |
|---------|------------------|
| `❌ Grok config not found` | copy `config.json.example` → `config.json` |
| `· … retry` (stderr) | transient 429/5xx; auto-heals |
| `⚠️ --fanout is ignored in angle mode` | expected when `--angle` is present |
| `✗ <model>` in header | that run failed; answer still valid if ≥1 `✓` |
| `signal · consensus: ...` | overlap summary across successful runs |
| `· all runs failed; degrading…` | upstream overloaded; auto single-model retry |
| `❌ search failed after degrade` | upstream down or bad key — check connectivity / `api_key` |
| `⏱ run … exceeded deadline` | one run too slow; raise `--deadline` or ignore |
