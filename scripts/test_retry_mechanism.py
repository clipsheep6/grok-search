#!/usr/bin/env python3
"""
测试 grok-search 重试机制
运行方式: python3 test_retry_mechanism.py
"""

import sys
import time
from pathlib import Path

# 添加 scripts 目录到路径
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from grok_search import GrokSearcher, _is_retryable_error, _get_retry_delay
import requests


def test_error_classification():
    """测试错误分类逻辑"""
    print("=" * 60)
    print("测试 1: 错误分类")
    print("=" * 60)

    class MockResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    test_cases = [
        # (错误类型, 是否可重试, 描述)
        (requests.exceptions.ConnectionError("test"), True, "ConnectionError"),
        (requests.exceptions.Timeout("test"), True, "Timeout"),
        (requests.exceptions.ChunkedEncodingError("test"), True, "ChunkedEncodingError"),
    ]

    # HTTP 错误测试
    http_tests = [
        (500, True, "HTTP 500 (服务器错误)"),
        (502, True, "HTTP 502 (网关错误)"),
        (503, True, "HTTP 503 (服务不可用)"),
        (429, True, "HTTP 429 (速率限制)"),
        (401, False, "HTTP 401 (未授权)"),
        (403, False, "HTTP 403 (禁止访问)"),
        (400, False, "HTTP 400 (错误请求)"),
        (404, False, "HTTP 404 (未找到)"),
    ]

    for status_code, expected, desc in http_tests:
        error = requests.exceptions.HTTPError()
        error.response = MockResponse(status_code)
        test_cases.append((error, expected, desc))

    passed = 0
    failed = 0

    for error, expected, desc in test_cases:
        result = _is_retryable_error(error)
        if result == expected:
            print(f"✅ {desc}: retryable={result}")
            passed += 1
        else:
            print(f"❌ {desc}: retryable={result} (expected={expected})")
            failed += 1

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_delay_calculation():
    """测试延迟计算"""
    print("\n" + "=" * 60)
    print("测试 2: 延迟计算")
    print("=" * 60)

    dummy_error = requests.exceptions.ConnectionError("test")

    passed = 0
    failed = 0

    for attempt in range(3):
        delay = _get_retry_delay(attempt, dummy_error, base_delay=1.0)
        expected_min = 1.0 * (2 ** attempt)
        expected_max = expected_min * 1.1

        if expected_min <= delay <= expected_max:
            print(f"✅ Attempt {attempt}: {delay:.2f}s (范围: {expected_min:.1f}-{expected_max:.1f}s)")
            passed += 1
        else:
            print(f"❌ Attempt {attempt}: {delay:.2f}s (超出范围: {expected_min:.1f}-{expected_max:.1f}s)")
            failed += 1

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_retry_after_header():
    """测试 Retry-After 响应头处理"""
    print("\n" + "=" * 60)
    print("测试 3: Retry-After 响应头")
    print("=" * 60)

    class MockResponse:
        def __init__(self, retry_after):
            self.status_code = 429
            self.headers = {'Retry-After': retry_after}

    # 测试整数格式
    error = requests.exceptions.HTTPError()
    error.response = MockResponse('60')

    delay = _get_retry_delay(0, error, base_delay=1.0)

    if delay == 60.0:
        print(f"✅ Retry-After 整数格式: {delay}s (expected=60s)")
        return True
    else:
        print(f"❌ Retry-After 整数格式: {delay}s (expected=60s)")
        return False


def test_method_signature():
    """测试 search() 方法签名"""
    print("\n" + "=" * 60)
    print("测试 4: search() 方法签名")
    print("=" * 60)

    import inspect

    sig = inspect.signature(GrokSearcher.search)
    params = list(sig.parameters.keys())

    expected_params = [
        'self', 'query', 'mode', 'context',
        'temperature', 'max_tokens',
        'max_retries', 'retry_base_delay'
    ]

    if params == expected_params:
        print(f"✅ 方法参数正确: {params}")

        # 检查默认值
        max_retries_default = sig.parameters['max_retries'].default
        retry_base_delay_default = sig.parameters['retry_base_delay'].default

        if max_retries_default == 3 and retry_base_delay_default == 1.0:
            print(f"✅ 默认值正确: max_retries={max_retries_default}, retry_base_delay={retry_base_delay_default}")
            return True
        else:
            print(f"❌ 默认值错误: max_retries={max_retries_default}, retry_base_delay={retry_base_delay_default}")
            return False
    else:
        print(f"❌ 方法参数不匹配")
        print(f"   Expected: {expected_params}")
        print(f"   Got: {params}")
        return False


def test_network_timeout():
    """测试网络超时重试（使用不可达 IP）"""
    print("\n" + "=" * 60)
    print("测试 5: 网络超时重试")
    print("=" * 60)
    print("⚠️  此测试会实际触发网络超时，需要约 3-5 秒")

    response = input("是否运行此测试？(y/n): ").strip().lower()
    if response != 'y':
        print("⏭️  跳过网络超时测试")
        return True

    searcher = GrokSearcher(
        api_key="test_key",
        base_url="http://10.255.255.1:9999",  # 不可达 IP
        api_mode="official"
    )

    start_time = time.time()
    result = searcher.search("test query", max_retries=2, retry_base_delay=0.5)
    elapsed = time.time() - start_time

    print(f"\n耗时: {elapsed:.1f}s")
    print(f"错误存在: {'error' in result}")
    print(f"重试次数: {result.get('retries_attempted', 0)}")
    print(f"重试成功: {result.get('retry_successful', False)}")

    # 验证
    if 'error' in result and result.get('retries_attempted') == 2 and not result.get('retry_successful'):
        print("✅ 网络超时重试测试通过")
        return True
    else:
        print("❌ 网络超时重试测试失败")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Grok-Search 重试机制测试套件")
    print("=" * 60)
    print()

    results = []

    # 运行测试
    results.append(("错误分类", test_error_classification()))
    results.append(("延迟计算", test_delay_calculation()))
    results.append(("Retry-After 响应头", test_retry_after_header()))
    results.append(("方法签名", test_method_signature()))
    results.append(("网络超时重试", test_network_timeout()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")

    print(f"\n总计: {passed}/{total} 通过 ({passed/total*100:.0f}%)")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
