---
name: grok-search
description: "Advanced semantic web search powered by Grok-4.1. Provides comprehensive research with real-time information, source citations, and analytical synthesis. Use when: (1) Need competitive analysis or market intelligence, (2) Require synthesis across multiple sources with expert analysis, (3) Basic WebSearch returns too many irrelevant results, (4) Researching patents, industry trends, or technical topics, (5) Need social media sentiment analysis, (6) Want analytical insights alongside factual data. Superior to basic search for complex queries requiring deep understanding and multi-source synthesis."
---

# Grok Search

Advanced semantic search using Grok-4.1 model for comprehensive research and analysis.

## Overview

Grok Search leverages the Grok-4.1 model's superior semantic understanding and real-time web access to provide deep, synthesized research results. Unlike basic search tools, Grok excels at understanding context, connecting disparate information, and providing analytical insights alongside factual data.

**Key advantages:**
- **Semantic understanding** - Analyzes query intent, not just keywords
- **Intelligent tool selection** - Automatically chooses optimal tools (web_search, x_search, code_execution, etc.)
- **Multi-source synthesis** - Combines insights from web, social media, and other sources
- **Real-time access** - Current information with source citations
- **Parallel search capability** - Multi-path concurrent search for complex queries

## Quick Start

### Using the Skill (Recommended)

Basic usage:
```
grok-search What are the latest AI agent trends in 2026?
```

With optional parameters:
```
grok-search What are the latest AI agent trends in 2026? mode=summary api_mode=reverse_proxy
```

### Direct Script Usage

For structured research reports:
```bash
python3 scripts/grok_search.py "Compare Notion vs Obsidian for team collaboration in 2026"
```

For analytical synthesis:
```bash
python3 scripts/grok_search.py "AI agent framework trends" --mode summary
```

For interactive research:
```bash
python3 scripts/grok_search.py --interactive
```

## Parameters

- **query** (required): Your search query or research question
- **mode** (optional):
  - `report` (default): Structured reports with executive summary, key findings, and complete source list
  - `summary`: Grok's analytical synthesis with insights
- **api_mode** (optional): `official` or `reverse_proxy` (see api_reference.md for details)

## Usage Modes

### Report Mode (Default)
Returns structured reports with executive summary, key findings with sources, detailed analysis by theme, and complete source list. Use for comprehensive research, documentation, and sharing with stakeholders.

### Summary Mode
Returns Grok's analytical synthesis with insights and source URLs. Use for quick insights, expert analysis, and when you need Grok's perspective.

### Interactive Mode
Multi-turn conversation for iterative refinement and follow-up questions. Use for exploratory research, drilling down into specific areas, and complex investigations.

---

## 🔀 Parallel Search Strategy (NEW)

### Important Note

**Parallel search is NOT automatically executed by the grok-search skill itself.** Instead, this strategy is a **guideline for the main Claude Code agent** to manually decompose queries and launch multiple grok-search subagents in parallel.

### When to Use Parallel Search

When you (the main agent) detect queries matching specific patterns, you should manually decompose them into sub-queries and launch multiple subagents using the Task tool with `subagent_type="general-purpose"`, each calling the grok-search skill.

### Query Classification & Execution Strategy

#### Strategy A: Independent Multi-Topic (Pure Parallel) ✅

**Trigger patterns:**
- "分别介绍 A、B、C"
- "Introduce A, B, and C separately"
- "各自的特点" / "each of their features"
- "分别分析" / "analyze separately"

**Execution:**
```
User: "分别介绍 Rust、Go、Python 的特点"

Parallel decomposition:
├─ Subagent 1: "Rust 编程语言的核心特点和优势"
├─ Subagent 2: "Go 编程语言的核心特点和优势"
└─ Subagent 3: "Python 编程语言的核心特点和优势"

Main agent: Simple aggregation of 3 independent results
```

**Information loss risk:** 🟢 Low (queries are truly independent)

---

#### Strategy B: Multi-Dimension Analysis (Pure Parallel) ✅

