#!/usr/bin/env python3
"""
Grok Parallel Search - Automatic query decomposition and parallel execution
Detects query patterns and executes multiple searches concurrently
"""

import os
import sys
import json
import argparse
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess


def detect_query_pattern(query: str) -> Tuple[str, List[str]]:
    """
    Detect query pattern and decompose into sub-queries

    Returns:
        (pattern_type, sub_queries)
        pattern_type: "comparison", "multi_topic", "multi_dimension", "sequential", "single"
    """
    query_lower = query.lower()

    # Pattern 1: Comparison queries
    comparison_patterns = [
        r'对比\s*(.+?)\s*和\s*(.+?)(?:的|$)',
        r'比较\s*(.+?)\s*和\s*(.+?)(?:的|$)',
        r'(.+?)\s*vs\s*(.+?)(?:\s|$)',
        r'(.+?)\s*versus\s*(.+?)(?:\s|$)',
        r'compare\s+(.+?)\s+and\s+(.+?)(?:\s|$)',
        r'(.+?)\s*和\s*(.+?)\s*的区别',
        r'difference\s+between\s+(.+?)\s+and\s+(.+?)(?:\s|$)',
    ]

    for pattern in comparison_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            topic_a = match.group(1).strip()
            topic_b = match.group(2).strip()

            # Extract the aspect being compared (e.g., "性能", "能力")
            aspect = ""
            aspect_match = re.search(r'(?:的|in|for)\s*(.+?)(?:\s|$)', query[match.end():])
            if aspect_match:
                aspect = aspect_match.group(1).strip()

            # Hybrid parallel strategy for comparison
            sub_queries = [
                f"{topic_a} vs {topic_b} {aspect} 对比评测和用户反馈",  # Preserve original comparison
                f"{topic_a} 的{aspect}核心特点和优势",  # Detailed A
                f"{topic_b} 的{aspect}核心特点和优势",  # Detailed B
            ]

            # Add supplementary comparison if aspect is specified
            if aspect:
                sub_queries.append(f"{topic_a} vs {topic_b} 在{aspect}方面的实际应用对比")

            return ("comparison", sub_queries)

    # Pattern 2: Independent multi-topic queries
    multi_topic_patterns = [
        r'分别介绍\s*(.+)',
        r'各自(?:的)?(.+)',
        r'分别分析\s*(.+)',
        r'introduce\s+(.+?)\s+separately',
        r'explain\s+(.+?)\s+individually',
    ]

    for pattern in multi_topic_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            topics_str = match.group(1).strip()
            # Split by common delimiters
            topics = re.split(r'[,，、和及and]', topics_str)
            topics = [t.strip() for t in topics if t.strip()]

            if len(topics) >= 2:
                # Extract the aspect (e.g., "特点", "features")
                aspect = ""
                aspect_match = re.search(r'(?:的|of)\s*(.+?)(?:\s|$)', topics[-1])
                if aspect_match:
                    aspect = aspect_match.group(1).strip()
                    topics[-1] = topics[-1].replace(f"的{aspect}", "").replace(f"of {aspect}", "").strip()

                sub_queries = [f"{topic} 的{aspect}核心特点和优势" if aspect else f"{topic} 的核心特点和优势"
                              for topic in topics]
                return ("multi_topic", sub_queries)

    # Pattern 3: Multi-dimension analysis
    multi_dim_patterns = [
        r'全面分析\s*(.+?)[:：]\s*(.+)',
        r'多维度分析\s*(.+?)[:：]\s*(.+)',
        r'深入分析\s*(.+?)[:：]\s*(.+)',
        r'comprehensive\s+analysis\s+of\s+(.+?)[:：]\s*(.+)',
        r'analyze\s+(.+?)\s+from\s+(.+)',
    ]

    for pattern in multi_dim_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            topic = match.group(1).strip()
            dimensions_str = match.group(2).strip()
            dimensions = re.split(r'[,，、和及and]', dimensions_str)
            dimensions = [d.strip() for d in dimensions if d.strip()]

            if len(dimensions) >= 2:
                sub_queries = [f"{topic} 的{dim}特点和分析" for dim in dimensions]
                return ("multi_dimension", sub_queries)

    # Pattern 4: Sequential queries (should NOT be parallelized)
    sequential_patterns = [
        r'先.+然后',
        r'首先.+接着',
        r'基于.+进行',
        r'找出.+并',
        r'first.+then',
        r'firstly.+next',
    ]

    for pattern in sequential_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return ("sequential", [query])

    # Default: single query
    return ("single", [query])


