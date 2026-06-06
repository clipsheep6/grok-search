#!/usr/bin/env python3
"""
grok-search — concurrent, consensus-ranked web search over a grok2api reverse
proxy (Grok web-chat behavior; NOT the official xAI API).

Design:
- Backend abstraction with a ProxyBackend (grok2api reverse proxy).
- Default tier = heterogeneous 2x concurrent + consensus (fast+accurate).
- --deep = breadth-extraction prompt + heterogeneous fanout + consensus.
- Mechanism lives here; multi-step research STRATEGY lives in SKILL/agent.
- Cost model: we pay in wall-clock TIME and in the payload returned to the
  caller. So: run concurrent, keep the return small (asymmetric output
  discipline: cut prose, never trim the source list).
"""

import argparse
import functools
import json
import random
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import requests
import urllib3


# --- Resilience constants (burst test: 6 concurrent OK against the proxy) ----
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
DEFAULT_RETRIES = 2
RETRY_BASE_DELAY = 2.0
DEFAULT_CONCURRENCY = 4          # fallback global in-flight cap; override via config/CLI
DEFAULT_STAGGER_MS_HIGH_CONCURRENCY = 1000
DEFAULT_DEADLINE = 180           # wall-clock ceiling for a fanout (seconds); now enforced per-request
PER_CALL_TIMEOUT = 300           # read timeout per call when no deadline is active
CONNECT_TIMEOUT = 10             # TCP connect timeout (seconds)

# --- Model tier ladder (overridable via config "models") ---------------------
# Validated live: grok-4.3-* are the fast lane (~8-13s, cheap); multi-agent adds
# depth/breadth; xhigh / non-reasoning / build are excluded as slow / no gain.
DEFAULT_MODELS = {
    'default': ['grok-4.3-high', 'grok-4.20-multi-agent-low'],
    'deep': ['grok-4.3-high', 'grok-4.20-multi-agent-medium', 'grok-4.20-multi-agent-low'],
    'degrade': 'grok-4.3-high',
}
# Higher rank => preferred as the "primary answer" run when several succeed.
PRIMARY_RANK = {
    'grok-4.20-multi-agent-medium': 4,
    'grok-4.20-multi-agent-low': 3,
    'grok-4.20-multi-agent-high': 3,
    'grok-4.3-high': 2,
    'grok-4.3-low': 1,
}

_CONCURRENCY_SEMAPHORE: Optional[threading.Semaphore] = None


# ============================================================================
# Helpers (config, parsing, extraction) — preserved from the validated engine
# ============================================================================

def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _coerce_positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            parsed = int(value)
            return parsed if parsed > 0 else None
    return None


def _normalize_base_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        return f"{base_url}/v1"
    return base_url


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        resp = exc.response
        return resp is not None and resp.status_code in RETRYABLE_STATUS
    return isinstance(exc, (requests.ConnectionError, requests.Timeout))


def _retry_after_seconds(exc: Exception) -> Optional[float]:
    """Parse a Retry-After header (delta-seconds or RFC-1123 date) if present."""
    if not isinstance(exc, requests.HTTPError) or exc.response is None:
        return None
    raw = exc.response.headers.get('Retry-After')
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return float(raw)
    try:
        from email.utils import parsedate_to_datetime
        when = parsedate_to_datetime(raw)
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None
    return None


def _local_now() -> datetime:
    try:
        return datetime.now().astimezone()
    except Exception:
        return datetime.now(timezone.utc)


def _local_time_context() -> str:
    now = _local_now()
    return (
        f"[Current Time Context]\n"
        f"- Date: {now.strftime('%Y-%m-%d')}\n"
        f"- Time: {now.strftime('%H:%M:%S')}"
    )


def _days_to_window(days: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    """Turn a recency duration into a (from_date, to_date) pair anchored at now."""
    if not days or days <= 0:
        return None, None
    now = _local_now()
    return (now - timedelta(days=days)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'invalid int value: {value!r}') from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError('must be > 0')
    return parsed


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'invalid int value: {value!r}') from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError('must be >= 0')
    return parsed


_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)
_URL_RE = re.compile(r'https?://[^\s\]>\)\"]+')
_MD_URL_RE = re.compile(r'\[([^\]]+)\]\((https?://[^)]+)\)')
_URL_STATUS_LIVE = 'live'
_URL_STATUS_DEAD = 'dead'
_URL_STATUS_UNVERIFIED = 'unverified'


def _strip_thinking(text: str) -> str:
    if not text:
        return text
    return _THINK_RE.sub('', text).strip()


def _extract_urls_from_text(text: str) -> List[str]:
    if not text:
        return []
    urls: Set[str] = set()
    for url in _URL_RE.findall(text):
        urls.add(url.rstrip('.,;:'))
    for _, url in _MD_URL_RE.findall(text):
        urls.add(url.rstrip('.,;:'))
    return sorted(urls)