**Trigger patterns:**
- "全面分析 X" / "comprehensive analysis of X"
- "多维度分析" / "multi-dimensional analysis"
- "深入分析" / "in-depth analysis"
- "从...角度分析" / "analyze from ... perspectives"

**Execution:**
```
User: "全面分析 Rust：性能、生态、学习曲线、应用场景"

Parallel decomposition:
├─ Subagent 1: "Rust 的性能特点和基准测试"
├─ Subagent 2: "Rust 生态系统和库支持现状"
├─ Subagent 3: "Rust 学习曲线和入门难度分析"
└─ Subagent 4: "Rust 的典型应用场景和案例"

Main agent: Structured integration by dimension
```

**Information loss risk:** 🟡 Medium (dimensions may have cross-references)

---

#### Strategy C: Comparison Query (Hybrid Parallel) ⚠️

**Trigger patterns:**
- "对比 A 和 B" / "compare A and B"
- "A vs B"
- "A 和 B 的区别" / "differences between A and B"
- "哪个更好" / "which is better"

**Execution (Hybrid Strategy):**
```
User: "对比 Claude Sonnet 4.5 和 GPT-4o 的能力"

Hybrid parallel decomposition:
├─ Subagent 1: "Claude Sonnet 4.5 vs GPT-4o 对比评测和用户反馈" ← Preserve original comparison
├─ Subagent 2: "Claude Sonnet 4.5 的核心能力、特点和优势"      ← Detailed A
├─ Subagent 3: "GPT-4o 的核心能力、特点和优势"                ← Detailed B
└─ Subagent 4: "Claude Sonnet 4.5 vs GPT-4o 在实际应用中的表现对比" ← Supplementary comparison

Main agent synthesis:
1. Prioritize Subagent 1 & 4 comparison results (most direct)
2. Use Subagent 2 & 3 for depth and details
3. Cross-validate for consistency
4. Generate comprehensive comparison report
```

**Why hybrid?**
- Preserves direct comparison articles from search engines
- Adds detailed individual analysis for depth
- Minimizes information loss from query decomposition

**Information loss risk:** 🟡 Medium (mitigated by preserving original query)

---

#### Strategy D: Sequential Query (Serial Only) ❌

**Trigger patterns:**
- "先...然后..." / "first...then..."
- "首先...接着..." / "firstly...next..."
- "基于...进行..." / "based on...do..."
- "找出...并对比..." / "find...and compare..."

**Execution (Serial):**
```
User: "找出 2024 年最流行的 3 个 AI 模型，然后对比它们的能力"

Step 1 (Serial): Search "2024 年最流行的 AI 模型"
         Result: Claude Sonnet 4.5, GPT-4o, Gemini 2.0

Step 2 (Parallel based on Step 1):
├─ Subagent 1: "Claude Sonnet 4.5 vs GPT-4o vs Gemini 2.0 对比"
├─ Subagent 2: "Claude Sonnet 4.5 核心能力"
├─ Subagent 3: "GPT-4o 核心能力"
└─ Subagent 4: "Gemini 2.0 核心能力"

Step 3: Main agent comprehensive comparison
```

**Information loss risk:** 🔴 High if forced to parallel (dependencies broken)

---

### Implementation Guidelines

#### 1. Query Analysis Phase

```
When user submits a query:

1. Detect query type:
   - Check for independent multi-topic patterns → Strategy A
   - Check for multi-dimension patterns → Strategy B
   - Check for comparison patterns → Strategy C
   - Check for sequential patterns → Strategy D
   - Default → Single query (no parallelization)

2. Validate parallelizability:
   - Are sub-queries truly independent?
   - Will decomposition lose critical context?
   - Is the overhead worth it? (minimum 2 sub-queries)

3. Decide execution mode:
   - Pure parallel (A, B)
   - Hybrid parallel (C)
   - Serial (D)
   - Single query (default)
```

#### 2. Parallel Execution Phase

