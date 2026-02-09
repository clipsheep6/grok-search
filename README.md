# Grok-Search Skill

高级语义搜索工具，基于 Grok-4.1 模型，提供实时信息检索、多源综合分析和智能工具选择。

## 快速开始

### 首次配置

1. **复制配置模板**：
   ```bash
   cd ~/.claude/skills/grok-search
   cp config.json.example config.json
   ```

2. **编辑配置文件**：
   ```bash
   # 编辑 config.json，填入你的 API 凭证
   {
     "api_key": "your-grok-api-key-here",
     "base_url": "https://api.x.ai/v1",
     "api_mode": "official"
   }
   ```

3. **API 模式说明**：
   - `official`: 标准 xAI API 格式（带工具参数）
     - 适用于：官方 xAI API、大多数第三方 API 提供商
   - `reverse_proxy`: 反向代理模式（基于提示词触发）
     - 适用于：不支持工具参数的 Web 界面反向代理

**注意**：`config.json` 已在 `.gitignore` 中，不会被提交到 Git 仓库。

## 功能特性

### 核心能力
- **语义理解** - 分析查询意图，而非简单关键词匹配
- **智能工具选择** - 自动选择最佳工具（web_search、x_search、code_execution 等）
- **多源综合** - 整合网页、社交媒体等多个来源的信息
- **实时访问** - 获取最新信息并提供来源引用
- **自动重试** - 智能处理网络问题和 API 不稳定情况

### 智能重试机制
- **自动重试**: 网络超时、连接错误、服务器 5xx 错误自动重试（最多 3 次）
- **智能判断**: 认证错误（401/403）和客户端错误（400/404）立即失败，不浪费时间
- **指数退避**: 1s → 2s → 4s，避免频繁请求
- **速率限制**: 自动遵守 HTTP 429 的 Retry-After 响应头

## 使用方法

### 基础用法

```bash
# 通过 Claude Code skill 调用
grok-search "What are the latest AI trends in 2026?"

# 指定输出模式
grok-search "Compare React vs Vue" mode=summary

# 指定 API 模式
grok-search "Latest news" api_mode=reverse_proxy
```

### Python 脚本调用

```python
from grok_search import GrokSearcher

# 初始化
searcher = GrokSearcher(
    api_key="your-key",
    base_url="https://api.x.ai/v1",
    api_mode="official"
)

# 基础搜索
result = searcher.search("What is Python?")
print(result['content'])

# 自定义重试配置
result = searcher.search(
    "complex query",
    max_retries=5,           # 增加重试次数
    retry_base_delay=2.0     # 调整延迟时间
)

# 禁用重试（快速失败）
result = searcher.search("query", max_retries=1)

# 控制 thinking 输出（grok2api 专用）
result = searcher.search(
    "query",
    thinking="disabled"  # 节省 20-50% token
)
```

## 参数说明

### Skill 参数
- `query` (必需) - 搜索查询或研究问题
- `mode` (可选) - 输出模式
  - `report` (默认) - 结构化报告格式
  - `summary` - Grok 分析总结
- `api_mode` (可选) - API 模式
  - `official` - 标准 xAI API（带工具参数）
  - `reverse_proxy` - 反向代理模式（基于提示词触发）

### Python 方法参数
- `query` - 搜索查询
- `mode` - 输出模式（同上）
- `temperature` - 模型温度（0-1，默认 0.7）
- `max_tokens` - 最大响应 token 数（默认 4000）
- `max_retries` - 最大重试次数（默认 3）
- `retry_base_delay` - 基础延迟秒数（默认 1.0）
- `thinking` - 控制思维链输出（grok2api 专用）
  - `"enabled"` - 显示推理过程
  - `"disabled"` - 隐藏推理过程（节省 20-50% token）
  - `None` - 使用服务端默认配置
- `stream` - 控制流式输出（grok2api 专用）
  - `True` - 启用流式响应
  - `False` - 等待完整响应
  - `None` - 使用服务端默认配置

## 响应格式

### 成功响应
```json
{
  "content": "搜索结果内容...",
  "sources": ["https://...", "https://..."],
  "usage": {"total_tokens": 1234},
  "model": "grok-4.1"
}
```

### 重试后成功
```json
{
  "content": "...",
  "sources": [...],
  "retries_attempted": 2,
  "retry_successful": true
}
```