def _collect_urls(value: Any) -> List[str]:
    urls: Set[str] = set()
    if isinstance(value, str):
        urls.update(_extract_urls_from_text(value))
    elif isinstance(value, list):
        for item in value:
            urls.update(_collect_urls(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and 'url' in key.lower() and isinstance(item, str):
                urls.add(item.rstrip('.,;:'))
            urls.update(_collect_urls(item))
    return sorted(urls)


def _collect_search_sources(value: Any) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []

    def walk(node: Any, path: str = 'root') -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                next_path = f'{path}.{key}'
                if key == 'search_sources':
                    if isinstance(item, list):
                        for idx, source in enumerate(item):
                            if isinstance(source, dict):
                                source = dict(source)
                                source.setdefault('_path', f'{next_path}[{idx}]')
                                found.append(source)
                    elif isinstance(item, dict):
                        source = dict(item)
                        source.setdefault('_path', next_path)
                        found.append(source)
                walk(item, next_path)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                walk(item, f'{path}[{idx}]')

    walk(value)
    return found


def _deadline_remaining(deadline_ts: Optional[float]) -> Optional[float]:
    if deadline_ts is None:
        return None
    return max(0.0, deadline_ts - time.time())


def _consensus_signal(merged: Dict[str, Any]) -> Dict[str, Any]:
    consensus = merged.get('consensus') or []
    unique_sources = len(consensus)
    multi_cited_sources = sum(1 for _, count in consensus if count >= 2)
    ok_runs = merged.get('ok_runs', 0)
    share = (multi_cited_sources / unique_sources) if unique_sources else 0.0

    if ok_runs <= 1 or unique_sources == 0:
        level = 'low'
    elif share >= 0.5:
        level = 'high'
    elif share >= 0.2:
        level = 'mixed'
    else:
        level = 'low'

    return {
        'level': level,
        'divergence': level != 'high',
        'unique_sources': unique_sources,
        'multi_cited_sources': multi_cited_sources,
    }


def _url_status_from_code(code: int) -> str:
    if 200 <= code < 400:
        return _URL_STATUS_LIVE
    if code in {404, 410}:
        return _URL_STATUS_DEAD
    return _URL_STATUS_UNVERIFIED


def _verify_url(
    url: str,
    *,
    verify_ssl: bool,
    disable_proxy: bool,
    deadline_ts: Optional[float] = None,
) -> str:
    remaining = _deadline_remaining(deadline_ts)
    if remaining is not None and remaining <= 0:
        return _URL_STATUS_UNVERIFIED

    read_timeout = 5.0 if remaining is None else max(1.0, min(5.0, remaining))
    timeout = (CONNECT_TIMEOUT, read_timeout)
    session = requests.Session()
    if disable_proxy:
        session.trust_env = False
    try:
        try:
            with session.request(
                'HEAD', url, allow_redirects=True, timeout=timeout,
                verify=verify_ssl,
            ) as response:
                code = response.status_code
        except (
            requests.exceptions.MissingSchema,
            requests.exceptions.InvalidSchema,
            requests.exceptions.InvalidURL,
        ):
            return _URL_STATUS_DEAD
        except requests.RequestException:
            return _URL_STATUS_UNVERIFIED

        status = _url_status_from_code(code)
        if status != _URL_STATUS_UNVERIFIED:
            return status
        if code == 405:
            try:
                with session.request(
                    'GET', url, allow_redirects=True, timeout=timeout,
                    verify=verify_ssl, stream=True,
                ) as response:
                    code = response.status_code
            except requests.RequestException:
                return _URL_STATUS_UNVERIFIED
            return _url_status_from_code(code)
        return status
    finally:
        session.close()


def _verify_sources(
    consensus: List[Tuple[str, int]],
    *,
    verify_urls: bool,
    deadline_ts: Optional[float],
    sources_limit: int,
    concurrency: int,
    verify_ssl: bool,
    disable_proxy: bool,
    verifier: Callable[..., str] = _verify_url,
) -> List[Dict[str, Any]]:
    shown = consensus[:sources_limit]
    sources = [
        {'url': url, 'count': count, 'status': _URL_STATUS_UNVERIFIED}
        for (url, count) in shown
    ]
    if not verify_urls or not sources:
        return sources
    if (_deadline_remaining(deadline_ts) or 0.0) <= 0:
        return sources

    indexed = list(enumerate(sources))

    def worker(item: Tuple[int, Dict[str, Any]]) -> Tuple[int, str]:
        idx, source = item
        status = verifier(
            source['url'],
            verify_ssl=verify_ssl,
            disable_proxy=disable_proxy,
            deadline_ts=deadline_ts,
        )
        return idx, status

    with ThreadPoolExecutor(max_workers=min(len(indexed), max(1, concurrency))) as ex:
        futures = {ex.submit(worker, item): item[0] for item in indexed}
        timeout = _deadline_remaining(deadline_ts)
        if timeout is not None and timeout <= 0:
            return sources
        try:
            for fut in as_completed(futures, timeout=timeout):
                idx, status = fut.result()
                sources[idx]['status'] = status
        except TimeoutError:
            for fut in futures:
                if fut.done():
                    idx, status = fut.result()
                    sources[idx]['status'] = status
    return sources


def _build_output_payload(
    query: str,
    tier: str,
    merged: Dict[str, Any],
    primary_summary: str,
    source_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    signal = _consensus_signal(merged)
    return {
        'query': query,
        'tier': tier,
        'summary': primary_summary,
        'runs': {
            'total': merged.get('total_runs', 0),
            'ok': merged.get('ok_runs', 0),
        },
        'consensus': signal,
        'sources': source_rows,
    }


def _load_config() -> Dict[str, Any]:
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    candidates = [skill_dir / 'config.json', Path.home() / '.grok' / 'config.json']
    for candidate in candidates:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text())
            except json.JSONDecodeError as e:
                raise SystemExit(f'❌ Grok config is not valid JSON ({candidate}): {e}')
            if isinstance(data, dict):
                # Validate required keys.
                if not data.get('api_key') or not data.get('base_url'):
                    raise SystemExit('❌ Grok config missing required key: api_key / base_url')
                data['_config_path'] = str(candidate)
                return data
    raise SystemExit('❌ Grok config not found (copy config.json.example to config.json)')


# ============================================================================
# Prompt shaping — asymmetric discipline: cut prose, never trim the source list
# ============================================================================

# Keep the in-script prompt contract short and stable. It should encode search
# discipline, not the full research strategy.
_CORE_RETRIEVAL_CONTRACT = (
    "RETRIEVAL CONTRACT:\n"
    "- Search first; answer only from what you can support from the sources you actually used.\n"
    "- Prefer primary, authoritative, and fresh sources over aggregators or paraphrases.\n"
    "- Separate confirmed facts from disputed or unresolved points when the evidence is mixed.\n"
    "- If the evidence is weak or conflicting, say so briefly instead of forcing one neat answer."
)

# A/B validated: these rules cut prose ~76% WITHOUT a synthesis call. The source
# protection clause is essential — naive tightening also dropped sources 13->7.
_OUTPUT_DISCIPLINE = (
    "OUTPUT RULES:\n"
    "- No preamble, no restating the question, no meta-commentary about searching.\n"
    "- Lead with a 1-2 sentence conclusion, then terse bullet findings. Cut filler and hedging.\n"
    "- SOURCE LIST IS PROTECTED: end with a list of EVERY distinct source URL you actually used. "
    "Never shorten or sample the source list to save space, even though the prose is kept tight."
)

_DEEP_RESEARCH_OVERLAY = (
    "MODE: deep research.\n"
    "- Map the landscape broadly, drill into the most important branches, cross-check key claims, "
    "and separate confirmed facts from disputed or unresolved points."
)

# Breadth extraction (validated: 14 -> 68 visible sources on multi-agent models).
_BREADTH_INSTRUCTION = (
    "BREADTH INSTRUCTION:\n"
    "- You have many parallel sub-agents reading many pages. Have each sub-agent surface the distinct "
    "sources it read, then merge into one de-duplicated source list of 30-60 concrete URLs grouped by "
    "sub-topic. Preserve breadth; do not collapse to only the top few."
)

_SYNTHESIS_BACKBONE_OVERLAY = (
    "ROLE: synthesis backbone.\n"
    "- This run is the cross-axis backbone for a larger research campaign.\n"
    "- Balance evidence across source types instead of letting one loud axis dominate.\n"
    "- If one evidence axis is much weaker than the others, say so briefly."
)

_ANGLE_EVIDENCE_PATH_OVERLAY = (
    "ROLE: evidence path.\n"
    "- This run is one evidence path inside a larger research campaign.\n"
    "- Optimize for distinctive sources, claims, disagreements, and missing evidence specific to this angle.\n"
    "- Do not collapse back into a generic whole-topic answer."
)

_AXIS_OVERLAYS = {
    'academic': (
        "AXIS: academic.\n"
        "- Focus on papers, benchmarks, surveys, arXiv, and research repos.\n"
        "- Surface evaluation setup, empirical results, limitations, and open questions."
    ),
    'industry': (
        "AXIS: industry.\n"
        "- Focus on official docs, launch posts, engineering blogs, case studies, and postmortems.\n"
        "- Surface product reality, implementation constraints, migration paths, and operational tradeoffs."
    ),
    'social': (
        "AXIS: social signal.\n"
        "- Focus on X.com, Hacker News, Reddit, and practitioner discussion.\n"
        "- Surface strongest praise, strongest critique, and the most useful linked primary sources.\n"
        "- Treat discussion-platform claims as signals unless other evidence supports them."
    ),
    'adoption': (
        "AXIS: adoption and implementation reality.\n"
        "- Focus on GitHub issues/PRs, RFCs/design docs, integration code, migration guides, example apps, "
        "deploy notes, operator writeups, incident threads, and repro repos.\n"
        "- Surface the actual technical path, what got implemented, where teams got stuck, and what broke."
    ),
}

_AXIS_KEYWORDS = {
    'academic': (
        'paper', 'papers', 'benchmark', 'benchmarks', 'survey', 'surveys', 'arxiv',
        'openreview', 'research repo', 'research repos',
    ),
    'industry': (
        'official doc', 'official docs', 'product announcement', 'product announcements',
        'engineering blog', 'engineering blogs', 'case study', 'case studies',
        'postmortem', 'postmortems', 'launch post', 'launch posts',
    ),
    'social': (
        'x.com', 'hacker news', 'reddit', 'discussion', 'discussions', 'praise',
        'criticism', 'critique',
    ),
    'adoption': (
        'github', 'issue', 'issues', 'pr', 'prs', 'rfc', 'rfcs', 'design doc',
        'design docs', 'integration code', 'migration guide', 'migration guides',
        'example app', 'example apps', 'deploy note', 'deploy notes', 'operator',
        'incident', 'incidents', 'repro repo', 'repro repos',
    ),
}


_PRESET_ANGLE_SUFFIXES = {
    'comparison': (
        'direct comparison benchmarks tradeoffs and primary sources',
        'first named option strengths limits risks failure modes and primary sources',
        'second named option strengths limits risks failure modes and primary sources',
    ),
    'controversy': (
        'best supporting evidence primary sources and strongest claims',
        'best critique counterevidence limitations and failed assumptions',
        'primary source reality what authoritative sources actually show',
    ),
    'recent-change': (
        'official announcements release notes and dated primary sources',
        'breaking changes migrations deprecations and compatibility risks',
        'incidents regressions community reports and unresolved issues',
    ),
    'mechanism': (
        'mechanism architecture internals and causal explanation',
        'counterexamples boundary conditions and where the mechanism fails',
        'operational evidence reproduction details and failure modes',
    ),
    'deep-tech': (
        'academic papers benchmarks surveys arXiv and research repos',
        'official docs product announcements engineering blogs and postmortems',
        'X.com top experts Hacker News Reddit practitioner discussions signals disputes and linked primary sources',
        'GitHub issues PRs RFCs design docs integration code migration guides example apps deployment notes operator writeups and incident reports',
    ),
    'tech-planning': (
        'industry and trend signals from academic papers patents standards industry engineering blogs official roadmaps X.com top experts Hacker News regulation funding and ecosystem shifts',
        'market customer segments buyer pain adoption blockers jobs to be done and budget signals',
        'competitors vendors alternatives benchmarks positioning roadmap and moat',
        'self fit assessment framework current capabilities assets constraints architecture talent data operating gaps and questions to evaluate; use only user-provided internal context',
        'opportunity whitespace timing entry points risks and leverage for technical strategy',
    ),
    'discovery': (
        'official primary sources docs announcements and specs',
        'implementation adoption GitHub issues PRs examples and operator notes',
        'criticism limitations incidents and unresolved questions',
    ),
}

_PRESET_ALIASES = {
    'tech-insight': 'tech-planning',
}


def _axis_overlay_for_query(query: str) -> Optional[str]:
    lower = query.lower()
    scored: List[Tuple[int, str]] = []
    for axis, keywords in _AXIS_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in lower)
        if score > 0:
            scored.append((score, axis))
    if not scored:
        return None
    _, best_axis = max(scored)
    return _AXIS_OVERLAYS[best_axis]


def _preset_angles(query: str, preset: Optional[str]) -> List[str]:
    if not preset:
        return []
    preset = _PRESET_ALIASES.get(preset, preset)
    suffixes = _PRESET_ANGLE_SUFFIXES[preset]
    return [f'{query} {suffix}' for suffix in suffixes]


def _build_query(
    query: str,
    *,
    deep: bool,
    breadth: bool,
    role: str = 'default',
    from_date: Optional[str],
    to_date: Optional[str],
    focus: Optional[str],
    inject_time: bool = True,
) -> str:
    """Single prompt shaper. Intent-driven, backend-agnostic."""
    blocks: List[str] = []
    if inject_time:
        blocks.append(_local_time_context())

    blocks.append(_CORE_RETRIEVAL_CONTRACT)

    if from_date and to_date:
        blocks.append(f'Prefer sources dated between {from_date} and {to_date}. Label any out-of-range material clearly as background.')
    elif from_date:
        blocks.append(f'Prefer sources dated on or after {from_date}. Label older material clearly as background.')

    if focus:
        blocks.append(f'Focus the search on these sources / platforms / angle: {focus}. Prefer primary and authoritative sources over aggregators.')

    if role == 'synthesis_backbone':
        blocks.append(_SYNTHESIS_BACKBONE_OVERLAY)
    elif role == 'angle_path':
        blocks.append(_ANGLE_EVIDENCE_PATH_OVERLAY)
        axis_overlay = _axis_overlay_for_query(query)
        if axis_overlay:
            blocks.append(axis_overlay)

    if deep:
        blocks.append(_DEEP_RESEARCH_OVERLAY)
        if breadth:
            blocks.append(_BREADTH_INSTRUCTION)

    blocks.append(_OUTPUT_DISCIPLINE)
    blocks.append(f'User request: {query}')
    return '\n\n'.join(blocks)


# ============================================================================
# Backend abstraction
# ============================================================================

class Backend:
    """Common interface. One concrete call against the upstream for one model."""

    name = 'base'

    def run(self, *, prompt: str, model: str, max_tokens: Optional[int],
            deadline_ts: Optional[float] = None) -> Dict[str, Any]:
        raise NotImplementedError


class ProxyBackend(Backend):
    """grok2api reverse proxy — behaves like Grok web chat. Default backend."""

    name = 'proxy'

    def __init__(self, api_key: str, base_url: str, disable_proxy: bool = False,
                 verify_ssl: bool = False, retries: int = DEFAULT_RETRIES):
        self.api_key = api_key
        self.base_url = _normalize_base_url(base_url)
        self.verify_ssl = verify_ssl
        self.retries = max(0, retries)
        self.session = requests.Session()
        if disable_proxy:
            self.session.trust_env = False
        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _parse_sse(self, response: requests.Response) -> Dict[str, Any]:
        text_chunks: List[str] = []
        citations: List[Any] = []
        search_sources: List[Dict[str, Any]] = []
        last_event: Dict[str, Any] = {}
        message: Dict[str, Any] = {'role': 'assistant', 'content': ''}
        malformed_events = 0
        valid_events = 0
        saw_done = False
        # Decode bytes ourselves (not iter_lines(decode_unicode=True)) so multi-byte
        # UTF-8 chars split across chunks don't corrupt into mojibake.
        response.encoding = 'utf-8'
        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode('utf-8', errors='replace') if isinstance(raw_line, (bytes, bytearray)) else raw_line
            if not line.startswith('data:'):
                continue
            data = line[len('data:'):].strip()
            if data == '[DONE]':
                saw_done = True
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                malformed_events += 1
                continue
            valid_events += 1
            if isinstance(event.get('error'), dict):
                raise RuntimeError(event['error'].get('message', 'SSE error'))
            last_event = event
            if isinstance(event.get('citations'), list):
                citations.extend(event['citations'])
            search_sources.extend(_collect_search_sources(event))
            choices = event.get('choices') or []
            if not choices:
                continue
            choice = choices[0]
            msg = choice.get('message') or {}
            delta = choice.get('delta') or {}
            if msg.get('content'):
                message['content'] = msg['content']
            if delta.get('content'):
                text_chunks.append(delta['content'])
            for container in (msg, delta):
                for key in ('annotations', 'search_sources', 'citations', 'references'):
                    if key in container and key not in message:
                        message[key] = container[key]
        if not message['content']:
            message['content'] = ''.join(text_chunks)
        result = {'choices': [{'message': message}], 'citations': citations,
                  'model': last_event.get('model'), 'usage': last_event.get('usage', {})}
        if search_sources:
            result['search_sources'] = search_sources
        result['_stream_complete'] = saw_done
        result['_valid_events'] = valid_events
        result['_malformed_events'] = malformed_events
        return result

    def _post_with_retry(self, payload: Dict[str, Any], headers: Dict[str, str],
                         deadline_ts: Optional[float] = None) -> Dict[str, Any]:
        url = f'{self.base_url}/chat/completions'
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            # --- Deadline check before each attempt ---------------------------
            if deadline_ts is not None:
                remaining = deadline_ts - time.time()
                if remaining <= 0:
                    raise TimeoutError('deadline exceeded')
                read_timeout = min(PER_CALL_TIMEOUT, remaining)
            else:
                read_timeout = PER_CALL_TIMEOUT
            timeout = (CONNECT_TIMEOUT, read_timeout)
            # ------------------------------------------------------------------
            try:
                with self.session.post(url, headers=headers, json=payload, timeout=timeout,
                                       verify=self.verify_ssl, stream=True) as response:
                    response.raise_for_status()
                    ctype = response.headers.get('content-type', '')
                    if 'text/event-stream' in ctype:
                        return self._parse_sse(response)
                    return response.json()
            except Exception as exc:  # noqa: BLE001 — retry decided by error class
                last_exc = exc
                if attempt >= self.retries or not _is_retryable_error(exc):
                    raise
                delay = _retry_after_seconds(exc)
                if delay is None:
                    # exponential backoff + jitter (avoid synchronized retry stampede)
                    delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1.5)
                # Cap delay to remaining deadline; if no time left, skip retry.
                if deadline_ts is not None:
                    remaining = deadline_ts - time.time()
                    if remaining <= 0 or delay >= remaining:
                        raise last_exc
                    delay = min(delay, remaining)
                print(f'⚠️  transient error ({exc}); retry {attempt + 1}/{self.retries} in {delay:.1f}s',
                      file=sys.stderr)
                time.sleep(delay)
        raise last_exc if last_exc else RuntimeError('request failed')

    def run(self, *, prompt: str, model: str, max_tokens: Optional[int],
            deadline_ts: Optional[float] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.3,
            'stream': True,
        }
        if max_tokens is not None:
            payload['max_tokens'] = max_tokens
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        raw = self._post_with_retry(payload, headers, deadline_ts=deadline_ts)
        if not isinstance(raw, dict):
            raise RuntimeError(f'unexpected response shape: {type(raw).__name__}')
        if raw.get('_stream_complete') is False:
            raise RuntimeError('incomplete SSE stream (missing [DONE])')
        if raw.get('_valid_events', 0) == 0 and raw.get('_malformed_events', 0) > 0:
            raise RuntimeError('malformed SSE stream (no valid events)')
        message = (raw.get('choices') or [{}])[0].get('message') or {}
        content = _strip_thinking(message.get('content', ''))
        structured = _collect_search_sources(raw)
        urls = sorted(set(
            _collect_urls(structured)
            + _collect_urls(raw.get('citations', []))
            + _collect_urls(message.get('annotations', []))
            + _collect_urls(message.get('references', []))
            + _extract_urls_from_text(content)
        ))
        return {
            'content': content,
            'urls': urls,
            'model': raw.get('model') or model,
            'usage': raw.get('usage', {}),
            'raw_response': raw,
            'payload': payload,
        }