```
For parallel execution (Main Agent's responsibility):

1. Decompose query into 2-5 sub-queries
   - Each sub-query must be self-contained
   - Include necessary context in each sub-query
   - Avoid overlap to minimize redundancy

2. Launch subagents in parallel (single message with multiple Task calls):

   # Example: Main agent launches parallel searches
   Task(subagent_type="general-purpose",
        prompt="Use the grok-search skill to search: {sub_query_1}",
        description="Search task 1",
        name="searcher-1")
   Task(subagent_type="general-purpose",
        prompt="Use the grok-search skill to search: {sub_query_2}",
        description="Search task 2",
        name="searcher-2")
   ...

3. Wait for all subagents to complete
   - Collect all results
   - Check for errors or incomplete results
```

#### 3. Synthesis Phase

```
After collecting all results:

1. For Strategy A (Independent):
   - Simple aggregation
   - Organize by topic
   - Remove duplicates

2. For Strategy B (Multi-dimension):
   - Structured integration by dimension
   - Identify cross-references
   - Build coherent narrative

3. For Strategy C (Comparison):
   - Prioritize direct comparison results
   - Use detailed results for depth
   - Cross-validate for consistency
   - Generate comparison table/summary

4. Quality checks:
   - Identify contradictions
   - Check for missing information
   - Validate source citations
```

#### 4. Context Preservation Techniques

**For comparison queries (Strategy C):**
```
✅ Good sub-query design (includes context):
- "Rust 相比 Go 的性能优势和劣势"
- "Go 相比 Rust 的性能优势和劣势"

❌ Bad sub-query design (loses context):
- "Rust 性能"
- "Go 性能"
```

**For multi-dimension queries (Strategy B):**
```
✅ Good sub-query design (self-contained):
- "Rust 的性能特点和基准测试结果"
- "Rust 生态系统的成熟度和库支持情况"

❌ Bad sub-query design (too vague):
- "Rust 性能"
- "Rust 生态"
```

---

### Performance Expectations

| Strategy | Serial Time | Parallel Time | Speedup | Information Loss |
|----------|-------------|---------------|---------|------------------|
| A (Independent) | 30s (3 queries) | ~12s | 2.5x | 🟢 Minimal |
| B (Multi-dim) | 40s (4 queries) | ~15s | 2.7x | 🟡 Low-Medium |
| C (Comparison) | 40s (4 queries) | ~15s | 2.7x | 🟡 Low (mitigated) |
| D (Sequential) | 50s (2 phases) | N/A | 1x | 🔴 High if parallel |

**Note:** Actual speedup depends on API response time, network latency, and Claude Code's subagent scheduling overhead.

---

### Constraints & Limitations

1. **Maximum parallel subagents:** 5 (Claude Code limit)
2. **Minimum sub-queries for parallelization:** 2
3. **Subagent communication:** Subagents cannot see each other's results during execution
4. **Cost:** Each subagent consumes API tokens independently
5. **Complexity overhead:** Parallel execution adds orchestration complexity

---

### Example Workflows

#### Example 1: Independent Multi-Topic (Strategy A)

```
User: "分别介绍 Rust、Go、Python 的特点"

Detection: Independent multi-topic pattern detected
Strategy: A (Pure Parallel)

Execution:
[Main Agent] Decomposing query into 3 independent sub-queries...
[Main Agent] Launching 3 parallel subagents...

├─ [Subagent 1] Searching: "Rust 编程语言的核心特点和优势"
├─ [Subagent 2] Searching: "Go 编程语言的核心特点和优势"
└─ [Subagent 3] Searching: "Python 编程语言的核心特点和优势"

[Main Agent] All subagents completed. Aggregating results...

Output:
# Rust、Go、Python 特点对比

## Rust
[Subagent 1 results]

## Go
[Subagent 2 results]

## Python
[Subagent 3 results]
```

#### Example 2: Comparison Query (Strategy C)

