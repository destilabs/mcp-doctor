# LLM-Based Parameter Generation for Token Efficiency Testing

## Overview

When testing token efficiency, mcp-doctor attempts to call tools with generated parameters. However, many tools have complex validation rules that cause initial parameter attempts to fail. 

The LLM-based parameter generator uses OpenAI or Anthropic models to **automatically fix parameter validation errors** by:
1. Analyzing the tool's input schema
2. Reading the error feedback from failed attempts
3. Generating corrected parameters that satisfy all validation rules
4. Retrying the tool call with the corrected parameters

This dramatically increases the success rate of token efficiency testing without manual parameter configuration.

## Setup

### 1. Install LLM Dependencies

```bash
pip install -e ".[llm]"
```

This installs:
- `openai>=1.0.0` for GPT models
- `anthropic>=0.34.0` for Claude models

### 2. Set API Key

**For OpenAI (recommended for cost efficiency):**
```bash
export OPENAI_API_KEY="sk-..."
```

**For Anthropic:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Usage

### Basic Usage (with default GPT-4o-mini)

```bash
mcp-doctor analyze \
  --target "https://mcp.explorium.ai/sse" \
  --oauth \
  --check token_efficiency \
  --show-tool-outputs
```

The tool will automatically:
- Try calling each tool with generated parameters
- If validation fails, use GPT-4o-mini to fix the parameters
- Retry with corrected parameters
- Display results with `✅ LLM correction successful!` when it works

### Using Different LLM Models

**GPT-4o (more capable, higher cost):**
```bash
mcp-doctor analyze \
  --target "https://mcp.explorium.ai/sse" \
  --oauth \
  --check token_efficiency \
  --llm-model gpt-4o
```

**Claude 3.5 Sonnet:**
```bash
mcp-doctor analyze \
  --target "https://mcp.explorium.ai/sse" \
  --oauth \
  --check token_efficiency \
  --llm-model claude-3-5-sonnet-20241022
```

**Available models:**
- `gpt-4o-mini` (default, best cost/performance)
- `gpt-4o` (most capable)
- `claude-3-5-sonnet-20241022` (Anthropic's best)
- `claude-3-5-haiku-20241022` (Anthropic's fast model)

## How It Works

### Example: Fixing Array Validation Errors

**Initial attempt (fails):**
```json
{
  "prospect_ids": [],
  "enrichments": []
}
```

**Error feedback:**
```
MCP error -32602: Invalid arguments for tool enrich-prospects:
[
  {
    "code": "too_small",
    "minimum": 1,
    "type": "array",
    "message": "Array must contain at least 1 element(s)",
    "path": ["prospect_ids"]
  }
]
```

**LLM generates corrected parameters:**
```json
{
  "prospect_ids": ["test_prospect_1"],
  "enrichments": ["company_info"]
}
```

**Result:** ✅ Tool call succeeds!

### What You'll See

When LLM correction is triggered:

```
⚙️  Using LLM to fix parameters for enrich-prospects
✅ LLM correction successful! (~421 tokens)
{
  "data": [...],
  "metadata": {...}
}
```

## Benefits

### Without LLM Parameter Generation
- 70-80% of tools fail with validation errors
- Requires manual parameter configuration per tool
- Time-consuming to test multiple tools

### With LLM Parameter Generation  
- 90-95%+ success rate for tool calls
- Automatic parameter correction
- Comprehensive token efficiency testing
- Minimal configuration needed

## Cost Considerations

**GPT-4o-mini** (recommended):
- ~$0.00015 per tool correction (typically 1-2 corrections per tool)
- Testing 12 tools: ~$0.002-0.004 total
- Extremely cost-effective

**GPT-4o:**
- ~$0.001-0.002 per tool correction
- Testing 12 tools: ~$0.012-0.024 total
- Use for complex schemas

**Claude 3.5 Sonnet:**
- Similar to GPT-4o
- Excellent at understanding complex validation rules

## Fallback Behavior

If LLM parameter generation is unavailable (no API key or package not installed):
- Falls back to basic parameter generation
- Tools with validation errors will fail
- Manual overrides via `--overrides` file still work

## Manual Overrides

For tools that need specific test data, you can still use manual overrides:

**overrides.json:**
```json
{
  "enrich-business": {
    "business_ids": ["real_business_id_123"],
    "parameters": ["revenue", "employee_count"]
  }
}
```

```bash
mcp-doctor analyze \
  --target "..." \
  --check token_efficiency \
  --overrides overrides.json
```

Manual overrides take precedence over LLM generation.

## Troubleshooting

### "OPENAI_API_KEY not set, LLM parameter generation disabled"
- Set your API key: `export OPENAI_API_KEY="sk-..."`
- Or use Anthropic: `export ANTHROPIC_API_KEY="sk-ant-..."`

### "openai package not installed"
- Install LLM dependencies: `pip install -e ".[llm]"`

### "LLM correction failed"
- Check API key is valid
- Try a different model with `--llm-model`
- Fall back to manual overrides if needed

## Example: Full Analysis with LLM

```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Run comprehensive analysis
mcp-doctor analyze \
  --target "https://mcp.explorium.ai/sse" \
  --oauth \
  --check token_efficiency \
  --show-tool-outputs \
  --verbose \
  --export-html report.html

# Output shows:
# - Initial parameter attempts
# - LLM corrections when validation fails  
# - Successful token measurements
# - Complete efficiency analysis
```

## Integration with CI/CD

```yaml
# .github/workflows/test.yml
- name: Test MCP Token Efficiency
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: |
    mcp-doctor analyze \
      --target "$MCP_SERVER_URL" \
      --check token_efficiency \
      --llm-model gpt-4o-mini
```

## Privacy & Security

- API keys are never logged or displayed
- Tool parameters and responses are sent to LLM provider
- Error messages may contain schema information
- Use manual overrides for sensitive test data