# ============================================================================
# Orchestration — concurrent fanout, resilience, consensus merge
# ============================================================================

def _guarded_run(backend: Backend, prompt: str, model: str, max_tokens: Optional[int],
                 label: str, deadline_ts: Optional[float] = None) -> Dict[str, Any]:
    """Run one call under the global concurrency semaphore. Never raises."""
    t0 = time.time()
    if _CONCURRENCY_SEMAPHORE is not None:
        _CONCURRENCY_SEMAPHORE.acquire()
    try:
        out = backend.run(prompt=prompt, model=model, max_tokens=max_tokens,
                          deadline_ts=deadline_ts)
        # Empty upstream responses are failures even if the HTTP request succeeded.
        content = out.get('content') or ''
        urls = out.get('urls') or []
        if not content.strip() and not urls:
            return {
                'label': label, 'model': model, 'ok': False,
                'error': 'empty response (no content or sources)',
                'latency': round(time.time() - t0, 1),
                'content': '', 'urls': [],
            }
        out.update({'label': label, 'ok': True, 'latency': round(time.time() - t0, 1)})
        return out
    except Exception as exc:  # noqa: BLE001 — failures are tolerated, not fatal
        return {'label': label, 'model': model, 'ok': False,
                'error': str(exc)[:200], 'latency': round(time.time() - t0, 1),
                'content': '', 'urls': []}
    finally:
        if _CONCURRENCY_SEMAPHORE is not None:
            _CONCURRENCY_SEMAPHORE.release()