```
User: "对比 Claude Sonnet 4.5 和 GPT-4o 的能力"

Detection: Comparison pattern detected
Strategy: C (Hybrid Parallel)

Execution:
[Main Agent] Using hybrid parallel strategy to preserve comparison context...
[Main Agent] Launching 4 parallel subagents...

├─ [Subagent 1] Searching: "Claude Sonnet 4.5 vs GPT-4o 对比评测"
├─ [Subagent 2] Searching: "Claude Sonnet 4.5 核心能力和特点"
├─ [Subagent 3] Searching: "GPT-4o 核心能力和特点"
└─ [Subagent 4] Searching: "Claude Sonnet 4.5 vs GPT-4o 用户反馈"

[Main Agent] All subagents completed. Synthesizing comparison report...
[Main Agent] Prioritizing direct comparison results...
[Main Agent] Cross-validating with detailed analysis...

Output:
# Claude Sonnet 4.5 vs GPT-4o 能力对比

## 执行摘要
[Synthesized from Subagent 1 & 4]

## 详细对比
| 维度 | Claude Sonnet 4.5 | GPT-4o |
|------|-------------------|--------|
| ... | [From Subagent 2] | [From Subagent 3] |

## 用户反馈
[From Subagent 4]

## 结论
[Synthesized analysis]
```

#### Example 3: Sequential Query (Strategy D)

```
User: "找出 2024 年最流行的 3 个 AI 模型，然后对比它们的能力"

Detection: Sequential pattern detected
Strategy: D (Serial)

Execution:
[Main Agent] Sequential query detected. Executing in phases...

Phase 1 (Serial):
[Main Agent] Searching: "2024 年最流行的 AI 模型"
[Main Agent] Result: Claude Sonnet 4.5, GPT-4o, Gemini 2.0

Phase 2 (Parallel based on Phase 1):
[Main Agent] Launching 4 parallel subagents for comparison...

├─ [Subagent 1] Searching: "Claude Sonnet 4.5 vs GPT-4o vs Gemini 2.0"
├─ [Subagent 2] Searching: "Claude Sonnet 4.5 核心能力"
├─ [Subagent 3] Searching: "GPT-4o 核心能力"
└─ [Subagent 4] Searching: "Gemini 2.0 核心能力"

[Main Agent] Synthesizing comprehensive comparison...

Output:
# 2024 年最流行 AI 模型对比

## 最流行的 3 个模型
1. Claude Sonnet 4.5
2. GPT-4o
3. Gemini 2.0

## 能力对比
[Comprehensive comparison table and analysis]
```

---

## Reference Documentation

Load these references as needed to optimize your research workflow:

### [search_patterns.md](references/search_patterns.md)
Query templates, use cases, workflows, and best practices for different research scenarios.

**Load when you need:**
- Guidance on crafting effective queries for specific scenarios (competitive analysis, patents, technical research)
- Example workflows for common research tasks
- Query refinement patterns and optimization techniques
- Best practices for effective research

### [tool_triggers.md](references/tool_triggers.md)
How Grok automatically selects tools (web_search, x_search, code_execution, etc.) based on query patterns.

**Load when you need:**
- Understanding how Grok chooses tools for different query types
- Debugging tool selection behavior
- Learning which query patterns trigger specific Grok capabilities

### [api_reference.md](references/api_reference.md)
Technical API documentation, configuration details, and troubleshooting.

**Load when you need:**
- Setting up API credentials and configuration
- Understanding API modes (official vs reverse_proxy)
- Troubleshooting connection or authentication issues
- Advanced options (temperature, token limits, output saving)
- Technical details about request/response format

## Quick Troubleshooting

**"API credentials not found"**
→ See api_reference.md "Configuration Setup" section

**"Connection timeout"**
→ See api_reference.md "Troubleshooting" section

**Poor results quality**
→ See search_patterns.md "Query Refinement Patterns"

**Need query examples**
→ See search_patterns.md for templates by domain

**Parallel search not triggering**
→ Check if query matches trigger patterns in "Parallel Search Strategy" section
