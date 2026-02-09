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