def _fanout(backend: Backend, tasks: List[Tuple[str, str, str]], max_tokens: Optional[int],
            deadline_ts: float, max_workers: int, stagger_s: float = 0.0) -> List[Dict[str, Any]]:
    """tasks = [(prompt, model, label)]. Concurrent; all work shares one deadline budget."""
    results: List[Dict[str, Any]] = []
    t0 = time.time()
    workers = min(len(tasks), max(1, max_workers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {}
        for i, (p, m, lbl) in enumerate(tasks):
            fut = ex.submit(_guarded_run, backend, p, m, max_tokens, lbl, deadline_ts)
            futures[fut] = (m, lbl)
            if stagger_s > 0 and i < len(tasks) - 1:
                remaining = max(0.0, deadline_ts - time.time())
                if remaining <= 0:
                    break
                time.sleep(min(stagger_s, remaining))
        collected: Set[Any] = set()
        try:
            timeout = max(0.0, deadline_ts - time.time())
            for fut in as_completed(futures, timeout=timeout):
                results.append(fut.result())
                collected.add(fut)
        except TimeoutError:
            for fut, (model, lbl) in futures.items():
                if fut in collected:
                    continue
                if fut.done():
                    try:
                        results.append(fut.result())
                        collected.add(fut)
                    except Exception:
                        pass
                else:
                    fut.cancel()
                    results.append({
                        'label': lbl,
                        'model': model,
                        'ok': False,
                        'error': 'deadline exceeded',
                        'latency': round(time.time() - t0, 1),
                        'content': '',
                        'urls': [],
                    })
                    print(f'⏱️  run "{lbl}" exceeded deadline; dropping', file=sys.stderr)
    return results


def _merge_consensus(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pick the primary answer; build a consensus-ranked union of source URLs."""
    ok = [r for r in results if r.get('ok')]
    # Consensus: count how many runs cited each URL.
    cite_count: Counter = Counter()
    for r in ok:
        cite_count.update(set(r.get('urls') or []))
    ranked = sorted(cite_count.items(), key=lambda kv: (-kv[1], kv[0]))

    # Primary answer = highest-ranked tier among successful runs (most depth).
    primary = max(
        ok,
        key=lambda r: (PRIMARY_RANK.get(r.get('model', ''), 0), len(r.get('content') or '')),
        default=None,
    )
    return {
        'primary': primary,
        'consensus': ranked,           # [(url, count)]
        'total_runs': len(results),
        'ok_runs': len(ok),
        'failed': [r for r in results if not r.get('ok')],
    }


# ============================================================================
# Rendering — compact markdown, consensus annotation
# ============================================================================

def _render(
    merged: Dict[str, Any],
    results: List[Dict[str, Any]],
    *,
    tier: str,
    wall: float,
    source_rows: List[Dict[str, Any]],
    verify_urls: bool,
) -> str:
    out: List[str] = []
    total, okc = merged['total_runs'], merged['ok_runs']
    consensus = merged['consensus']
    signal = _consensus_signal(merged)

    # --- structured run summary (key info at a glance) -----------------------
    out.append(f'━━ grok-search · {tier} · {okc}/{total} runs · {wall:.1f}s ━━')
    for r in results:
        mark = '✓' if r.get('ok') else '✗'
        model = r.get('model', '?')
        if r.get('ok'):
            out.append(f'{mark} {model}  {r.get("latency", 0):.1f}s · {len(r.get("urls") or [])} src')
        else:
            out.append(f'{mark} {model}  {r.get("error", "failed")[:60]}')
    out.append('')
    out.append(
        'signal · '
        f'consensus: {signal["level"]} · '
        f'divergence: {"yes" if signal["divergence"] else "no"} · '
        f'unique: {signal["unique_sources"]} · '
        f'multi-cited: {signal["multi_cited_sources"]}'
    )
    out.append('')

    primary = merged.get('primary')
    if primary and primary.get('content'):
        out.append(primary['content'].strip())
        out.append('')

    if consensus:
        out.append(f'## Sources · {len(consensus)} unique (×N = cited by N runs)')
        for i, source in enumerate(source_rows, 1):
            url = source['url']
            count = source['count']
            tag = f' ×{count}' if count > 1 else ''
            status = f' [{source["status"]}]' if verify_urls else ''
            out.append(f'{i}. {url}{tag}{status}')
        if len(consensus) > len(source_rows):
            out.append(f'… +{len(consensus) - len(source_rows)} more (--sources-limit)')
    return '\n'.join(out).strip()


def _resolve_models(config: Dict[str, Any]) -> Dict[str, Any]:
    models = dict(DEFAULT_MODELS)
    cfg_models = config.get('models')
    if isinstance(cfg_models, dict):
        models.update(cfg_models)
    return models


def _resolve_concurrency(config: Dict[str, Any], cli_value: Optional[int]) -> int:
    if cli_value is not None:
        return max(1, cli_value)
    cfg_value = _coerce_positive_int(config.get('concurrency'))
    if cfg_value is not None:
        return cfg_value
    return DEFAULT_CONCURRENCY


def _resolve_stagger_ms(config: Dict[str, Any], cli_value: Optional[int], concurrency: int) -> int:
    if cli_value is not None:
        return max(0, cli_value)
    raw = config.get('stagger_ms')
    if raw == 0 or raw == '0':
        return 0
    cfg_value = _coerce_positive_int(raw)
    if cfg_value is not None:
        return cfg_value
    return DEFAULT_STAGGER_MS_HIGH_CONCURRENCY if concurrency > 2 else 0


# ============================================================================
# Task planning helper — isolated for testability
# ============================================================================

def _plan_tasks(
    query: str,
    angles: List[str],
    deep: bool,
    fanout: Optional[int],
    angle_fanout: Optional[int],
    include_base_query: bool,
    model: Optional[str],
    models: Dict[str, Any],
    build_query_fn: Any,
) -> List[Tuple[str, str, str]]:
    """Return [(prompt, model_name, label)] for _fanout.

    Angle mode (angles non-empty): one task per angle by default, or
    angle_fanout tasks per angle when requested, round-robin across the ladder.
    Consensus mode: same query, heterogeneous models, fanout times.
    """
    if model:
        ladder = [model]
    else:
        ladder = list(models['deep'] if deep else models['default'])

    tasks: List[Tuple[str, str, str]] = []
    if angles:
        # Angle mode: optional base query, plus one or more runs per angle.
        items = ([query] if include_base_query else []) + angles
        runs_per_angle = angle_fanout if angle_fanout is not None else 1
        runs_per_angle = max(1, runs_per_angle)
        for i, item in enumerate(items):
            role = 'synthesis_backbone' if include_base_query and i == 0 else 'angle_path'
            prompt = build_query_fn(item, deep=deep, breadth=deep, role=role)
            for run_idx in range(runs_per_angle):
                mdl = ladder[(i * runs_per_angle + run_idx) % len(ladder)]
                suffix = f'.run[{run_idx}]' if runs_per_angle > 1 else ''
                label = f'angle[{i}]{suffix}:{mdl}'
                tasks.append((prompt, mdl, label))
    else:
        # Consensus mode: same query, heterogeneous models concurrently.
        n = fanout if fanout is not None else (3 if deep else 2)
        n = max(1, n)
        prompt = build_query_fn(query, deep=deep, breadth=deep, role='default')
        for i in range(n):
            mdl = ladder[i % len(ladder)]
            tasks.append((prompt, mdl, f'run[{i}]:{mdl}'))

    return tasks


# ============================================================================
# main
# ============================================================================

def main() -> None:
    global _CONCURRENCY_SEMAPHORE
    parser = argparse.ArgumentParser(
        description='Concurrent consensus web search over a grok2api reverse proxy.')
    parser.add_argument('query', help='Search query (quote it: "..."). Use --angle for multi-angle mode.')
    parser.add_argument('--deep', action='store_true',
                        help='Deep research: breadth extraction + heterogeneous fanout + consensus')
    parser.add_argument('--fanout', type=_positive_int, default=None,
                        help='Concurrent runs (default 2; --deep default 3); global cap applies')
    parser.add_argument('--preset', choices=sorted(set(_PRESET_ANGLE_SUFFIXES) | set(_PRESET_ALIASES)),
                        help='Expand a common research protocol into explicit angles when --angle is omitted')
    parser.add_argument('--angle', action='append', default=[],
                        help='Explicit research angle (repeatable); each runs concurrently')
    parser.add_argument('--angle-fanout', type=_positive_int, default=None,
                        help='Run each angle with N model passes; use with manual batching for high-value research')
    parser.add_argument('--no-base-query', action='store_true',
                        help='In angle mode, skip the extra base query and run only the explicit angles')
    parser.add_argument('--days', type=_positive_int, help='Recency window: prefer sources from the last N days')
    parser.add_argument('--focus', help='Soft source/platform/angle hint (proxy: prompt-level)')
    parser.add_argument('--sources-limit', type=_positive_int, default=30, help='Max source URLs to print')
    parser.add_argument('--concurrency', type=_positive_int, default=None,
                        help='Global in-flight request cap (CLI overrides config; fallback default 4)')
    parser.add_argument('--stagger-ms', type=_nonnegative_int, default=None,
                        help='Delay between launching upstream requests (CLI overrides config; auto-defaults to 1000ms when concurrency > 2)')
    parser.add_argument('--deadline', type=_positive_int, default=DEFAULT_DEADLINE,
                        help='Wall-clock ceiling for the whole search in seconds (default 180); shared across fanout and degrade')
    parser.add_argument('--model', help='Force a single model (overrides the tier ladder)')
    parser.add_argument('--verify-urls', action='store_true',
                        help='Best-effort verification for the final printed source URLs')
    parser.add_argument('--json', action='store_true',
                        help='Emit a minimal machine-readable JSON wrapper instead of markdown')
    parser.add_argument('--dump-raw', help='Write raw responses to a file')
    parser.add_argument('--max-tokens', type=_positive_int, default=None,
                        help='Per-tier safety ceiling for response tokens')
    args = parser.parse_args()

    query = args.query.strip()
    if not query:
        parser.error('Query required')

    angles: List[str] = list(args.angle)
    if not angles:
        angles = _preset_angles(query, args.preset)
    elif args.preset:
        print('⚠️  --preset is ignored when explicit --angle values are provided', file=sys.stderr)

    # Warn if --fanout is given alongside angle mode (it is ignored there).
    if angles and args.fanout is not None:
        print('⚠️  --fanout is ignored in angle mode; use --angle-fanout for per-angle runs', file=sys.stderr)

    config = _load_config()
    models = _resolve_models(config)
    concurrency = _resolve_concurrency(config, args.concurrency)
    stagger_ms = _resolve_stagger_ms(config, args.stagger_ms, concurrency)
    backend = ProxyBackend(
        api_key=config['api_key'], base_url=config['base_url'],
        disable_proxy=_coerce_bool(config.get('disable_proxy', False)),
        verify_ssl=_coerce_bool(config.get('verify_ssl', False)),
    )
    _CONCURRENCY_SEMAPHORE = threading.Semaphore(concurrency)

    from_date, to_date = _days_to_window(args.days)
    # Per-tier token ceiling (generous; protects the source list from truncation).
    max_tokens = args.max_tokens if args.max_tokens is not None else (2500 if args.deep else 1200)
    build_query = functools.partial(_build_query, from_date=from_date, to_date=to_date, focus=args.focus)

    # --- Plan the concurrent tasks: [(prompt, model, label)] ------------------
    tasks = _plan_tasks(
        query=query,
        angles=angles,
        deep=args.deep,
        fanout=args.fanout,
        angle_fanout=args.angle_fanout,
        include_base_query=not args.no_base_query,
        model=args.model,
        models=models,
        build_query_fn=build_query,
    )

    # --- Execute --------------------------------------------------------------
    tier = 'deep' if args.deep else 'default'
    print(f'· {len(tasks)} run(s) [{tier}]: {", ".join(t[1] for t in tasks)}', file=sys.stderr)
    _t0 = time.time()
    deadline_ts = _t0 + args.deadline
    results = _fanout(
        backend, tasks, max_tokens, deadline_ts,
        max_workers=concurrency, stagger_s=(stagger_ms / 1000.0),
    )

    # --- Degrade: if nothing succeeded, try a single light model -------------
    if not any(r.get('ok') for r in results):
        degrade_model = models.get('degrade', 'grok-4.3-high')
        print(f'· all runs failed; degrading to {degrade_model}', file=sys.stderr)
        prompt = build_query(query, deep=False, breadth=False)
        results = [_guarded_run(
            backend, prompt, degrade_model, 1200, f'degrade:{degrade_model}',
            deadline_ts=deadline_ts,
        )]
        if not any(r.get('ok') for r in results):
            err = results[0].get('error', 'unknown') if results else 'no result'
            print(f'❌ search failed after degrade: {err}', file=sys.stderr)
            sys.exit(1)

    merged = _merge_consensus(results)
    source_rows = _verify_sources(
        merged.get('consensus') or [],
        verify_urls=args.verify_urls,
        deadline_ts=deadline_ts,
        sources_limit=args.sources_limit,
        concurrency=concurrency,
        verify_ssl=backend.verify_ssl,
        disable_proxy=_coerce_bool(config.get('disable_proxy', False)),
    )
    primary = merged.get('primary') or {}
    payload = _build_output_payload(
        query=query,
        tier=tier,
        merged=merged,
        primary_summary=(primary.get('content') or '').strip(),
        source_rows=source_rows,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_render(
            merged, results, tier=tier, wall=time.time() - _t0,
            source_rows=source_rows, verify_urls=args.verify_urls,
        ))

    # --dump-raw written AFTER rendering so a write failure never loses the answer.
    if args.dump_raw:
        try:
            Path(args.dump_raw).write_text(
                json.dumps([r.get('raw_response') for r in results if r.get('ok')],
                           ensure_ascii=False, indent=2))
        except Exception as exc:
            print(f'⚠️  --dump-raw failed: {exc}', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else '?'
        print(f'❌ HTTP {status}: {exc}', file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f'❌ {exc}', file=sys.stderr)
        sys.exit(1)
