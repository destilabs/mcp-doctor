# Tool Call Caching

## Overview

The tool call cache automatically saves successful tool executions (inputs and outputs) during token efficiency testing. This creates a valuable knowledge base of:

- **Working parameters** for each tool
- **Actual responses** and token counts
- **Performance metrics** (response time, size)
- **Successful scenarios** (minimal, typical, LLM-corrected)

## Benefits

### 1. **Knowledge Base Building**
- Accumulate examples of successful tool calls
- Understand what parameters work for each tool
- Track typical response sizes and formats

### 2. **Debugging & Analysis**
- Review actual tool responses offline
- Compare responses across different scenarios
- Identify patterns in tool behavior

### 3. **Parameter Reuse**
- Reference successful parameters for manual overrides
- Build test suites from cached examples
- Share working examples with team members

### 4. **Performance Tracking**
- Track token counts over time
- Monitor response times
- Identify performance regressions

## Cache Structure

Caches are stored at: `~/.mcp-analyzer/tool-call-cache/{server_hash}/{tool_name}/`

### Directory Layout
```
~/.mcp-analyzer/tool-call-cache/
└── a1b2c3d4e5f6g7h8/              # Server URL hash
    ├── _metadata.json              # Server information
    ├── match-business/             # Tool directory
    │   ├── _index.json            # Tool statistics
    │   ├── minimal_20251003_120000_123456.json
    │   ├── minimal_llm_corrected_20251003_120005_789012.json
    │   └── typical_20251003_120010_345678.json
    └── enrich-prospects/
        ├── _index.json
        └── minimal_llm_corrected_20251003_120015_901234.json
```

### Cache File Format

Each cached call is stored as JSON:

```json
{
  "tool_name": "match-business",
  "server_url": "https://mcp.explorium.ai/sse",
  "timestamp": "2025-10-03T12:00:00.123456",
  "scenario": "minimal_llm_corrected",
  "input_params": {
    "businesses_to_match": [
      {"name": "Tesla", "domain": "tesla.com"}
    ],
    "tool_reasoning": "test query"
  },
  "output_response": {
    "data": [...],
    "metadata": {...}
  },
  "metrics": {
    "token_count": 421,
    "response_time_seconds": 1.234,
    "response_size_bytes": 1685
  }
}
```

## Usage

### Enable/Disable Caching

**Enabled by default:**
```bash
mcp-doctor analyze \
  --target "https://mcp.explorium.ai/sse" \
  --oauth \
  --check token_efficiency
```

**Explicitly enable:**
```bash
mcp-doctor analyze \
  --target "..." \
  --check token_efficiency \
  --cache-tool-calls
```

**Disable caching:**
```bash
mcp-doctor analyze \
  --target "..." \
  --check token_efficiency \
  --no-cache-tool-calls
```

### View Cache Statistics

**All cached servers:**
```bash
mcp-doctor cache-stats
```

Output:
```
All Cached Servers:

https://mcp.explorium.ai/sse
  Tools: 12, Calls: 24

https://api.example.com/mcp
  Tools: 5, Calls: 10
```

**Specific server:**
```bash
mcp-doctor cache-stats --server "https://mcp.explorium.ai/sse"
```

Output:
```
Cache Statistics for https://mcp.explorium.ai/sse
Cache Path: /Users/you/.mcp-analyzer/tool-call-cache/a1b2c3d4e5f6g7h8
Total Tools: 12
Total Cached Calls: 24

Tools:
  • match-business: 3 calls
    - minimal: 1
    - minimal_llm_corrected: 1
    - typical: 1
  • enrich-prospects: 2 calls
    - minimal_llm_corrected: 2
  ...
```

### Clear Cache

**Clear all cache (with confirmation):**
```bash
mcp-doctor cache-clear
```

**Clear specific server:**
```bash
mcp-doctor cache-clear --server "https://mcp.explorium.ai/sse"
```

**Clear specific tool:**
```bash
mcp-doctor cache-clear \
  --server "https://mcp.explorium.ai/sse" \
  --tool "match-business"
```

**Skip confirmation:**
```bash
mcp-doctor cache-clear --yes
```

## Use Cases

### 1. **Building Manual Overrides**

Review cached successful calls to create override files:

```bash
# View cache
mcp-doctor cache-stats --server "https://mcp.explorium.ai/sse"

# Find cached files
ls ~/.mcp-analyzer/tool-call-cache/*/match-business/

# Extract successful parameters
cat ~/.mcp-analyzer/tool-call-cache/*/match-business/minimal_llm_corrected_*.json | \
  jq '.input_params' > overrides.json
```

### 2. **Debugging Tool Behavior**

```bash
# Cache calls during testing
mcp-doctor analyze --target "..." --check token_efficiency --show-tool-outputs

# Review cached responses
cat ~/.mcp-analyzer/tool-call-cache/*/enrich-prospects/*.json | \
  jq '{input: .input_params, tokens: .metrics.token_count, time: .metrics.response_time_seconds}'
```

### 3. **Performance Tracking**

```bash
# Run checks over time
mcp-doctor analyze --target "..." --check token_efficiency

# Analyze trends
find ~/.mcp-analyzer/tool-call-cache -name "*.json" -not -name "_*" | \
  xargs jq -r '[.tool_name, .timestamp, .metrics.token_count, .metrics.response_time_seconds] | @csv'
```

