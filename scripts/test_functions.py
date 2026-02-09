#!/usr/bin/env python3
"""
Grok-Search 功能测试套件
测试 grok_search.py 的核心功能
"""

import sys
import time
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from grok_search import (
    GrokSearcher,
    _is_retryable_error,
    _get_retry_delay,
    _format_output_with_sources,
    _get_local_time_info,
    _needs_time_context
)
import requests


def test_time_context_detection():
    """测试时间上下文检测"""
    print("=" * 60)
    print("测试 1: 时间上下文检测")
    print("=" * 60)

    test_cases = [
        ("What is the latest news?", True, "latest"),
        ("Current AI trends", True, "current"),
        ("今天的天气", True, "今天"),
        ("最新的技术", True, "最新"),
        ("What is Python?", False, "无时间关键词"),
        ("How to code?", False, "无时间关键词"),
    ]

    passed = 0
    failed = 0

    for query, expected, desc in test_cases:
        result = _needs_time_context(query)
        if result == expected:
            print(f"✅ {desc}: needs_time={result}")
            passed += 1
        else:
            print(f"❌ {desc}: needs_time={result} (expected={expected})")
            failed += 1

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_source_formatting():
    """测试来源格式化"""
    print("\n" + "=" * 60)
    print("测试 2: 来源格式化")
    print("=" * 60)

    # 测试用例 1: 有来源
    content1 = "This is a test response."
    sources1 = ["https://example.com", "https://test.com"]
    result1 = _format_output_with_sources(content1, sources1)

    if "## 📚 Sources" in result1 and "example.com" in result1:
        print("✅ 有来源时正确添加 Sources 章节")
        passed1 = True
    else:
        print("❌ 有来源时未正确添加 Sources 章节")
        passed1 = False

    # 测试用例 2: 无来源
    content2 = "This is a test response."
    sources2 = []
    result2 = _format_output_with_sources(content2, sources2)

    if "⚠️ **Note**" in result2 and "internal knowledge" in result2:
        print("✅ 无来源时正确添加警告信息")
        passed2 = True
    else:
        print("❌ 无来源时未正确添加警告信息")
        passed2 = False

    # 测试用例 3: 内容中已有 URL
    content3 = "Check https://example.com for more info."
    sources3 = []
    result3 = _format_output_with_sources(content3, sources3)

    if "Verified with" in result3 and "external source" in result3:
        print("✅ 内容中有 URL 时正确识别")
        passed3 = True
    else:
        print("❌ 内容中有 URL 时未正确识别")
        passed3 = False

    print(f"\n结果: {sum([passed1, passed2, passed3])} 通过, {3 - sum([passed1, passed2, passed3])} 失败")
    return passed1 and passed2 and passed3


def test_credentials_loading():
    """测试凭证加载逻辑"""
    print("\n" + "=" * 60)
    print("测试 3: 凭证加载")
    print("=" * 60)

    # 测试直接传参
    try:
        searcher = GrokSearcher(
            api_key="test_key",
            base_url="https://test.com",
            api_mode="official"
        )

        if searcher.api_key == "test_key" and searcher.base_url == "https://test.com" and searcher.api_mode == "official":
            print("✅ 直接传参加载凭证成功")
            return True
        else:
            print("❌ 直接传参加载凭证失败")
            return False
    except Exception as e:
        print(f"❌ 凭证加载异常: {e}")
        return False


def test_search_instruction_building():
    """测试搜索指令构建"""
    print("\n" + "=" * 60)
    print("测试 4: 搜索指令构建")
    print("=" * 60)

    searcher = GrokSearcher(
        api_key="test",
        base_url="https://test.com",
        api_mode="reverse_proxy"
    )

    test_cases = [
        ("generate an image", "image_generation", "图片生成"),
        ("calculate 2+2", "code_execution", "代码执行"),
        ("trending on twitter", "x_search", "社交媒体"),
        ("compare React vs Vue", "web_search", "对比研究"),
    ]

    passed = 0
    failed = 0

    for query, expected_tool, desc in test_cases:
        instruction = searcher._build_search_instruction(query)
        if expected_tool in instruction:
            print(f"✅ {desc}: 包含 {expected_tool}")
            passed += 1
        else:
            print(f"❌ {desc}: 未包含 {expected_tool}")
            failed += 1

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_iterative_prompt_building():
    """测试迭代研究提示词构建"""
    print("\n" + "=" * 60)
    print("测试 5: 迭代研究提示词")
    print("=" * 60)

    searcher = GrokSearcher(
        api_key="test",
        base_url="https://test.com",
        api_mode="reverse_proxy"
    )

    # 测试深度研究模式
    prompt_depth = searcher._build_iterative_search_prompt("test query", enable_depth=True)
    if "DEEP RESEARCH MODE" in prompt_depth and "Phase 1" in prompt_depth:
        print("✅ 深度研究模式提示词正确")
        passed1 = True
    else:
        print("❌ 深度研究模式提示词错误")
        passed1 = False

    # 测试广度优先模式
    prompt_breadth = searcher._build_iterative_search_prompt("test query", enable_depth=False)
    if "BREADTH-FIRST" in prompt_breadth and "Strategy" in prompt_breadth:
        print("✅ 广度优先模式提示词正确")
        passed2 = True
    else:
        print("❌ 广度优先模式提示词错误")
        passed2 = False

    print(f"\n结果: {sum([passed1, passed2])} 通过, {2 - sum([passed1, passed2])} 失败")
    return passed1 and passed2


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Grok-Search 功能测试套件")
    print("=" * 60)
    print()

    results = []

    # 运行功能测试
    results.append(("时间上下文检测", test_time_context_detection()))
    results.append(("来源格式化", test_source_formatting()))
    results.append(("凭证加载", test_credentials_loading()))
    results.append(("搜索指令构建", test_search_instruction_building()))
    results.append(("迭代研究提示词", test_iterative_prompt_building()))

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
        print("\n🎉 所有功能测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
