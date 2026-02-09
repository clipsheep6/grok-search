#!/usr/bin/env python3
"""
Grok Search Script - Advanced semantic search using Grok-4.1 model
Supports both single-query and multi-turn conversation modes
"""

import os
import sys
import json
import argparse
import re
import time
import random
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import requests


def _get_local_time_info() -> str:
    """Get local time information for time-sensitive queries"""
    try:
        local_tz = datetime.now().astimezone().tzinfo
        local_now = datetime.now(local_tz)
    except Exception:
        local_now = datetime.now(timezone.utc)

    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return (
        f"[Current Time Context]\n"
        f"- Date: {local_now.strftime('%Y-%m-%d')} ({weekdays[local_now.weekday()]})\n"
        f"- Time: {local_now.strftime('%H:%M:%S')}\n"
    )


def _needs_time_context(query: str) -> bool:
    """Detect if query needs time context"""
    keywords = [
        "current", "now", "today", "tomorrow", "yesterday",
        "this week", "last week", "next week",
        "latest", "recent", "recently", "up-to-date",
        "当前", "现在", "今天", "明天", "昨天",
        "最新", "最近", "近期", "实时"
    ]
    query_lower = query.lower()
    return any(kw in query_lower or kw in query for kw in keywords)


def _format_output_with_sources(content: str, sources: List[str]) -> str:
    """Format output to ensure sources are visible and transparent"""
    # Extract URLs from content (for reverse proxy mode where sources are embedded)
    import re
    content_urls = re.findall(r'https?://[^\s\)]+', content)

    # Check for Grok citation markers (reverse proxy format)
    has_grok_citations = bool(re.search(r'<grok:render.*?citation', content))

    # Merge all sources
    all_sources = list(set(sources + content_urls))

    # If sources exist but not visible in content, append them
    has_urls_in_content = bool(re.search(r'https?://', content))

    if sources and not has_urls_in_content:
        content += "\n\n## 📚 Sources (from API)\n"
        # Limit to 10 sources for readability
        for i, url in enumerate(sources[:10], 1):
            content += f"{i}. {url}\n"
        if len(sources) > 10:
            content += f"... and {len(sources) - 10} more sources\n"

    # Add transparency badge
    source_count = len(all_sources)

    # Consider Grok citations as valid sources even without URLs
    if source_count == 0 and not has_grok_citations:
        content += "\n\n⚠️ **Note**: This response is based on model's internal knowledge without external web sources. Please verify critical information independently."
    elif has_grok_citations and source_count == 0:
        # Count citation markers
        citation_count = len(re.findall(r'<grok:render.*?citation', content))
        content += f"\n\n✅ **Search performed with {citation_count} citation(s)** (reverse proxy format)"
    else:
        content += f"\n\n✅ **Verified with {source_count} external source(s)**"

    return content


def _is_retryable_error(exception: requests.exceptions.RequestException) -> bool:
    """
    Determine if an error is transient and should be retried.

    Args:
        exception: The caught RequestException

    Returns:
        True if error is retryable, False otherwise
    """
    # Network-level errors are always retryable
    if isinstance(exception, (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError
    )):
        return True

    # Check HTTP status codes for HTTPError
    if isinstance(exception, requests.exceptions.HTTPError):
        if hasattr(exception, 'response') and exception.response is not None:
            status_code = exception.response.status_code

            # 5xx errors are retryable (server issues)
            if status_code >= 500:
                return True

            # 429 is retryable (rate limiting)
            if status_code == 429:
                return True

            # 4xx errors (except 429) are NOT retryable
            if 400 <= status_code < 500:
                return False

    # All other errors are not retryable by default
    return False


def _get_retry_delay(
    attempt: int,
    exception: requests.exceptions.RequestException,
    base_delay: float = 1.0
) -> float:
    """
    Calculate retry delay with exponential backoff and jitter.

    Args:
        attempt: Current retry attempt number (0-indexed)
        exception: The caught exception (to check for Retry-After header)
        base_delay: Base delay in seconds

    Returns:
        Delay in seconds before next retry
    """
    # Check for Retry-After header (429 responses)
    if isinstance(exception, requests.exceptions.HTTPError):
        if hasattr(exception, 'response') and exception.response is not None:
            retry_after = exception.response.headers.get('Retry-After')
            if retry_after:
                try:
                    # Try parsing as integer (seconds)
                    return float(retry_after)
                except ValueError:
                    # Could be HTTP-date format, but we'll fall back to exponential
                    pass

    # Exponential backoff: base_delay * 2^attempt
    delay = base_delay * (2 ** attempt)

    # Add jitter (0-10% of delay) to prevent thundering herd
    jitter = random.uniform(0, 0.1 * delay)

    return delay + jitter