### 4. **Sharing Examples**

```bash
# Export cache for a server
tar -czf mcp-cache.tar.gz ~/.mcp-analyzer/tool-call-cache/a1b2c3d4e5f6g7h8/

# Share with team
# Team member extracts:
tar -xzf mcp-cache.tar.gz -C ~/
```

## Cache Management

### Storage Location

- **Default**: `~/.mcp-analyzer/tool-call-cache/`
- **Per-server**: Hashed directory prevents conflicts
- **Per-tool**: Organized by tool name

### Cache Growth

- Each successful call: ~1-10 KB (depending on response size)
- 100 successful calls: ~100 KB - 1 MB
- Typical usage: < 10 MB per server

### Cache Maintenance

**Periodic cleanup:**
```bash
# Keep only recent caches (last 30 days)
find ~/.mcp-analyzer/tool-call-cache -name "*.json" -mtime +30 -delete

# Keep only LLM-corrected successes
find ~/.mcp-analyzer/tool-call-cache -name "minimal_*.json" -delete
```

**Selective cleanup:**
```bash
# Clear old caches for specific server
mcp-doctor cache-clear --server "old-server-url.com"

# Clear problematic tool
mcp-doctor cache-clear --server "..." --tool "broken-tool"
```

## Integration with LLM Parameter Generation

Cache works seamlessly with LLM parameter generation:

1. **Static parameters fail** → Attempt silently cached
2. **LLM generates correction** → Shown to user
3. **LLM correction succeeds** → Cached with `_llm_corrected` suffix
4. **Next run** → Can reference cached successful parameters

This creates a growing knowledge base of working parameters discovered by the LLM.

## Privacy & Security

### What's Cached
- ✅ Tool names and parameters
- ✅ Tool responses (full output)
- ✅ Performance metrics
- ✅ Timestamps and scenarios

### What's NOT Cached
- ❌ API keys or credentials
- ❌ OAuth tokens
- ❌ Failed tool calls
- ❌ Validation errors

### Security Notes
- Cache is stored **locally only** (never uploaded)
- Contains **actual tool responses** (may include sensitive data)
- Review cache before sharing: `mcp-doctor cache-stats`
- Clear sensitive caches: `mcp-doctor cache-clear`

## Advanced Usage

### Programmatic Access

```python
from mcp_analyzer.checkers.tool_call_cache import ToolCallCache

# Initialize cache
cache = ToolCallCache("https://mcp.explorium.ai/sse")

# Get statistics
stats = cache.get_cache_stats()
print(f"Total calls: {stats['total_calls']}")

# Get cached calls for a tool
calls = cache.get_cached_calls("match-business", scenario="minimal_llm_corrected")
for call in calls:
    print(f"Input: {call['input_params']}")
    print(f"Tokens: {call['metrics']['token_count']}")
```

### Custom Cache Directory

```python
from pathlib import Path
from mcp_analyzer.checkers.tool_call_cache import ToolCallCache

custom_dir = Path("/custom/cache/location")
cache = ToolCallCache("https://server.com", cache_dir=custom_dir)
```

## FAQ

**Q: Does caching slow down analysis?**  
A: No, caching adds <10ms per successful call (negligible).

**Q: Can I disable caching permanently?**  
A: Yes, use `--no-cache-tool-calls` flag or set in config.

**Q: How do I find cache for a specific server?**  
A: Use `mcp-doctor cache-stats` to see all servers with their paths.

**Q: Can I version control the cache?**  
A: Yes, but review for sensitive data first. Consider adding to `.gitignore`.

**Q: What happens if cache gets corrupted?**  
A: Clear it with `mcp-doctor cache-clear` and rebuild.

## Examples

### Complete Workflow

```bash
# 1. Run analysis with caching
export OPENAI_API_KEY="sk-..."
mcp-doctor analyze \
  --target "https://mcp.explorium.ai/sse" \
  --oauth \
  --check token_efficiency \
  --show-tool-outputs

# Output shows:
# ⚙️  Using LLM to fix parameters for match-business
# ✅ LLM correction successful! (~421 tokens)
# 💾 Cached 12 successful tool calls to ~/.mcp-analyzer/tool-call-cache/...

# 2. View what was cached
mcp-doctor cache-stats --server "https://mcp.explorium.ai/sse"

# 3. Extract successful parameters
cat ~/.mcp-analyzer/tool-call-cache/*/match-business/*_llm_corrected_*.json | \
  jq '.input_params' | head -1 > match-business-params.json

# 4. Use for manual testing
mcp-doctor analyze \
  --target "..." \
  --check token_efficiency \
  --overrides match-business-params.json
```

## Troubleshooting

**Cache not being created:**
- Ensure `--cache-tool-calls` is enabled (default)
- Check file permissions on `~/.mcp-analyzer/`
- Verify tools are succeeding (check with `--show-tool-outputs`)

**Can't find cache directory:**
```bash
mcp-doctor cache-stats  # Shows all cache locations
```

**Cache taking too much space:**
```bash
du -sh ~/.mcp-analyzer/tool-call-cache/
mcp-doctor cache-clear  # Clear old caches
```


