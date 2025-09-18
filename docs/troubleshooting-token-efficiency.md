# Token Efficiency Analysis: Troubleshooting Guide

This guide helps you resolve common issues when using MCP Doctor's Token Efficiency Analysis feature.

## Common Issues and Solutions

### 🚨 "No working endpoint found for tool calling"

**Problem**: MCP Doctor can't execute tools on your MCP server.

**Symptoms**:
```
MCPClientError: No working endpoint found for tool calling on server http://localhost:3001
```

**Solutions**:

1. **Check MCP Protocol Support**:
   ```bash
   # Verify your server supports tools/call method
   curl -X POST http://localhost:3001/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
   ```

2. **Use STDIO Transport**:
   Most NPX-based MCP servers use STDIO transport, which should work automatically:
   ```bash
   mcp-doctor analyze --target "npx your-mcp-server" --check token_efficiency
   ```

3. **Check Server Implementation**:
   Ensure your MCP server implements the `tools/call` method according to the MCP specification.

### ⚠️ "Tools Successfully Analyzed: 0/X"

**Problem**: Tools are discovered but can't be executed.

**Symptoms**:
- Server connects successfully
- Tools are listed
- But no tools can be executed for token analysis

**Solutions**:

1. **Check Required Parameters**:
   ```bash
   # Run with verbose mode to see what arguments are being generated
   mcp-doctor analyze --target "npx your-mcp-server" --check token_efficiency --verbose
   ```

2. **Verify Tool Schemas**:
   Ensure your tools have proper parameter schemas:
   ```json
   {
     "name": "my_tool",
     "parameters": {
       "properties": {
         "required_param": {"type": "string"}
       },
       "required": ["required_param"]
     }
   }
   ```

3. **Test Tools Manually**:
   Try calling your tools directly to ensure they work:
   ```bash
   # Test if your MCP server tools work
   npx your-mcp-server
   # Then test tool calls manually
   ```

### 🔍 "Response contains 0 tokens"

**Problem**: Tool executions succeed but show 0 tokens.

**Possible Causes**:

1. **Empty Responses**: Your tools return `null`, `{}`, or empty strings
2. **Error Responses**: Tools return error objects instead of data
3. **Unexpected Response Format**: Non-JSON responses

**Solutions**:

1. **Check Response Content**:
   ```bash
   # Use verbose mode to see actual responses
   mcp-doctor analyze --target "npx your-mcp-server" --check token_efficiency --verbose
   ```

2. **Verify Tool Output**:
   Ensure your tools return meaningful data:
   ```json
   // Good response
   {
     "result": "This is actual content with data...",
     "metadata": {"items": 42}
   }
   
   // Bad response (will show 0 tokens)
   {
     "success": true
   }
   ```

### 🐛 "Tool execution failed: [Tool Name]"

**Problem**: Specific tools fail during execution.

**Debugging Steps**:

1. **Check Generated Arguments**:
   ```bash
   mcp-doctor analyze --target "npx your-mcp-server" --check token_efficiency --verbose
   ```
   Look for the arguments being passed to failing tools.

2. **Validate Parameter Types**:
   Ensure your tool accepts the generated argument types:
   ```python
   # If your tool expects an integer but gets a string
   def my_tool(limit: int):  # MCP Doctor generates limit=10
       return f"Processing {limit} items"
   ```

3. **Handle Sample Values Gracefully**:
   Your tools should handle sample values like `"https://example.com"`:
   ```python
   def scrape_url(url: str):
       if url == "https://example.com":
           return {"content": "Sample content for testing"}
       # ... actual scraping logic
   ```

### 📊 Inconsistent Token Counts

**Problem**: Token counts seem wrong or inconsistent.

**Understanding Token Estimation**:

MCP Doctor uses character-based approximation: `tokens ≈ characters / 4`

This is:
- **Fast** and **consistent**
- **Conservative** (tends to overestimate)
- **Approximate** (within ~20% of actual)

**When Token Counts Seem Off**:

1. **Large Text Content**: Token estimation works best for structured JSON
2. **Binary Data**: Base64 encoded data inflates token counts
3. **Highly Structured Data**: JSON overhead affects estimation

### 🔧 Performance Issues

**Problem**: Token efficiency analysis is slow.

**Optimization Tips**:

1. **Reduce Tool Count**: Test specific tools if you have many:
   ```bash
   # Focus on specific tools by filtering server response
   ```

2. **Increase Timeout**: For slow tools:
   ```bash
   mcp-doctor analyze --target "npx your-mcp-server" --check token_efficiency --timeout 60
   ```

3. **Check Tool Performance**: Slow tools indicate potential optimization opportunities

### 🚫 "NotImplementedError: HTTP transport not supported"

**Problem**: Trying to use token efficiency with HTTP-only MCP servers.

**Current Limitation**: Token efficiency analysis currently requires tool execution capability, which is primarily supported via STDIO transport.

**Solutions**:

1. **Use NPX/STDIO Servers**: Most MCP servers support this
2. **Static Analysis Only**: Use description analysis instead:
   ```bash
   mcp-doctor analyze --target http://your-server --check descriptions
   ```

## Debugging Checklist

When token efficiency analysis isn't working:

- [ ] **Server Connection**: Can MCP Doctor connect and list tools?
- [ ] **Tool Schemas**: Do tools have proper parameter definitions?
- [ ] **Required Parameters**: Are required parameters correctly marked?
- [ ] **Tool Execution**: Do tools accept the generated sample arguments?
- [ ] **Response Format**: Do tools return meaningful data (not just status messages)?
- [ ] **Transport Type**: Are you using a compatible transport (STDIO recommended)?

## Getting More Information

### Verbose Mode
Always start debugging with verbose mode:
```bash
mcp-doctor analyze --target "npx your-mcp-server" --check token_efficiency --verbose
```

This shows:
- Generated test arguments for each tool
- Actual tool responses
- Token count calculations
- Error details for failed tools

### JSON Output
For programmatic analysis:
```bash
mcp-doctor analyze --target "npx your-mcp-server" --check token_efficiency --output-format json > analysis.json
```

### Log Analysis
Check the tool execution logs for patterns:
- Which tools consistently fail?
- What arguments cause issues?
- Are there common error messages?

## Best Practices for MCP Server Developers

To ensure your MCP server works well with token efficiency analysis:

### 1. Proper Schema Definition
```json
{
  "name": "search_documents",
  "description": "Search through document database",
  "parameters": {
    "properties": {
      "query": {
        "type": "string",
        "description": "Search query text"
      },
      "limit": {
        "type": "integer",
        "description": "Maximum results (1-1000)",
        "minimum": 1,
        "maximum": 1000,
        "default": 10
      }
    },
    "required": ["query"]
  }
}
```

### 2. Handle Sample Data
```python
def search_documents(query: str, limit: int = 10):
    # Handle test queries gracefully
    if query == "sample query":
        return {
            "results": [
                {"title": "Sample Document", "content": "Sample content..."}
                # ... generate sample results
            ],
            "total": limit
        }
    
    # Real implementation
    return perform_actual_search(query, limit)
```

### 3. Return Meaningful Data
```python
# Good: Returns actual content
def get_user_profile(user_id: str):
    return {
        "name": "John Doe",
        "email": "john@example.com",
        "bio": "Software developer with 5 years experience...",
        "projects": [...]
    }

# Bad: Returns only status
def get_user_profile(user_id: str):
    return {"success": True, "message": "Profile retrieved"}
```

### 4. Implement Pagination
```python
def list_items(limit: int = 10, offset: int = 0):
    # Support the pagination parameters that MCP Doctor tests
    items = get_items_from_database(limit=limit, offset=offset)
    return {
        "items": items,
        "total": get_total_count(),
        "limit": limit,
        "offset": offset
    }
```

## When to Contact Support

Contact support if:

- [ ] You've followed all troubleshooting steps
- [ ] Your MCP server works with other tools but not MCP Doctor
- [ ] You're getting unexpected results consistently
- [ ] You need help optimizing your MCP server for token efficiency

**Support Channels**:
- 🐛 [GitHub Issues](https://github.com/destilabs/mcp-doctor/issues)
- 💬 [GitHub Discussions](https://github.com/destilabs/mcp-doctor/discussions)
- 🌐 [Destilabs Support](https://destilabs.com)

---

Remember: The goal of token efficiency analysis is to help you optimize your MCP server for AI agent usage. If you're seeing issues, they often indicate real optimization opportunities!
