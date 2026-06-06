"""
Tests for grok_search.py — all network calls are mocked.
Run with: python3 -m pytest tests/test_grok_search.py -q
       or: python3 tests/test_grok_search.py
"""

import importlib
import io
import json
import sys
import time
import threading
import argparse
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Import grok_search from scripts/ without installing it as a package.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / 'scripts')
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import grok_search  # noqa: E402  (after sys.path manipulation)


# ===========================================================================
# Fake helpers
# ===========================================================================

class FakeResponse:
    """Minimal requests.Response stand-in for _parse_sse tests."""

    def __init__(self, lines: List[bytes], content_type: str = 'text/event-stream',
                 status_code: int = 200):
        self._lines = lines
        self.headers = {'content-type': content_type}
        self.encoding = 'utf-8'
        self.status_code = status_code

    def iter_lines(self, decode_unicode: bool = False):
        for line in self._lines:
            yield line

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)

    def json(self):
        return {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FastBackend(grok_search.Backend):
    """Returns immediately with real content."""
    name = 'fast'

    def run(self, *, prompt: str, model: str, max_tokens: Optional[int],
            deadline_ts: Optional[float] = None) -> Dict[str, Any]:
        return {
            'content': 'fast answer',
            'urls': ['https://example.com/fast'],
            'model': model,
            'usage': {},
        }


class SlowBackend(grok_search.Backend):
    """Sleeps for `sleep_s` seconds before returning (simulates a slow network call)."""
    name = 'slow'

    def __init__(self, sleep_s: float):
        self.sleep_s = sleep_s

    def run(self, *, prompt: str, model: str, max_tokens: Optional[int],
            deadline_ts: Optional[float] = None) -> Dict[str, Any]:
        # Respect the deadline_ts: sleep in small increments, check deadline.
        end = time.time() + self.sleep_s
        while time.time() < end:
            if deadline_ts is not None and time.time() >= deadline_ts:
                raise TimeoutError('deadline exceeded')
            time.sleep(0.05)
        return {
            'content': 'slow answer',
            'urls': ['https://example.com/slow'],
            'model': model,
            'usage': {},
        }


class EmptyBackend(grok_search.Backend):
    """Always returns empty content and empty urls."""
    name = 'empty'

    def run(self, *, prompt: str, model: str, max_tokens: Optional[int],
            deadline_ts: Optional[float] = None) -> Dict[str, Any]:
        return {
            'content': '',
            'urls': [],
            'model': model,
            'usage': {},
        }


class FullBackend(grok_search.Backend):
    """Returns non-empty content and urls."""
    name = 'full'

    def run(self, *, prompt: str, model: str, max_tokens: Optional[int],
            deadline_ts: Optional[float] = None) -> Dict[str, Any]:
        return {
            'content': 'some real answer text',
            'urls': ['https://example.com/1'],
            'model': model,
            'usage': {},
        }


# ===========================================================================
# Test 1 — Deadline bounds wall-clock time
# ===========================================================================

def test_deadline_bounds_wall_clock():
    """A slow task that respects deadline_ts must not block past ~deadline."""
    # One fast task (0.05s), one slow task (sleeps 2s but checks deadline).
    tasks = [
        ('prompt_fast', 'model-a', 'fast_label'),
        ('prompt_slow', 'model-b', 'slow_label'),
    ]

    # Use a mixed backend: fast for model-a, slow for model-b.
    class MixedBackend(grok_search.Backend):
        name = 'mixed'
        def run(self, *, prompt, model, max_tokens, deadline_ts=None):
            if model == 'model-a':
                return {'content': 'fast', 'urls': ['https://fast.example.com'], 'model': model, 'usage': {}}
            # slow path: honour deadline_ts
            end = time.time() + 2.0
            while time.time() < end:
                if deadline_ts is not None and time.time() >= deadline_ts:
                    raise TimeoutError('deadline exceeded')
                time.sleep(0.05)
            return {'content': 'slow', 'urls': ['https://slow.example.com'], 'model': model, 'usage': {}}

    backend = MixedBackend()
    # Reset semaphore for test isolation.
    grok_search._CONCURRENCY_SEMAPHORE = threading.Semaphore(4)

    deadline = 1  # 1 second — slow task (2s) must be cut short
    slack = 0.8   # allow up to 0.8s overhead for scheduling
    t0 = time.time()
    results = grok_search._fanout(
        backend, tasks, None, time.time() + deadline, max_workers=4
    )
    elapsed = time.time() - t0

    assert elapsed < deadline + slack, (
        f"_fanout took {elapsed:.2f}s but deadline was {deadline}s (slack {slack}s)"
    )
    # The fast result must be present.
    ok_results = [r for r in results if r.get('ok')]
    assert any(r.get('model') == 'model-a' for r in ok_results), \
        "Fast result should be present in output"
    assert len(results) == 2, f"Expected 2 result rows (fast success + slow timeout), got {len(results)}"
    assert any((not r.get('ok')) and 'deadline exceeded' in (r.get('error') or '') for r in results), \
        f"Expected one timeout failure row, got: {results}"


# ===========================================================================
# Test 2 — Empty success -> failure
# ===========================================================================

def test_empty_success_becomes_failure():
    """_guarded_run must mark empty content+urls as ok=False."""
    grok_search._CONCURRENCY_SEMAPHORE = threading.Semaphore(4)
    result = grok_search._guarded_run(
        EmptyBackend(), 'prompt', 'model-x', None, 'test_label'
    )
    assert result['ok'] is False, "Empty content+urls must produce ok=False"
    assert 'empty response' in result['error'].lower(), (
        f"Expected 'empty response' in error, got: {result['error']}"
    )
    assert result['content'] == ''
    assert result['urls'] == []


# ===========================================================================
# Test 3 — Non-empty success stays ok=True
# ===========================================================================

def test_nonempty_success_stays_ok():
    """_guarded_run must keep ok=True when content or urls are non-empty."""
    grok_search._CONCURRENCY_SEMAPHORE = threading.Semaphore(4)
    result = grok_search._guarded_run(
        FullBackend(), 'prompt', 'model-y', None, 'test_label'
    )
    assert result['ok'] is True, f"Non-empty result must be ok=True, got: {result}"


# ===========================================================================
# Test 4 — Single positional; unquoted multi-word raises SystemExit
# ===========================================================================

def test_unquoted_multiword_query_rejected():
    """Extra bare positional args must cause argparse to exit."""
    parser_used = False
    try:
        # Simulate: grok_search.py word1 word2 word3
        # With a single required positional this should fail with SystemExit.
        p = argparse.ArgumentParser()
        p.add_argument('query')
        p.parse_args(['word1', 'word2', 'word3'])
        parser_used = True
    except SystemExit:
        pass
    assert not parser_used, "Should have raised SystemExit for extra positionals"


def test_single_quoted_query_parses():
    """A single quoted multi-word string must parse as one query."""
    p = argparse.ArgumentParser()
    p.add_argument('query')
    ns = p.parse_args(['hello world this is one query'])
    assert ns.query == 'hello world this is one query'


# ===========================================================================
# Test 5 — Angle mode vs. consensus mode task planning
# ===========================================================================

def test_angle_mode_task_count():
    """Angle mode: task count = 1 (base query) + number of angles, regardless of fanout."""
    models = {
        'default': ['model-a', 'model-b'],
        'deep': ['model-a', 'model-b', 'model-c'],
        'degrade': 'model-a',
    }
    build_fn = lambda q, **kw: f'prompt:{q}'

    angles = ['angle1', 'angle2', 'angle3']
    tasks = grok_search._plan_tasks(
        query='base query',
        angles=angles,
        deep=False,
        fanout=10,       # should be ignored in angle mode
        include_base_query=True,
        model=None,
        models=models,
        build_query_fn=build_fn,
    )
    # Expected: 1 base + 3 angles = 4 tasks
    assert len(tasks) == 4, f"Expected 4 tasks, got {len(tasks)}"


def test_angle_mode_fanout_does_not_change_count():
    """Different fanout values must not change angle-mode task count."""
    models = {
        'default': ['model-a', 'model-b'],
        'deep': ['model-a', 'model-b', 'model-c'],
        'degrade': 'model-a',
    }
    build_fn = lambda q, **kw: f'prompt:{q}'
    angles = ['a1', 'a2']

    for fanout_val in [1, 2, 5, 10, None]:
        tasks = grok_search._plan_tasks(
            query='q', angles=angles, deep=False,
            fanout=fanout_val, include_base_query=True, model=None, models=models,
            build_query_fn=build_fn,
        )
        assert len(tasks) == 3, (
            f"fanout={fanout_val}: expected 3 tasks (1+2 angles), got {len(tasks)}"
        )


def test_consensus_mode_fanout_respected():
    """In consensus mode, fanout controls the number of tasks."""
    models = {
        'default': ['model-a', 'model-b'],
        'deep': ['model-a', 'model-b', 'model-c'],
        'degrade': 'model-a',
    }
    build_fn = lambda q, **kw: f'prompt:{q}'

    tasks = grok_search._plan_tasks(
        query='q', angles=[], deep=False,
        fanout=5, include_base_query=True, model=None, models=models,
        build_query_fn=build_fn,
    )
    assert len(tasks) == 5


# ===========================================================================
# Test 6 — Malformed SSE handling
# ===========================================================================

def _make_sse_line(data: str) -> bytes:
    return f'data: {data}'.encode('utf-8')


def test_parse_sse_tolerates_invalid_json():
    """_parse_sse must not raise on lines with invalid JSON; valid content is returned."""
    valid_delta = json.dumps({
        'choices': [{'delta': {'content': 'hello '}, 'message': {}}],
        'citations': [],
    })
    valid_delta2 = json.dumps({
        'choices': [{'delta': {'content': 'world'}, 'message': {}}],
        'citations': [],
    })
    lines = [
        _make_sse_line('not-valid-json{{{'),
        _make_sse_line('{broken":'),
        _make_sse_line(valid_delta),
        _make_sse_line(valid_delta2),
        b'data: [DONE]',
    ]
    resp = FakeResponse(lines)
    backend = grok_search.ProxyBackend.__new__(grok_search.ProxyBackend)
    result = backend._parse_sse(resp)
    content = result['choices'][0]['message']['content']
    assert 'hello' in content and 'world' in content, (
        f"Valid content should be returned despite invalid JSON lines; got: {repr(content)}"
    )


def test_parse_sse_all_invalid_yields_empty():
    """A stream with only invalid/empty lines must produce empty content."""
    lines = [
        _make_sse_line('not-json'),
        _make_sse_line('{bad}'),
        b'data: [DONE]',
    ]
    resp = FakeResponse(lines)
    backend = grok_search.ProxyBackend.__new__(grok_search.ProxyBackend)
    result = backend._parse_sse(resp)
    content = result['choices'][0]['message']['content']
    # Empty content from SSE means _guarded_run will mark it ok=False (fix #2).
    assert content == '', f"Expected empty content from all-invalid SSE, got: {repr(content)}"


def test_parse_sse_all_invalid_then_guarded_run_fails():
    """_guarded_run should mark an all-invalid SSE stream as ok=False."""
    lines = [
        _make_sse_line('bad-json'),
        b'data: [DONE]',
    ]

    class SSEEmptyBackend(grok_search.Backend):
        name = 'sse_empty'
        def run(self, *, prompt, model, max_tokens, deadline_ts=None):
            resp = FakeResponse(lines)
            # Re-use _parse_sse logic inline via a temporary ProxyBackend instance.
            pb = grok_search.ProxyBackend.__new__(grok_search.ProxyBackend)
            parsed = pb._parse_sse(resp)
            message = (parsed.get('choices') or [{}])[0].get('message') or {}
            content = grok_search._strip_thinking(message.get('content', ''))
            return {'content': content, 'urls': [], 'model': model, 'usage': {}}

    grok_search._CONCURRENCY_SEMAPHORE = threading.Semaphore(4)
    result = grok_search._guarded_run(SSEEmptyBackend(), 'p', 'm', None, 'lbl')
    assert result['ok'] is False
    assert 'empty response' in result['error'].lower()


def test_parse_sse_missing_done_then_guarded_run_fails():
    """A truncated SSE stream with content but no [DONE] must not count as success."""
    valid_delta = json.dumps({
        'choices': [{'delta': {'content': 'partial answer'}, 'message': {}}],
        'citations': [],
    })
    lines = [_make_sse_line(valid_delta)]

    class TruncatedSSEBackend(grok_search.Backend):
        name = 'truncated_sse'

        def run(self, *, prompt, model, max_tokens, deadline_ts=None):
            resp = FakeResponse(lines)
            pb = grok_search.ProxyBackend.__new__(grok_search.ProxyBackend)
            raw = pb._parse_sse(resp)
            if raw.get('_stream_complete') is False:
                raise RuntimeError('incomplete SSE stream (missing [DONE])')
            return {'content': 'should not happen', 'urls': [], 'model': model, 'usage': {}}

    grok_search._CONCURRENCY_SEMAPHORE = threading.Semaphore(4)
    result = grok_search._guarded_run(TruncatedSSEBackend(), 'p', 'm', None, 'lbl')
    assert result['ok'] is False
    assert 'missing [done]' in result['error'].lower()


def test_main_degrade_reuses_global_deadline():
    """The degrade fallback must receive the same global deadline budget."""
    argv = ['grok_search.py', 'quoted query', '--deadline', '7']
    observed = {}

    def fake_fanout(backend, tasks, max_tokens, deadline_ts, max_workers, stagger_s=0.0):
        observed['fanout_deadline_ts'] = deadline_ts
        return [{'ok': False, 'model': 'model-a', 'error': 'boom', 'content': '', 'urls': []}]

    def fake_guarded_run(backend, prompt, model, max_tokens, label, deadline_ts=None):
        observed['degrade_deadline_ts'] = deadline_ts
        return {'ok': False, 'model': model, 'error': 'deadline exceeded', 'content': '', 'urls': []}

    with patch.object(sys, 'argv', argv), \
         patch.object(grok_search, '_load_config', return_value={
             'api_key': 'k',
             'base_url': 'https://example.test',
             'models': {'default': ['model-a'], 'deep': ['model-a'], 'degrade': 'model-z'},
         }), \
         patch.object(grok_search, '_fanout', side_effect=fake_fanout), \
         patch.object(grok_search, '_guarded_run', side_effect=fake_guarded_run):
        try:
            grok_search.main()
        except SystemExit:
            pass

    assert 'fanout_deadline_ts' in observed
    assert observed['degrade_deadline_ts'] == observed['fanout_deadline_ts']


def test_invalid_numeric_args_rejected():
    """Numeric flags should fail fast instead of silently changing meaning."""
    invalid_argvs = [
        ['grok_search.py', 'q', '--deadline', '0'],
        ['grok_search.py', 'q', '--sources-limit', '-1'],
        ['grok_search.py', 'q', '--days', '0'],
    ]
    for argv in invalid_argvs:
        with patch.object(sys, 'argv', argv):
            try:
                grok_search.main()
                assert False, f'Expected SystemExit for argv={argv!r}'
            except SystemExit as exc:
                assert exc.code != 0


def test_consensus_signal_levels():
    """Consensus level should reflect how many URLs are multi-cited."""
    high = grok_search._consensus_signal({
        'consensus': [('a', 2), ('b', 2), ('c', 1)],
        'ok_runs': 2,
    })
    low = grok_search._consensus_signal({
        'consensus': [('a', 1), ('b', 1), ('c', 1)],
        'ok_runs': 2,
    })
    assert high['level'] == 'high'
    assert high['divergence'] is False
    assert low['level'] == 'low'
    assert low['divergence'] is True


def test_verify_sources_skips_when_deadline_spent():
    """URL verification should not run after the shared deadline is exhausted."""
    seen = {'called': False}

    def fake_verifier(url, **kwargs):
        seen['called'] = True
        return 'live'

    rows = grok_search._verify_sources(
        [('https://example.com/a', 2)],
        verify_urls=True,
        deadline_ts=time.time() - 1,
        sources_limit=10,
        concurrency=4,
        verify_ssl=False,
        disable_proxy=True,
        verifier=fake_verifier,
    )
    assert seen['called'] is False
    assert rows[0]['status'] == 'unverified'


def test_verify_sources_applies_statuses():
    """Verification statuses should be attached to the final source rows."""
    mapping = {
        'https://example.com/live': 'live',
        'https://example.com/dead': 'dead',
        'https://example.com/unknown': 'unverified',
    }

    def fake_verifier(url, **kwargs):
        return mapping[url]

    rows = grok_search._verify_sources(
        [
            ('https://example.com/live', 2),
            ('https://example.com/dead', 1),
            ('https://example.com/unknown', 1),
        ],
        verify_urls=True,
        deadline_ts=time.time() + 30,
        sources_limit=10,
        concurrency=4,
        verify_ssl=False,
        disable_proxy=True,
        verifier=fake_verifier,
    )
    assert [row['status'] for row in rows] == ['live', 'dead', 'unverified']


def test_build_output_payload_minimal_schema():
    """The JSON wrapper should stay minimal and stable."""
    payload = grok_search._build_output_payload(
        query='q',
        tier='default',
        merged={
            'total_runs': 2,
            'ok_runs': 2,
            'consensus': [('https://example.com/a', 2), ('https://example.com/b', 1)],
        },
        primary_summary='summary text',
        source_rows=[{'url': 'https://example.com/a', 'count': 2, 'status': 'live'}],
    )
    assert payload['query'] == 'q'
    assert payload['tier'] == 'default'
    assert payload['summary'] == 'summary text'
    assert payload['runs'] == {'total': 2, 'ok': 2}
    assert payload['consensus']['level'] in {'high', 'mixed', 'low'}
    assert payload['sources'][0]['status'] == 'live'


def test_main_json_output():
    """--json should emit the script-owned wrapper, not markdown."""
    argv = ['grok_search.py', 'quoted query', '--json']
    stdout = io.StringIO()

    def fake_fanout(backend, tasks, max_tokens, deadline_ts, max_workers, stagger_s=0.0):
        return [{
            'ok': True,
            'model': 'model-a',
            'content': 'primary summary',
            'urls': ['https://example.com/a'],
            'latency': 0.1,
        }]

    with patch.object(sys, 'argv', argv), \
         patch.object(grok_search, '_load_config', return_value={
             'api_key': 'k',
             'base_url': 'https://example.test',
             'models': {'default': ['model-a'], 'deep': ['model-a'], 'degrade': 'model-a'},
         }), \
         patch.object(grok_search, '_fanout', side_effect=fake_fanout), \
         patch.object(grok_search, '_verify_sources', return_value=[
             {'url': 'https://example.com/a', 'count': 1, 'status': 'unverified'}
         ]), \
         redirect_stdout(stdout):
        grok_search.main()

    payload = json.loads(stdout.getvalue())
    assert payload['query'] == 'quoted query'
    assert payload['summary'] == 'primary summary'
    assert payload['sources'][0]['url'] == 'https://example.com/a'
    assert 'consensus' in payload


# ===========================================================================
# Test 8 — Protocol tests for common search combinations
# ===========================================================================

def test_official_fact_check_protocol_carries_verification_status():
    """Verified lookups should preserve source verification status in the payload."""
    payload = grok_search._build_output_payload(
        query='OpenAI Responses API official docs',
        tier='default',
        merged={
            'total_runs': 2,
            'ok_runs': 2,
            'consensus': [('https://developers.openai.com/api/docs/quickstart', 2)],
        },
        primary_summary='summary',
        source_rows=[{
            'url': 'https://developers.openai.com/api/docs/quickstart',
            'count': 2,
            'status': 'live',
        }],
    )
    assert payload['sources'][0]['status'] == 'live'


def test_recent_changes_protocol_injects_date_window():
    """Recent-state queries should carry an explicit date preference block."""
    query = grok_search._build_query(
        'latest OpenAI changelog entries',
        deep=False,
        breadth=False,
        from_date='2026-05-01',
        to_date='2026-06-01',
        focus=None,
        inject_time=False,
    )
    assert 'Prefer sources dated between 2026-05-01 and 2026-06-01.' in query


def test_compare_protocol_preserves_head_to_head_angle():
    """Comparison runs should preserve explicit direct-comparison angles."""
    models = {
        'default': ['model-a', 'model-b'],
        'deep': ['model-a', 'model-b', 'model-c'],
        'degrade': 'model-a',
    }
    build_fn = lambda q, **kw: f'prompt:{q}'
    tasks = grok_search._plan_tasks(
        query='A vs B',
        angles=['A vs B direct benchmarks', 'A limits', 'B limits'],
        deep=False,
        fanout=None,
        include_base_query=True,
        model=None,
        models=models,
        build_query_fn=build_fn,
    )
    prompts = [task[0] for task in tasks]
    assert 'prompt:A vs B direct benchmarks' in prompts


def test_preset_expands_common_angle_set():
    """Presets should turn one query into scenario-specific evidence angles."""
    angles = grok_search._preset_angles('A vs B', 'comparison')
    assert len(angles) == 3
    assert angles[0].startswith('A vs B ')
    assert 'direct comparison' in angles[0]


def test_tech_planning_preset_uses_five_look_angles():
    """The technology-planning preset should map 5-look strategy into evidence angles."""
    angles = grok_search._preset_angles('AI coding agents', 'tech-planning')
    assert len(angles) == 5
    joined = '\n'.join(angles)
    assert 'industry and trend signals' in joined
    assert 'academic papers patents standards' in joined
    assert 'X.com top experts Hacker News' in joined
    assert 'market customer segments' in joined
    assert 'competitors vendors alternatives' in joined
    assert 'self fit assessment framework' in joined
    assert 'use only user-provided internal context' in joined
    assert 'opportunity whitespace timing' in joined


def test_tech_insight_alias_stays_compatible():
    """The old tech-insight name should remain as a compatibility alias."""
    assert grok_search._preset_angles('q', 'tech-insight') == grok_search._preset_angles('q', 'tech-planning')


def test_empty_preset_returns_no_angles():
    """Without a preset, the default path should remain consensus mode."""
    assert grok_search._preset_angles('query', None) == []


def test_angle_mode_query_roles_are_layered():
    """Angle mode should give the base query a backbone role and angles an evidence-path role."""
    models = {
        'default': ['model-a', 'model-b'],
        'deep': ['model-a', 'model-b', 'model-c'],
        'degrade': 'model-a',
    }
    prompts = []

    def build_fn(q, **kw):
        prompts.append((q, kw.get('role')))
        return f'prompt:{q}:{kw.get("role")}'

    grok_search._plan_tasks(
        query='dynamic workflow',
        angles=['academic papers', 'GitHub issues'],
        deep=False,
        fanout=None,
        include_base_query=True,
        model=None,
        models=models,
        build_query_fn=build_fn,
    )
    assert prompts[0] == ('dynamic workflow', 'synthesis_backbone')
    assert prompts[1] == ('academic papers', 'angle_path')
    assert prompts[2] == ('GitHub issues', 'angle_path')


def test_angle_mode_can_skip_base_query():
    """Angle mode should support running only explicit angles when base query is disabled."""
    models = {
        'default': ['model-a', 'model-b'],
        'deep': ['model-a', 'model-b', 'model-c'],
        'degrade': 'model-a',
    }
    build_fn = lambda q, **kw: f'prompt:{q}:{kw.get("role")}'
    tasks = grok_search._plan_tasks(
        query='base query',
        angles=['academic papers', 'GitHub issues', 'industry docs'],
        deep=False,
        fanout=None,
        include_base_query=False,
        model=None,
        models=models,
        build_query_fn=build_fn,
    )
    assert len(tasks) == 3
    assert all(':angle_path' in task[0] for task in tasks)


def test_build_query_adds_axis_specific_overlay():
    """Axis-aware angle prompts should steer social and GitHub runs differently."""
    social = grok_search._build_query(
        'dynamic workflow X.com Hacker News Reddit discussions praise criticism',
        deep=False,
        breadth=False,
        role='angle_path',
        from_date=None,
        to_date=None,
        focus=None,
        inject_time=False,
    )
    adoption = grok_search._build_query(
        'dynamic workflow GitHub issues PRs RFCs design docs integration code migration guides',
        deep=False,
        breadth=False,
        role='angle_path',
        from_date=None,
        to_date=None,
        focus=None,
        inject_time=False,
    )
    backbone = grok_search._build_query(
        'dynamic workflow for AI agents',
        deep=False,
        breadth=False,
        role='synthesis_backbone',
        from_date=None,
        to_date=None,
        focus=None,
        inject_time=False,
    )
    assert 'AXIS: social signal.' in social
    assert 'Treat discussion-platform claims as signals' in social
    assert 'AXIS: adoption and implementation reality.' in adoption
    assert 'actual technical path' in adoption
    assert 'ROLE: synthesis backbone.' in backbone
    assert 'one loud axis dominate' in backbone


def test_landscape_scan_protocol_defaults_to_three_deep_runs():
    """Landscape scans should use the default deep fanout of three runs."""
    models = {
        'default': ['model-a', 'model-b'],
        'deep': ['model-a', 'model-b', 'model-c'],
        'degrade': 'model-a',
    }
    build_fn = lambda q, **kw: f'prompt:{q}'
    tasks = grok_search._plan_tasks(
        query='AI agent orchestration landscape',
        angles=[],
        deep=True,
        fanout=None,
        include_base_query=True,
        model=None,
        models=models,
        build_query_fn=build_fn,
    )
    assert len(tasks) == 3


def test_resolve_concurrency_prefers_cli_then_config():
    """Concurrency should come from CLI first, then config, then fallback."""
    assert grok_search._resolve_concurrency({'concurrency': 3}, None) == 3
    assert grok_search._resolve_concurrency({'concurrency': 3}, 2) == 2
    assert grok_search._resolve_concurrency({}, None) == grok_search.DEFAULT_CONCURRENCY


def test_resolve_stagger_defaults_only_for_higher_concurrency():
    """Stagger should auto-enable only when concurrency is above 2, unless overridden."""
    assert grok_search._resolve_stagger_ms({}, None, 2) == 0
    assert grok_search._resolve_stagger_ms({}, None, 5) == grok_search.DEFAULT_STAGGER_MS_HIGH_CONCURRENCY
    assert grok_search._resolve_stagger_ms({'stagger_ms': 250}, None, 5) == 250
    assert grok_search._resolve_stagger_ms({'stagger_ms': 0}, None, 5) == 0
    assert grok_search._resolve_stagger_ms({}, 400, 5) == 400


def test_branch_drill_protocol_keeps_json_contract_stable():
    """Branch drill-down should remain safe for downstream JSON chaining."""
    payload = grok_search._build_output_payload(
        query='deep branch query',
        tier='deep',
        merged={
            'total_runs': 3,
            'ok_runs': 2,
            'consensus': [('https://example.com/branch', 2)],
        },
        primary_summary='branch summary',
        source_rows=[{'url': 'https://example.com/branch', 'count': 2, 'status': 'unverified'}],
    )
    assert payload['tier'] == 'deep'
    assert payload['runs']['ok'] == 2
    assert payload['sources'][0]['status'] == 'unverified'


def test_controversy_protocol_marks_low_overlap_as_divergent():
    """Controversial/low-overlap outputs should set divergence explicitly."""
    payload = grok_search._build_output_payload(
        query='controversial topic',
        tier='default',
        merged={
            'total_runs': 2,
            'ok_runs': 2,
            'consensus': [
                ('https://example.com/a', 1),
                ('https://example.com/b', 1),
                ('https://example.com/c', 1),
            ],
        },
        primary_summary='summary',
        source_rows=[],
    )
    assert payload['consensus']['level'] == 'low'
    assert payload['consensus']['divergence'] is True


# ===========================================================================
# Simple __main__ harness (fallback if pytest not available)
# ===========================================================================

if __name__ == '__main__':
    tests = [
        test_deadline_bounds_wall_clock,
        test_empty_success_becomes_failure,
        test_nonempty_success_stays_ok,
        test_unquoted_multiword_query_rejected,
        test_single_quoted_query_parses,
        test_angle_mode_task_count,
        test_angle_mode_fanout_does_not_change_count,
        test_consensus_mode_fanout_respected,
        test_parse_sse_tolerates_invalid_json,
        test_parse_sse_all_invalid_yields_empty,
        test_parse_sse_all_invalid_then_guarded_run_fails,
        test_parse_sse_missing_done_then_guarded_run_fails,
        test_main_degrade_reuses_global_deadline,
        test_invalid_numeric_args_rejected,
        test_consensus_signal_levels,
        test_verify_sources_skips_when_deadline_spent,
        test_verify_sources_applies_statuses,
        test_build_output_payload_minimal_schema,
        test_main_json_output,
        test_official_fact_check_protocol_carries_verification_status,
        test_recent_changes_protocol_injects_date_window,
        test_compare_protocol_preserves_head_to_head_angle,
        test_angle_mode_query_roles_are_layered,
        test_build_query_adds_axis_specific_overlay,
        test_landscape_scan_protocol_defaults_to_three_deep_runs,
        test_branch_drill_protocol_keeps_json_contract_stable,
        test_resolve_concurrency_prefers_cli_then_config,
        test_resolve_stagger_defaults_only_for_higher_concurrency,
        test_controversy_protocol_marks_low_overlap_as_divergent,
    ]
    failures = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f'PASS  {test_fn.__name__}')
        except Exception as e:
            print(f'FAIL  {test_fn.__name__}: {e}')
            failures += 1
    print(f'\n{len(tests) - failures}/{len(tests)} passed')
    sys.exit(0 if failures == 0 else 1)