def run_single_search(query: str, mode: str = "report", **kwargs) -> Dict[str, Any]:
    """
    Run a single grok search using the existing grok_search.py script

    Args:
        query: Search query
        mode: Output mode (report/summary)
        **kwargs: Additional arguments to pass to grok_search.py

    Returns:
        Dict with search results
    """
    script_dir = Path(__file__).parent
    grok_search_script = script_dir / "grok_search.py"

    # Build command
    cmd = [sys.executable, str(grok_search_script), query, "--mode", mode]

    # Add optional arguments
    if kwargs.get("api_key"):
        cmd.extend(["--api-key", kwargs["api_key"]])
    if kwargs.get("base_url"):
        cmd.extend(["--base-url", kwargs["base_url"]])
    if kwargs.get("api_mode"):
        cmd.extend(["--api-mode", kwargs["api_mode"]])
    if kwargs.get("temperature"):
        cmd.extend(["--temperature", str(kwargs["temperature"])])
    if kwargs.get("max_tokens"):
        cmd.extend(["--max-tokens", str(kwargs["max_tokens"])])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # 3 minutes timeout
        )

        if result.returncode == 0:
            return {
                "query": query,
                "content": result.stdout,
                "success": True
            }
        else:
            return {
                "query": query,
                "content": result.stderr or result.stdout,
                "success": False,
                "error": f"Search failed with return code {result.returncode}"
            }
    except subprocess.TimeoutExpired:
        return {
            "query": query,
            "content": "",
            "success": False,
            "error": "Search timed out after 3 minutes"
        }
    except Exception as e:
        return {
            "query": query,
            "content": "",
            "success": False,
            "error": str(e)
        }


def parallel_search(sub_queries: List[str], mode: str = "report", max_workers: int = 5, **kwargs) -> List[Dict[str, Any]]:
    """
    Execute multiple searches in parallel

    Args:
        sub_queries: List of sub-queries to search
        mode: Output mode
        max_workers: Maximum number of parallel workers (default: 5, Claude Code limit)
        **kwargs: Additional arguments

    Returns:
        List of search results
    """
    results = []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(sub_queries))) as executor:
        # Submit all searches
        future_to_query = {
            executor.submit(run_single_search, query, mode, **kwargs): query
            for query in sub_queries
        }

        # Collect results as they complete
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                result = future.result()
                results.append(result)
                print(f"✓ Completed: {query[:50]}...", file=sys.stderr)
            except Exception as e:
                results.append({
                    "query": query,
                    "content": "",
                    "success": False,
                    "error": str(e)
                })
                print(f"✗ Failed: {query[:50]}... - {e}", file=sys.stderr)

    return results