class GrokSearcher:
    """Handles Grok API interactions for advanced search"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, api_mode: Optional[str] = None):
        """Initialize with API credentials from args or config"""
        # Priority 1: Skill directory config (recommended)
        skill_dir = Path(__file__).parent.parent
        self.skill_config_file = skill_dir / "config.json"

        # Priority 2: Legacy home directory config (for backward compatibility)
        self.legacy_config_dir = Path.home() / ".grok"
        self.legacy_config_file = self.legacy_config_dir / "config.json"

        # Load or prompt for credentials
        self.api_key, self.base_url, self.api_mode = self._get_credentials(api_key, base_url, api_mode)

    def _normalize_base_url(self, base_url: str) -> str:
        """Normalize base URL by ensuring it ends with /v1"""
        if not base_url:
            return base_url

        # Remove trailing slashes
        base_url = base_url.rstrip('/')

        # Add /v1 if not present
        if not base_url.endswith('/v1'):
            base_url = f"{base_url}/v1"
            print(f"ℹ️  Auto-normalized base_url to: {base_url}", file=sys.stderr)

        return base_url

    def _get_credentials(self, api_key: Optional[str], base_url: Optional[str], api_mode: Optional[str]) -> tuple:
        """Get credentials from args, config file, or prompt user"""
        # Try arguments first
        if api_key and base_url and api_mode:
            base_url = self._normalize_base_url(base_url)
            return api_key, base_url, api_mode

        # Try environment variables
        env_key = os.getenv("GROK_API_KEY")
        env_url = os.getenv("GROK_BASE_URL")
        env_mode = os.getenv("GROK_API_MODE")
        if env_key and env_url and env_mode:
            env_url = self._normalize_base_url(env_url)
            return env_key, env_url, env_mode

        # Try skill directory config file (Priority 1)
        if self.skill_config_file.exists():
            with open(self.skill_config_file, 'r') as f:
                config = json.load(f)
                if config.get("api_key") and config.get("base_url") and config.get("api_mode"):
                    base_url = self._normalize_base_url(config["base_url"])
                    return config["api_key"], base_url, config["api_mode"]

        # Try legacy home directory config file (Priority 2 - backward compatibility)
        if self.legacy_config_file.exists():
            with open(self.legacy_config_file, 'r') as f:
                config = json.load(f)
                if config.get("api_key") and config.get("base_url") and config.get("api_mode"):
                    print(f"⚠️  Using legacy config from {self.legacy_config_file}", file=sys.stderr)
                    print(f"   Consider migrating to {self.skill_config_file}", file=sys.stderr)
                    base_url = self._normalize_base_url(config["base_url"])
                    return config["api_key"], base_url, config["api_mode"]

        # Check if running in interactive terminal
        if not sys.stdin.isatty():
            # Non-interactive environment - print configuration instructions and exit
            print("\n❌ Grok API credentials not found!", file=sys.stderr)
            print("\n📝 Please configure credentials using one of these methods:\n", file=sys.stderr)
            print("Method 1: Config File (Recommended)", file=sys.stderr)
            print(f"  Copy {self.skill_config_file.parent}/config.json.example to config.json", file=sys.stderr)
            print(f"  Edit {self.skill_config_file} with your credentials:", file=sys.stderr)
            print('  {', file=sys.stderr)
            print('    "api_key": "your-api-key",', file=sys.stderr)
            print('    "base_url": "https://api.x.ai/v1",', file=sys.stderr)
            print('    "api_mode": "official"  // or "reverse_proxy"', file=sys.stderr)
            print('  }', file=sys.stderr)
            print("", file=sys.stderr)
            print("Method 2: Environment Variables", file=sys.stderr)
            print("  export GROK_API_KEY='your-api-key'", file=sys.stderr)
            print("  export GROK_BASE_URL='https://api.x.ai/v1'", file=sys.stderr)
            print("  export GROK_API_MODE='official'  # or 'reverse_proxy'", file=sys.stderr)
            print("", file=sys.stderr)
            print("Method 3: Command Line Arguments", file=sys.stderr)
            print("  python3 grok_search.py 'query' --api-key 'key' --base-url 'url' --api-mode 'official'", file=sys.stderr)
            print("", file=sys.stderr)
            print("Method 4: Interactive Setup", file=sys.stderr)
            print("  Run this script in an interactive terminal to be prompted for credentials", file=sys.stderr)
            print("", file=sys.stderr)
            sys.exit(1)

        # Interactive terminal - prompt user and save
        print("Grok API credentials not found. Let's set them up!")
        print(f"\n📝 Configuration will be saved to: {self.skill_config_file}\n")

        api_key = input("API Key: ").strip()
        base_url = input("Base URL (default: https://api.x.ai/v1): ").strip()
        if not base_url:
            base_url = "https://api.x.ai/v1"

        # Always ask for mode - no auto-detection
        print("\nAPI Mode (REQUIRED):")
        print("  1. official - Standard API format with tool parameters")
        print("      Use for: Official xAI API, most third-party API providers")
        print("  2. reverse_proxy - Web-based reverse proxy (prompt triggers)")
        print("      Use for: Web interface reverse proxies that don't support tool parameters")

        while True:
            mode_choice = input("Select mode [1/2]: ").strip()
            if mode_choice in ["1", "2"]:
                api_mode = "official" if mode_choice == "1" else "reverse_proxy"
                break
            print("❌ Invalid choice. Please enter 1 or 2.")

        if not api_key or not base_url:
            print("❌ API Key and Base URL are required", file=sys.stderr)
            sys.exit(1)

        # Normalize base_url before saving
        base_url = self._normalize_base_url(base_url)

        # Save to skill directory config
        with open(self.skill_config_file, 'w') as f:
            json.dump({
                "api_key": api_key,
                "base_url": base_url,
                "api_mode": api_mode
            }, f, indent=2)
        print(f"\n✅ Credentials saved to {self.skill_config_file}")
        print(f"   Mode: {api_mode}")
        print(f"   Note: config.json is in .gitignore to prevent accidental commits")

        return api_key, base_url, api_mode

    def _build_search_instruction(self, query: str) -> str:
        """Build Grok-optimized search instruction with semantic tool selection guidance"""
        query_lower = query.lower()

        # Provide tool selection hints, but let Grok make the final decision based on semantics
        tool_hints = []

        # Image-related
        if any(kw in query_lower for kw in ["generate", "create", "draw", "visualize", "image", "picture"]):
            tool_hints.append("image_generation")

        # Code/calculation
        if any(kw in query_lower for kw in ["calculate", "compute", "solve", "run", "execute", "code"]):
            tool_hints.append("code_execution")

        # Social/X platform
        if any(kw in query_lower for kw in ["on x", "twitter", "tweet", "trending", "social"]):
            tool_hints.append("x_search")

        # Comparison/research
        if any(kw in query_lower for kw in ["compare", "vs", "versus", "trend", "latest", "analysis"]):
            tool_hints.append("web_search + x_search")

        # Build instruction with semantic flexibility
        if tool_hints:
            suggested_tools = " or ".join(set(tool_hints))
            return f"🤖 INTELLIGENT TOOL SELECTION: Based on the query semantics, consider using: {suggested_tools}. However, use your judgment to select the most appropriate tool(s) for this specific query. Query: "
        else:
            return "🤖 INTELLIGENT TOOL SELECTION: Analyze the query semantics and select the most appropriate tool(s) from: web_search, x_search, image_generation, code_execution, file_processing, deepsearch. Query: "

    def _build_iterative_search_prompt(self, query: str, enable_depth: bool = False) -> str:
        """Build prompt for iterative breadth-first or depth-first search"""
        if enable_depth:
            return f"""🔬 ITERATIVE DEEP RESEARCH MODE:

