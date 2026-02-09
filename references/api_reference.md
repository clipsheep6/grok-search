# Grok API Reference

Technical reference for Grok API integration, configuration, and troubleshooting.

## Table of Contents

1. [API Endpoint & Authentication](#api-endpoint--authentication)
2. [Request/Response Format](#requestresponse-format)
3. [API Mode Configuration](#api-mode-configuration)
4. [Configuration Setup](#configuration-setup)
5. [Advanced Options](#advanced-options)
6. [Error Handling](#error-handling)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

---

## API Endpoint & Authentication

### Endpoint

```
POST {base_url}/chat/completions
```

### Authentication

Include API key in request headers:

```
Authorization: Bearer {api_key}
```

---

## Request/Response Format

### Request Format

```json
{
  "model": "grok-4.1",
  "messages": [
    {
      "role": "system",
      "content": "System prompt"
    },
    {
      "role": "user",
      "content": "User query"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 4000,
  "top_p": 1.0,
  "stream": false
}
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | Required | Model identifier (use "grok-4.1") |
| `messages` | array | Required | Conversation history with role and content |
| `temperature` | float | 0.7 | Sampling temperature (0-1). Higher = more creative |
| `max_tokens` | integer | 4000 | Maximum tokens in response |
| `top_p` | float | 1.0 | Nucleus sampling parameter |
| `stream` | boolean | false | Enable streaming responses |

### Response Format

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "grok-4.1",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Response content"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 500,
    "total_tokens": 600
  }
}
```

---

## API Mode Configuration

**IMPORTANT:** The `api_mode` parameter is **required** and must be configured.

The skill supports two API modes:

### Official API Mode (`official`)
- **Use for:** Official xAI API, most third-party API providers
- **How it works:** Uses standard API `tools` and `tool_choice` parameters
- **When to use:** Your API provider supports the official xAI API format with tool calling

### Reverse Proxy Mode (`reverse_proxy`)
- **Use for:** Web-based reverse proxy APIs that simulate web interface
- **How it works:** Uses prompt-based triggers to activate search
- **When to use:** Your API provider is a reverse proxy that doesn't support tool parameters

### Configuration Priority

The API mode is determined in this order (highest to lowest priority):

1. Parameter passed when invoking skill (highest priority)
2. Command-line argument `--api-mode`
3. Environment variable `GROK_API_MODE`
4. Config file `~/.grok/config.json` (must include `api_mode` field)

### Example Config File

```json
{
  "api_key": "your-api-key",
  "base_url": "https://your-api-url/v1",
  "api_mode": "reverse_proxy"
}
```

---

## Configuration Setup

### First-Time Setup

On first use, the script will prompt for credentials and save them:

```
Grok API credentials not found. Please provide them:
API Key: [your-key]
Base URL: [your-base-url]
API Mode (official/reverse_proxy): [your-mode]
✅ Credentials saved to ~/.grok/config.json
```

### Manual Configuration

**Option 1: Environment variables**
```bash
export GROK_API_KEY="your-api-key"
export GROK_BASE_URL="https://api.x.ai/v1"
export GROK_API_MODE="reverse_proxy"  # or "official"
```

**Option 2: Config file**

Create `~/.grok/config.json`:
```json
{
  "api_key": "your-api-key",
  "base_url": "https://api.x.ai/v1",
  "api_mode": "reverse_proxy"
}
```

The script will automatically prompt for credentials on first use and save them to the config file.

---

## Advanced Options

### Temperature Control

Adjust creativity vs. factuality:

```bash
# More factual (0.3-0.5)
python3 scripts/grok_search.py "query" --temperature 0.4

# More creative/analytical (0.7-0.9)
python3 scripts/grok_search.py "query" --temperature 0.8
```

**Recommendations:**
- Use 0.3-0.5 for factual queries (data, statistics, technical specs)
- Use 0.7-0.9 for creative/analytical tasks (synthesis, insights, predictions)

### Save Output

Save results to file:

```bash
python3 scripts/grok_search.py "query" --output research_report.md
```

Output files are saved in Markdown format with proper formatting for easy sharing and documentation.

### Token Limits

Adjust maximum response length:

```bash
python3 scripts/grok_search.py "query" --max-tokens 6000
```

**Default:** 4000 tokens
**Range:** 1000-8000 tokens
**Note:** Higher token limits increase API costs but allow more comprehensive responses.

---

## Error Handling

### Common Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 401 | Unauthorized | Check API key validity |
| 429 | Rate limit exceeded | Implement backoff/retry logic |
| 500 | Server error | Retry with exponential backoff |
| 503 | Service unavailable | Wait and retry |

### Python Integration Example

```python
import requests

def call_grok(query, api_key, base_url):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "grok-4.1",
        "messages": [
            {"role": "user", "content": query}
        ],
        "temperature": 0.7,
        "max_tokens": 4000
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=120
    )

    response.raise_for_status()
    return response.json()
```

---

## Troubleshooting

### "API credentials not found"

**Cause:** No credentials configured in environment variables or config file.

**Solution:**
1. Run the script once to be prompted for credentials
2. Or set environment variables manually
3. Or create `~/.grok/config.json` manually

### "Connection timeout"

**Cause:** Queries are complex and may take 30-60 seconds to process.

**Solutions:**
- Increase timeout value in script configuration
- Check network connectivity and firewall settings
- Verify base URL is correct and accessible
- Try a simpler query first to test connectivity

### "Rate limit exceeded"

**Cause:** Too many requests in a short time period.

**Solutions:**
- Wait before retrying (typically 60 seconds)
- Space out queries with delays between requests
- Check your API plan limits with provider
- Consider upgrading API plan if hitting limits frequently

### "Poor results quality"

**Cause:** Query may be too vague or not optimized for Grok's capabilities.

**Solutions:**
- Refine query to be more specific (include timeframes, scope, specific aspects)
- Try different temperature settings (lower for factual, higher for analytical)
- Use interactive mode to iterate and refine
- Consult search_patterns.md for query optimization techniques
- Add context and constraints to narrow the search

### Connection Issues

**Symptoms:** Network errors, timeouts, connection refused

**Solutions:**
- Verify base URL is correct
- Check network connectivity
- Ensure firewall allows outbound HTTPS
- Test with curl or similar tool to verify endpoint accessibility

### Authentication Errors

**Symptoms:** 401 errors, "Invalid API key" messages

**Solutions:**
- Verify API key is valid and not expired
- Check for extra whitespace in credentials
- Ensure proper header formatting in config
- Test with a fresh API key from provider
- Verify base URL matches your provider's endpoint

### Timeout Issues

**Symptoms:** Requests hang or timeout after long wait

**Solutions:**
- Increase timeout value for complex queries (default: 120s)
- Consider breaking large queries into smaller parts
- Use streaming for long responses (if supported)
- Check network stability and latency
- Try during off-peak hours if provider has high load

---

## Best Practices

### Token Management
Monitor `usage` field in responses to track consumption and optimize costs.

### Temperature Tuning
- Use 0.3-0.5 for factual queries
- Use 0.7-0.9 for creative/analytical tasks

### Context Window
Keep conversation history manageable (Grok-4.1 supports large context but costs scale with tokens).

### Error Handling
Always implement retry logic with exponential backoff for production use.

### Streaming
Consider streaming for long responses to improve user experience and detect issues early.

### Rate Limiting
Implement client-side rate limiting to avoid hitting API limits:
- Track requests per minute/hour
- Add delays between requests
- Queue requests during high-volume periods

### Cost Optimization
- Use appropriate token limits (don't request more than needed)
- Cache results for repeated queries
- Use summary mode for quick insights (fewer tokens than report mode)
- Monitor usage regularly to avoid unexpected costs

### Security
- Never commit API keys to version control
- Use environment variables or secure config files
- Rotate API keys periodically
- Monitor for unauthorized usage
