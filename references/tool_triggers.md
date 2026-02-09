# Grok Tool Triggers Reference

This document describes how the grok-search skill intelligently selects and triggers different Grok tools based on query patterns.

## Available Grok Tools

Based on Grok web interface capabilities (as of 2026):

1. **web_search** - Real-time web search and page browsing
2. **x_search** - Search X/Twitter posts, users, trends, conversations
3. **image_generation** - Create images via Grok Imagine/Aurora
4. **image_understanding** - Analyze and understand uploaded images
5. **code_execution** - Run Python code, perform calculations
6. **file_processing** - Analyze PDFs, documents, files
7. **deepsearch** - Deep research mode for comprehensive synthesis

## Automatic Tool Selection

The skill analyzes your query and automatically triggers the most appropriate tool(s):

### Image Generation
**Triggers:** generate image, create image, draw, visualize, show me picture, make image

**Example queries:**
- "Generate an image of a futuristic city"
- "Create a logo for my startup"
- "Draw a diagram showing the architecture"

**Tool used:** `image_generation`

---

### Code Execution
**Triggers:** run code, execute, calculate, compute, solve equation, debug code

**Example queries:**
- "Calculate compound interest on $10000 at 5% for 10 years"
- "Run this Python code and show the output"
- "Solve the equation: 2x + 5 = 15"

**Tool used:** `code_execution`

---

### File Analysis
**Triggers:** analyze file, read pdf, process document, extract from

**Example queries:**
- "Analyze this PDF and summarize the key points"
- "Extract data from the uploaded spreadsheet"
- "Read this document and find all mentions of AI"

**Tool used:** `file_processing`

---

### Deep Research
**Triggers:** deep research, comprehensive analysis, in-depth study, detailed investigation

**Example queries:**
- "Deep research on quantum computing applications in 2026"
- "Comprehensive analysis of the AI chip market"
- "In-depth study of climate change solutions"

**Tool used:** `deepsearch`

---

### Comparison Analysis
**Triggers:** compare, vs, versus, difference between

**Example queries:**
- "Compare Notion vs Obsidian for team collaboration"
- "What's the difference between React and Vue?"
- "Python vs JavaScript for backend development"

**Tools used:** `web_search` + `x_search`

---

### Trend Analysis
**Triggers:** trend, latest, emerging, future of, state of

**Example queries:**
- "What are the latest AI agent trends?"
- "Emerging technologies in 2026"
- "Future of quantum computing"

**Tools used:** `web_search` + `x_search`

---

### Patent Research
**Triggers:** patent, prior art, intellectual property, ip landscape

**Example queries:**
- "Find patents related to transformer architecture"
- "Patent landscape for AI chips"
- "Prior art search for neural network optimization"

**Tool used:** `web_search`

---

### Technical Guides
**Triggers:** how to, tutorial, guide, best practice, implementation, step by step

**Example queries:**
- "How to implement OAuth2 authentication"
- "Best practices for React performance optimization"
- "Step by step guide to deploy on AWS"

**Tool used:** `web_search`

---

### Social Sentiment
**Triggers:** sentiment, opinion, discussion, what people say, what do people think

**Example queries:**
- "What do people think about the new iPhone?"
- "Sentiment around AI regulation"
- "Discussion about climate change on social media"

**Tools used:** `x_search` + `web_search`

---

### Market Intelligence
**Triggers:** market, industry, competitive, landscape, market share

**Example queries:**
- "AI chip market analysis"
- "Competitive landscape for cloud providers"
- "Industry trends in fintech"

**Tool used:** `web_search`

---

### X Platform Search
**Triggers:** on x, on twitter, x post, tweet, x user, twitter user, trending on x

**Example queries:**
- "What's trending on X about AI?"
- "Find tweets about the Super Bowl"
- "X user @elonmusk recent posts"

**Tool used:** `x_search`

---

### Breaking News
**Triggers:** news, breaking, current event, happening now, today, just happened

**Example queries:**
- "Breaking news about AI today"
- "What's happening now in tech?"
- "Current events in the Middle East"

**Tools used:** `web_search` + `x_search`

---

### Technical Documentation
**Triggers:** documentation, api reference, official docs, specification

**Example queries:**
- "React documentation for hooks"
- "AWS API reference for S3"
- "Python official docs for asyncio"

**Tool used:** `web_search`

---

### Default (Comprehensive Search)
**Triggers:** All other queries

**Example queries:**
- "What is quantum computing?"
- "Explain blockchain technology"
- "History of artificial intelligence"

**Tools used:** `web_search` + `x_search`

---

## Tool Selection Strategy

The skill uses intelligent pattern matching to:

1. **Detect query intent** - Analyze keywords and context
2. **Select optimal tools** - Choose the most appropriate tool(s)
3. **Provide targeted instructions** - Guide Grok to use specific capabilities
4. **Optimize for quality** - Ensure the best results for each query type

## Benefits

- **Automatic optimization** - No need to manually specify tools
- **Better results** - Each query uses the most appropriate capabilities
- **Comprehensive coverage** - Combines multiple tools when beneficial
- **User-friendly** - Just ask naturally, the skill handles the rest

## Examples in Action

### Example 1: Comparison Query
```
Query: "Compare Notion vs Obsidian"
Detected: Comparison analysis
Tools: web_search + x_search
Instruction: "🔍 USE WEB_SEARCH + X_SEARCH: Search authoritative
sources and X discussions comparing these options..."
```

### Example 2: Calculation Query
```
Query: "Calculate compound interest on $10000"
Detected: Code execution needed
Tool: code_execution
Instruction: "💻 USE CODE EXECUTION: Use your code interpreter
to run the code, perform calculations..."
```

### Example 3: Social Query
```
Query: "What's trending on X about AI?"
Detected: X platform search
Tool: x_search
Instruction: "🐦 USE X_SEARCH: Search X platform for posts,
users, trends, and conversations..."
```

## Notes

- Tool selection happens automatically in `reverse_proxy` mode
- In `official` API mode, tool parameters are sent via API
- The system prompt includes tool awareness and selection strategy
- Multiple tools can be triggered for comprehensive queries