### 失败响应
```json
{
  "error": "错误信息",
  "content": "Error executing search after 3 attempts: ...",
  "retries_attempted": 3,
  "retry_successful": false
}
```

## 使用场景

### 1. 研究分析
```bash
grok-search "Deep research on quantum computing applications in 2026"
```

### 2. 趋势对比
```bash
grok-search "Compare AI frameworks: PyTorch vs TensorFlow vs JAX"
```

### 3. 实时信息
```bash
grok-search "Latest developments in AI safety research"
```

### 4. 社交媒体洞察
```bash
grok-search "What are people saying about GPT-5 on X/Twitter?"
```

### 5. 技术文档查询
```bash
grok-search "How to implement OAuth2 in FastAPI"
```

## 最佳实践

### 网络不稳定环境
```python
# 增加重试次数和延迟
result = searcher.search(
    "query",
    max_retries=5,
    retry_base_delay=2.0
)
```

### 生产环境
```python
# 使用默认配置（已优化）
result = searcher.search("query")
```

### 快速失败场景
```python
# 减少重试次数
result = searcher.search("query", max_retries=1)
```

## 配置说明

### 凭证配置

**方法 1: 环境变量**
```bash
export GROK_API_KEY='your-api-key'
export GROK_BASE_URL='https://api.x.ai/v1'
export GROK_API_MODE='official'
```

**方法 2: 配置文件**
创建 `~/.grok/config.json`:
```json
{
  "api_key": "your-api-key",
  "base_url": "https://api.x.ai/v1",
  "api_mode": "official"
}
```

**方法 3: 命令行参数**
```bash
python3 grok_search.py "query" \
  --api-key "your-key" \
  --base-url "https://api.x.ai/v1" \
  --api-mode "official"
```

## 性能说明

### 重试延迟
| 场景 | 额外延迟 |
|------|---------|
| 首次成功 | 0ms |
| 1 次重试 | ~1.1s |
| 2 次重试 | ~3.3s |
| 3 次重试 | ~7.7s |

### 用户反馈
重试时会在 stderr 显示进度：
```
⚠️  API request failed (attempt 1/3): ConnectionError
   Retrying in 1.2s...
```

## 故障排查

### 问题：认证失败
**症状**: HTTP 401/403 错误
**解决**: 检查 API key 是否正确，确认账户权限

### 问题：请求超时
**症状**: Timeout 错误，自动重试 3 次后失败
**解决**:
- 检查网络连接
- 增加重试次数：`max_retries=5`
- 增加延迟时间：`retry_base_delay=2.0`

### 问题：速率限制
**症状**: HTTP 429 错误
**解决**: 自动处理，会遵守 Retry-After 响应头等待

## 技术细节

### 重试策略
- **指数退避**: `delay = base_delay * (2 ** attempt) + jitter`
- **随机抖动**: 0-10% 的延迟时间，防止惊群效应
- **智能分类**: 区分临时性错误和永久性错误

### 代码位置
- **主文件**: `scripts/grok_search.py` (704 行)
- **重试函数**: `_is_retryable_error()`, `_get_retry_delay()`
- **测试文件**: `scripts/test_retry_mechanism.py`

## 测试

### 运行测试

```bash
cd ~/.claude/skills/grok-search/scripts
python3 test_retry_mechanism.py
```

### 测试覆盖

测试套件包含以下测试：

1. **错误分类测试** (11 个测试用例)
   - 网络错误：ConnectionError, Timeout, ChunkedEncodingError
   - HTTP 5xx 错误：500, 502, 503
   - HTTP 429 速率限制
   - HTTP 4xx 错误：400, 401, 403, 404

2. **延迟计算测试** (3 个测试用例)
   - 验证指数退避公式
   - 验证随机抖动范围

3. **Retry-After 响应头测试**
   - 验证 HTTP 429 的 Retry-After 处理

4. **方法签名测试**
   - 验证 search() 方法参数
   - 验证默认值

5. **网络超时重试测试** (可选)
   - 实际触发网络超时
   - 验证重试行为

### 测试结果

所有测试通过率：**100% (5/5)**

## 更新日志

### 2026-02-08
- ✅ 添加智能重试机制
- ✅ 支持指数退避策略
- ✅ 遵守 Retry-After 响应头
- ✅ 添加重试统计信息
- ✅ 完全向后兼容

---

**文档**: 完整 skill 文档请参考 `SKILL.md`
**状态**: ✅ 生产就绪
# grok-search