def synthesize_results(results: List[Dict[str, Any]], pattern: str, original_query: str) -> str:
    """
    Synthesize multiple search results into a coherent response

    Args:
        results: List of search results
        pattern: Query pattern type
        original_query: Original user query

    Returns:
        Synthesized response
    """
    output = []

    # Header
    output.append(f"# 并行搜索结果：{original_query}\n")
    output.append(f"**搜索策略**: {pattern.upper()}\n")
    output.append(f"**并行查询数**: {len(results)}\n")
    output.append(f"**成功**: {sum(1 for r in results if r['success'])}/{len(results)}\n")
    output.append("\n---\n\n")

    # Strategy-specific synthesis
    if pattern == "comparison":
        output.append("## 对比分析\n\n")

        # Prioritize comparison results (first query)
        if results and results[0]['success']:
            output.append("### 综合对比\n\n")
            output.append(results[0]['content'])
            output.append("\n\n")

        # Add detailed analysis from other queries
        if len(results) > 1:
            output.append("### 详细分析\n\n")
            for i, result in enumerate(results[1:], 1):
                if result['success']:
                    output.append(f"#### 维度 {i}\n\n")
                    output.append(result['content'])
                    output.append("\n\n")

    elif pattern == "multi_topic":
        output.append("## 分主题分析\n\n")

        for i, result in enumerate(results, 1):
            if result['success']:
                output.append(f"### 主题 {i}: {result['query'][:50]}...\n\n")
                output.append(result['content'])
                output.append("\n\n---\n\n")

    elif pattern == "multi_dimension":
        output.append("## 多维度分析\n\n")

        for i, result in enumerate(results, 1):
            if result['success']:
                output.append(f"### 维度 {i}: {result['query'][:50]}...\n\n")
                output.append(result['content'])
                output.append("\n\n---\n\n")

    else:
        # Default: just concatenate
        for i, result in enumerate(results, 1):
            if result['success']:
                output.append(f"## 结果 {i}\n\n")
                output.append(result['content'])
                output.append("\n\n---\n\n")

    # Error summary
    failed = [r for r in results if not r['success']]
    if failed:
        output.append("\n## ⚠️ 部分查询失败\n\n")
        for result in failed:
            output.append(f"- **查询**: {result['query'][:50]}...\n")
            output.append(f"  **错误**: {result.get('error', 'Unknown error')}\n")

    return "".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Grok Parallel Search - Automatic query decomposition and parallel execution"
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument("--mode", choices=["report", "summary"], default="report",
                       help="Output mode")
    parser.add_argument("--api-key", help="Grok API key")
    parser.add_argument("--base-url", help="Grok API base URL")
    parser.add_argument("--api-mode", choices=["official", "reverse_proxy"],
                       help="API mode")
    parser.add_argument("--temperature", type=float, default=0.7,
                       help="Model temperature")
    parser.add_argument("--max-tokens", type=int, default=4000,
                       help="Maximum response tokens")
    parser.add_argument("--max-workers", type=int, default=5,
                       help="Maximum parallel workers (default: 5)")
    parser.add_argument("--force-single", action="store_true",
                       help="Force single query mode (disable parallel)")
    parser.add_argument("--output", "-o", help="Save output to file")

    args = parser.parse_args()

    # Detect query pattern
    pattern, sub_queries = detect_query_pattern(args.query)

    print(f"🔍 Query Pattern: {pattern.upper()}", file=sys.stderr)
    print(f"📊 Sub-queries: {len(sub_queries)}", file=sys.stderr)

    # Force single mode or sequential pattern
    if args.force_single or pattern == "sequential" or pattern == "single":
        print("⚡ Executing single search...", file=sys.stderr)
        result = run_single_search(
            args.query,
            args.mode,
            api_key=args.api_key,
            base_url=args.base_url,
            api_mode=args.api_mode,
            temperature=args.temperature,
            max_tokens=args.max_tokens
        )

        if result['success']:
            output = result['content']
        else:
            print(f"❌ Search failed: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)
    else:
        # Parallel execution
        print(f"🚀 Launching {len(sub_queries)} parallel searches...", file=sys.stderr)
        for i, sq in enumerate(sub_queries, 1):
            print(f"  {i}. {sq}", file=sys.stderr)
        print("", file=sys.stderr)

        results = parallel_search(
            sub_queries,
            args.mode,
            args.max_workers,
            api_key=args.api_key,
            base_url=args.base_url,
            api_mode=args.api_mode,
            temperature=args.temperature,
            max_tokens=args.max_tokens
        )

        print("\n✅ All searches completed. Synthesizing results...", file=sys.stderr)
        output = synthesize_results(results, pattern, args.query)

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"\n💾 Output saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