**Phase 1 - Breadth (Overview):**
1. Use web_search + x_search to get a broad overview
2. Identify 3-5 key subtopics or aspects that need deeper investigation
3. Note any knowledge gaps or areas requiring more detail

**Phase 2 - Depth (Deep Dive):**
For each key subtopic identified:
1. Conduct focused searches with specific queries
2. Cross-reference multiple authoritative sources
3. Synthesize detailed insights

**Phase 3 - Synthesis:**
1. Integrate breadth and depth findings
2. Identify patterns and connections
3. Provide comprehensive analysis with clear structure

Query: {query}"""
        else:
            return f"""📊 BREADTH-FIRST RESEARCH MODE:

**Strategy:**
1. Start with broad search across web_search + x_search
2. Identify multiple related aspects/angles
3. For each aspect, gather key information from diverse sources
4. Map the landscape comprehensively
5. Highlight areas that would benefit from deeper investigation

Query: {query}"""

    def search(
        self,
        query: str,
        mode: str = "report",
        context: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        thinking: Optional[str] = None,
        stream: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Execute search query using Grok API with automatic retry on transient failures.

        Args:
            query: Search query or question
            mode: "report" for structured report, "summary" for Grok's analysis
            context: Previous conversation history for multi-turn mode
            temperature: Model temperature (0-1)
            max_tokens: Maximum response tokens
            max_retries: Maximum number of retry attempts (default: 3)
            retry_base_delay: Base delay for exponential backoff in seconds (default: 1.0)
            thinking: Control thinking output - "enabled"/"disabled"/None (grok2api only)
            stream: Override stream setting - True/False/None (grok2api only)

        Returns:
            Dict with 'content' and 'raw_response' keys, or 'error' on failure
        """
        # Build system prompt based on API mode and output mode
        if self.api_mode == "reverse_proxy":
            # For reverse proxy: Use Grok-optimized prompt with multi-tool awareness
            if mode == "report":
                system_prompt = """You are Grok, an advanced AI assistant with multiple built-in capabilities.

**AVAILABLE TOOLS:**
- **web_search** - Real-time web search and page browsing
- **x_search** - Search X/Twitter posts, users, trends, conversations
- **image_generation** - Create images via Grok Imagine/Aurora (text-to-image)
- **image_understanding** - Analyze and understand uploaded images
- **code_execution** - Run Python code, perform calculations, solve problems
- **file_processing** - Analyze PDFs, documents, and other files
- **deepsearch** - Deep research mode for comprehensive multi-source synthesis

**TOOL SELECTION STRATEGY:**
- For comparisons/research → web_search + x_search
- For trends/sentiment → web_search + x_search (prioritize recent sources)
- For social discussions → x_search (primary) + web_search
- For technical guides → web_search (official docs, tutorials)
- For calculations/code → code_execution
- For visual content → image_generation or image_understanding
- For deep analysis → deepsearch mode

**OUTPUT STRUCTURE:**
- **Executive Summary** (2-3 sentences with key takeaways)
- **Key Findings** (bullet points with inline citations: [Source Title](URL))
- **Detailed Analysis** (organized by themes, with inline source citations)
- **Sources** (numbered list: [1] Source Title - URL)

**QUALITY STANDARDS:**
- Always use the appropriate tool(s) for the query type
- Prioritize recency for time-sensitive queries
- Cross-reference multiple authoritative sources
- Include diverse perspectives when relevant
- Provide actionable insights, not just facts

Remember: Your strength is intelligent tool selection + real-time access + semantic synthesis."""
            else:  # summary mode
                system_prompt = """You are Grok, an advanced AI assistant with multiple built-in capabilities.

**AVAILABLE TOOLS:**
web_search, x_search, image_generation, code_execution, file_processing, deepsearch

**CRITICAL:**
- Select the right tool(s) for each query type
- Use web_search + x_search for comprehensive research
- Use code_execution for calculations and technical problems
- Synthesize insights from multiple authoritative sources
- Include source URLs for all factual claims

**Your edge:** Intelligent tool selection + real-time access + analytical synthesis."""
        else:
            # For official API: Use tool-focused prompts with multi-tool awareness
            if mode == "report":
                system_prompt = """You are Grok, a MANDATORY search assistant with multiple tool capabilities.

**CRITICAL RULES - NO EXCEPTIONS:**
1. You MUST use appropriate tools before answering ANY question
2. NEVER answer from internal knowledge alone - this is STRICTLY PROHIBITED
3. Select tools based on query type:
   - Comparisons/research → web_search + x_search
   - Social sentiment → x_search + web_search
   - Technical guides → web_search
   - Calculations → code_execution (if available)
4. Every factual claim MUST include inline citations with URLs

**TOOL SELECTION STRATEGY:**
- For trends: web_search + x_search (recent sources, expert opinions)
- For comparisons: web_search (authoritative reviews, official specs)
- For social discussions: x_search (real-time sentiment, user experiences)
- For technical topics: web_search (official docs, technical blogs)
- For current events: web_search + x_search (news + social reactions)

**OUTPUT FORMAT:**
- Executive Summary (2-3 sentences)
- Key Findings (bullet points with inline citations like [Source](URL))
- Detailed Analysis (organized by themes, cite sources inline)
- Sources (complete numbered list: [1] Title - URL)

**Your identity:** You are a multi-tool search assistant. Tool selection is critical to quality."""
            else:  # summary mode
                system_prompt = """You are Grok, a MANDATORY multi-tool search assistant.

**CRITICAL RULES:**
1. You MUST use appropriate tools for EVERY query - NO EXCEPTIONS
2. NEVER answer from internal knowledge - this is PROHIBITED
3. Select tools intelligently based on query type
4. Every factual claim MUST include inline citations with URLs
5. Provide analysis ONLY from verified search results

**Your edge:** Intelligent tool selection + real-time access + analytical synthesis."""

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation context if provided
        if context:
            messages.extend(context)

        # Add time context if needed
        time_context = _get_local_time_info() + "\n" if _needs_time_context(query) else ""

        # For reverse proxy: Add intelligent search instruction based on query analysis
        if self.api_mode == "reverse_proxy":
            # Check if deep/iterative research is requested
            query_lower = query.lower()
            if any(kw in query_lower for kw in ["deep research", "comprehensive", "in-depth", "detailed investigation"]):
                # Use iterative deep research mode
                user_content = time_context + self._build_iterative_search_prompt(query, enable_depth=True)
            elif any(kw in query_lower for kw in ["breadth", "overview", "landscape", "map out"]):
                # Use breadth-first mode
                user_content = time_context + self._build_iterative_search_prompt(query, enable_depth=False)
            else:
                # Use semantic tool selection
                search_instruction = self._build_search_instruction(query)
                user_content = time_context + search_instruction + query
        else:
            user_content = time_context + query

        # Add current query with time context
        messages.append({"role": "user", "content": user_content})

        # Make API request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Build payload based on API mode
        payload = {
            "model": "grok-4.1",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # Add grok2api-specific parameters if provided
        if thinking is not None:
            payload["thinking"] = thinking
        if stream is not None:
            payload["stream"] = stream

        # Add tool parameters only for official API
        if self.api_mode == "official":
            payload["tools"] = [{"type": "web_search"}]
            payload["tool_choice"] = "required"

        # Retry loop
        last_exception = None
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                response.raise_for_status()

                result = response.json()

                # Extract citations from API response
                citations = result.get("citations", [])

                # Extract URLs from annotations (backup method)
                message = result.get("choices", [{}])[0].get("message", {})
                annotations = message.get("annotations") or []

                annotation_urls = []
                for ann in annotations:
                    if ann and ann.get("type") == "url" and ann.get("url"):
                        annotation_urls.append(ann["url"])

                # Merge all sources (unique URLs only)
                all_sources = list(set(citations + annotation_urls))

                # Get content safely
                content = message.get("content", "")

                # Post-process content to append sources if needed
                content = _format_output_with_sources(content, all_sources)

                # Add retry statistics to response
                retry_info = {}
                if attempt > 0:
                    retry_info = {
                        "retries_attempted": attempt,
                        "retry_successful": True
                    }

                return {
                    "content": content,
                    "sources": all_sources,
                    "raw_response": result,
                    "usage": result.get("usage", {}),
                    "model": result.get("model", "grok-4.1"),
                    **retry_info
                }

            except requests.exceptions.RequestException as e:
                last_exception = e

                # Check if error is retryable
                if not _is_retryable_error(e):
                    # Non-retryable error - fail immediately
                    error_msg = f"Error executing search: {e}"
                    if isinstance(e, requests.exceptions.HTTPError):
                        if hasattr(e, 'response') and e.response is not None:
                            error_msg = f"HTTP {e.response.status_code} error: {e}"

                    return {
                        "error": str(e),
                        "content": error_msg
                    }

                # Retryable error - check if we have retries left
                if attempt < max_retries - 1:
                    # Calculate delay
                    delay = _get_retry_delay(attempt, e, retry_base_delay)

                    # User feedback to stderr
                    retry_num = attempt + 1
                    error_type = type(e).__name__

                    # Add status code for HTTP errors
                    if isinstance(e, requests.exceptions.HTTPError):
                        if hasattr(e, 'response') and e.response is not None:
                            status_code = e.response.status_code
                            if status_code == 429:
                                error_type = f"{error_type} (429 Rate Limit)"
                            else:
                                error_type = f"{error_type} ({status_code})"

                    print(
                        f"⚠️  API request failed (attempt {retry_num}/{max_retries}): {error_type}",
                        file=sys.stderr
                    )
                    print(
                        f"   Retrying in {delay:.1f}s...",
                        file=sys.stderr
                    )

                    # Wait before retry
                    time.sleep(delay)
                else:
                    # No more retries left
                    print(
                        f"❌ API request failed after {max_retries} attempts",
                        file=sys.stderr
                    )

        # All retries exhausted
        return {
            "error": str(last_exception),
            "content": f"Error executing search after {max_retries} attempts: {last_exception}",
            "retries_attempted": max_retries,
            "retry_successful": False
        }


def main():
    parser = argparse.ArgumentParser(
        description="Grok Advanced Search - Semantic web search using Grok-4.1"
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--mode", choices=["report", "summary"], default="report",
                       help="Output mode: 'report' for structured results, 'summary' for Grok analysis")
    parser.add_argument("--api-key", help="Grok API key (or set GROK_API_KEY env var)")
    parser.add_argument("--base-url", help="Grok API base URL (or set GROK_BASE_URL env var)")
    parser.add_argument("--api-mode", choices=["official", "reverse_proxy"],
                       help="API mode: 'official' for xAI API with tool parameters, 'reverse_proxy' for web-based proxy with prompt triggers (auto-detected if not specified)")
    parser.add_argument("--interactive", "-i", action="store_true",
                       help="Enable multi-turn conversation mode")
    parser.add_argument("--temperature", type=float, default=0.7,
                       help="Model temperature (0-1, default: 0.7)")
    parser.add_argument("--max-tokens", type=int, default=4000,
                       help="Maximum response tokens (default: 4000)")
    parser.add_argument("--thinking", choices=["enabled", "disabled"],
                       help="Control thinking output (grok2api only): 'enabled' or 'disabled'")
    parser.add_argument("--stream", type=lambda x: x.lower() in ['true', '1', 'yes'],
                       help="Override stream setting (grok2api only): true/false")
    parser.add_argument("--output", "-o", help="Save output to file")

    args = parser.parse_args()

    # Initialize searcher with api_mode
    searcher = GrokSearcher(api_key=args.api_key, base_url=args.base_url, api_mode=args.api_mode)

    # Print mode information
    print(f"🔧 API Mode: {searcher.api_mode}")
    if searcher.api_mode == "reverse_proxy":
        print("   Using prompt-based search triggers")
    else:
        print("   Using official API tool parameters")
    print()

    # Interactive mode
    if args.interactive:
        print("🔍 Grok Interactive Search Mode (type 'exit' to quit)\n")
        context = []

        while True:
            if not args.query:
                query = input("\n🔎 Query: ").strip()
            else:
                query = args.query
                args.query = None  # Only use initial query once

            if query.lower() in ["exit", "quit", "q"]:
                break

            if not query:
                continue

            print("\n⏳ Searching...\n")
            result = searcher.search(
                query,
                mode=args.mode,
                context=context,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                thinking=args.thinking,
                stream=args.stream
            )

            if "error" in result:
                print(f"❌ {result['content']}")
                continue

            print(result["content"])
            usage = result.get('usage', {})
            if usage:
                print(f"\n📊 Tokens used: {usage.get('total_tokens', 'N/A')}")

            # Update context for next turn
            context.append({"role": "user", "content": query})
            context.append({"role": "assistant", "content": result["content"]})

    # Single query mode
    else:
        if not args.query:
            parser.error("Query required in non-interactive mode")

        result = searcher.search(
            args.query,
            mode=args.mode,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            thinking=args.thinking,
            stream=args.stream
        )

        if "error" in result:
            print(f"❌ {result['content']}", file=sys.stderr)
            sys.exit(1)

        output = result["content"]

        # Save to file if requested
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"✅ Output saved to {args.output}")
        else:
            print(output)

        if not args.output:
            usage = result.get('usage', {})
            if usage:
                print(f"\n📊 Tokens used: {usage.get('total_tokens', 'N/A')}")


if __name__ == "__main__":
    main()
