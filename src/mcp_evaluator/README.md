# MCP Tool Calling Evaluator

Single, consolidated client for evaluating tool calling accuracy across **any MCP server** type.

## 🚀 Quick Start

### 1. Set up API keys and server providers
```bash
# Configure LLM provider API keys
echo "ANTHROPIC_API_KEY=your-key" >> .env

# Configure server providers (copy example and customize)
cp server_providers.example.json server_providers.json
# Edit server_providers.json with your server details and API key env var names
```

### 2. Run with any MCP server

#### **Interactive Chat Mode**
```bash
python src/mcp_evaluator/evaluator.py "https://api.example.com/mcp"
```

#### **Dataset Evaluation Mode**  
```bash
python src/mcp_evaluator/evaluator.py "https://api.example.com/mcp" dataset my-dataset.json
```

#### **Generate Results for Existing Workflow**
```bash
# Generate actual results file
python src/mcp_evaluator/evaluator.py "https://api.example.com/mcp" generate my-dataset.json results.json

# Then use existing evaluate-dataset command
mcp-doctor evaluate-dataset --dataset my-dataset.json --actual-results results.json
```

## 📋 Single File Architecture

| File | Purpose | Lines |
|------|---------|-------|
| `evaluator.py` | **Complete MCP tool calling evaluator** | ~300 |
| `README.md` | Documentation | - |

### **Integration with Existing Workflow:**

```python
# Uses existing components:
from mcp_analyzer.mcp_client import MCPClient          # ✅ Universal MCP connectivity
from mcp_analyzer.dataset_evaluator import evaluate_dataset  # ✅ Existing evaluation logic
```

✅ **Streamable HTTP Support** - Auto-detects and upgrades to Streamable transport  
✅ **All Transport Types** - HTTP, SSE, STDIO, NPX commands  
✅ **Dataset Compatible** - Works with existing dataset format  
✅ **Claude 4** - Uses latest non-deprecated model

## 🎯 Evaluation Features

- **Universal Server Support**: Works with ANY MCP server (HTTP, NPX, local scripts)
- **Multi-LLM Support**: Anthropic Claude 4 or OpenAI GPT-4o  
- **Tool Accuracy Metrics**: Measures tool selection accuracy
- **Execution Validation**: Verifies tools actually execute
- **Interactive Chat**: Test queries interactively
- **Programmatic API**: Use for automated evaluation

## 💬 Evaluation Usage

### Interactive Evaluation
```
Query: What's my team name?
🤖 Based on your team info, your team is called "Test Team"
📊 Accuracy: 1.00 | Tools: ['get_team_info']

Query: List my campaigns and add a lead
🤖 [Response with campaign info and lead addition]
📊 Accuracy: 1.00 | Tools: ['get_campaigns', 'add_lead_to_campaign']
```

### Programmatic Evaluation  
```python
async with await create_evaluator("https://api.example.com/mcp") as evaluator:
    result = await evaluator.evaluate_query(
        "What's my team name?",
        expected_tools=["get_team_info"]
    )
    print(f"Accuracy: {result.tool_accuracy}")
```

## 🌐 Supported MCP Server Types

The evaluator uses your existing `MCPClient` infrastructure and supports **all transport types**:

| Type | Example | Auto-Detection |
|------|---------|----------------|
| **Streamable HTTP** | `https://api.example.com/mcp` | ✅ Auto-upgrades |
| **SSE** | `https://api.other.com/mcp` | ✅ Auto-detects |
| **HTTP/REST** | Legacy REST APIs | ✅ Fallback support |
| **NPX Servers** | `npx @modelcontextprotocol/server-filesystem /docs` | ✅ Auto-launch |
| **Local Python** | `./server.py` | ✅ STDIO |
| **Local Node.js** | `./server.js` | ✅ STDIO |

**Smart Detection:** Auto-detects configured server providers and loads their API keys from environment variables

## 🎯 Built for Tool Calling Evaluation

- ✅ **Accuracy Measurement**: Tool selection accuracy scoring
- ✅ **Multi-LLM Comparison**: Test Claude 4 vs GPT-4o
- ✅ **Universal Server Support**: Any MCP server type
- ✅ **Execution Validation**: Verifies tools actually work
- ✅ **Minimal Codebase**: Single file, focused purpose
