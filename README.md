# MCP Doctor 🩺

**A comprehensive diagnostic tool for MCP (Model Context Protocol) servers**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

MCP Doctor is your go-to diagnostic tool for analyzing MCP servers and ensuring they follow best practices for AI agent integration. Just like a medical doctor diagnoses health issues, MCP Doctor diagnoses your MCP servers to ensure they're agent-friendly, performant, and compliant with [Anthropic's best practices](https://www.anthropic.com/engineering/writing-tools-for-agents).

## 🎯 What is MCP Doctor?

MCP Doctor performs comprehensive health checks on your MCP servers, whether they're running as traditional HTTP services or launched via NPX commands. It analyzes tool descriptions, parameter schemas, and server behavior to provide actionable recommendations for improving AI agent compatibility.

## ✨ Key Features

- 🔍 **Deep Analysis** - Comprehensive evaluation of MCP server health
- 🌐 **Universal Support** - Works with HTTP servers and NPX-launched packages
- 🔧 **Environment Handling** - Secure API key and environment variable management
- 📊 **Rich Reports** - Beautiful terminal output with detailed diagnostics
- 🚀 **Easy Integration** - Simple CLI and Python API
- ⚡ **Fast Execution** - Async operations for quick analysis

## 🧠 Philosophy

MCP Doctor is built around two core principles that drive every design decision:

### ⚡ **Speed First**
This tool is designed for **frequent, everyday usage** by developers and AI engineers. Speed is paramount:

- **No AI dependencies** - We deliberately avoid LLM-based evaluation to ensure consistent, fast analysis
- **Rule-based analysis** - Lightning-fast pattern matching and heuristic evaluation
- **Async architecture** - Concurrent operations for maximum performance
- **Minimal overhead** - Direct protocol communication without unnecessary abstractions

*Why this matters: When you're iterating on MCP servers, waiting 30+ seconds for AI-powered analysis breaks your flow. MCP Doctor gives you actionable insights in seconds, not minutes.*

### 🔒 **Security Paramount**
Security isn't an afterthought—it's baked into every feature:

- **Smart credential filtering** - Automatically detects and hides sensitive environment variables from logs
- **Configurable privacy levels** - From secure filtering to complete logging disablement
- **No data transmission** - All analysis happens locally; your secrets never leave your machine
- **Secure defaults** - Safe configurations out of the box

*Why this matters: MCP servers often handle sensitive API keys, database credentials, and private data. MCP Doctor ensures your secrets stay secret while providing the insights you need.*

These principles ensure MCP Doctor remains a tool you'll reach for daily—fast enough for rapid iteration, secure enough for production environments.

## 🚀 Quick Start

### Installation

```bash
pip install mcp-doctor
```

### Basic Usage

```bash
# Diagnose an HTTP MCP server
mcp-doctor analyze --target http://localhost:8000/mcp

# Diagnose an NPX-launched MCP server
mcp-doctor analyze --target "npx firecrawl-mcp"

# Diagnose with environment variables
mcp-doctor analyze --target "export FIRECRAWL_API_KEY=your_key && npx firecrawl-mcp"

# Get detailed diagnostic output
mcp-doctor analyze --target http://localhost:8000/mcp --verbose
```

## 🎬 Demonstrations

### NPX Server Analysis
See MCP Doctor in action analyzing an NPX-launched MCP server:

[📹 Watch NPX Analysis Demo](./docs/video/MCP%20doctor%20_%20npx.mp4)

### HTTP Server Analysis  
Watch MCP Doctor diagnose an HTTP MCP server:

[📹 Watch HTTP Analysis Demo](./docs/video/MCP-doctor%20_%20http.mp4)

## 🩺 Diagnostic Capabilities

### 📝 Tool Description Analysis
- **Clarity Assessment** - Evaluates description readability and completeness
- **Context Validation** - Ensures tools explain when and how to use them
- **Parameter Naming** - Checks for descriptive vs generic parameter names
- **Purpose Clarity** - Validates that each tool's purpose is clearly stated
- **Jargon Detection** - Identifies technical terms that should be simplified

### 🔮 Future Diagnostics (Roadmap)
- **Schema Validation** - Parameter schema compatibility checks
- **Performance Analysis** - Response time and resource usage evaluation
- **Security Audit** - Authentication and authorization best practices
- **Integration Testing** - Agent interaction simulation

## 🌐 Server Support

### HTTP Servers
```bash
mcp-doctor analyze --target http://localhost:8000/mcp
mcp-doctor analyze --target https://api.example.com/mcp
```

### NPX Packages
```bash
# Basic NPX analysis
mcp-doctor analyze --target "npx firecrawl-mcp"

# With environment variables (inline)
mcp-doctor analyze --target "export API_KEY=abc123 && npx firecrawl-mcp"

# With environment variables (JSON format)
mcp-doctor analyze --target "npx firecrawl-mcp" --env-vars '{"API_KEY": "abc123"}'

# With custom working directory
mcp-doctor analyze --target "npx firecrawl-mcp" --working-dir "/path/to/project"
```

## 📊 Output Formats

```bash
# Beautiful table output (default)
mcp-doctor analyze --target "npx firecrawl-mcp" --output-format table

# JSON for programmatic use
mcp-doctor analyze --target "npx firecrawl-mcp" --output-format json > report.json

# YAML for human-readable structured data
mcp-doctor analyze --target "npx firecrawl-mcp" --output-format yaml
```

## 🔧 Python API

### HTTP Server Diagnosis
```python
import asyncio
from mcp_analyzer.mcp_client import MCPClient
from mcp_analyzer.checkers.descriptions import DescriptionChecker

async def diagnose_http_server():
    client = MCPClient("http://localhost:8000/mcp")
    
    try:
        tools = await client.get_tools()
        
        checker = DescriptionChecker()
        results = checker.analyze_tool_descriptions(tools)
        
        return results
    finally:
        await client.close()

# Run diagnosis
results = asyncio.run(diagnose_http_server())
print(f"Found {len(results['issues'])} issues")
```

### NPX Server Diagnosis
```python
import asyncio
from mcp_analyzer.mcp_client import MCPClient
from mcp_analyzer.checkers.descriptions import DescriptionChecker

async def diagnose_npx_server():
    # Method 1: Environment variables in command
    client = MCPClient("export FIRECRAWL_API_KEY=abc123 && npx firecrawl-mcp")
    
    # Method 2: Environment variables via kwargs
    # client = MCPClient("npx firecrawl-mcp", env_vars={"FIRECRAWL_API_KEY": "abc123"})
    
    try:
        # Server will be launched automatically
        server_info = await client.get_server_info()
        tools = await client.get_tools()
        
        checker = DescriptionChecker()
        results = checker.analyze_tool_descriptions(tools)
        
        print(f"Diagnosed NPX server at: {client.get_server_url()}")
        return results
        
    finally:
        # This will automatically stop the NPX server
        await client.close()

# Run diagnosis
results = asyncio.run(diagnose_npx_server())
print(f"Found {len(results['issues'])} issues")
```

## 🏥 Example Diagnostic Report

```
🩺 MCP Doctor - Server Diagnosis
NPX Command: export FIRECRAWL_API_KEY=abc123 && npx firecrawl-mcp

✅ NPX server launched at http://localhost:3001
✅ Connected! Found 12 tools

📝 Tool Description Analysis
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Diagnostic Result            ┃    Count ┃ Percentage ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━┩
│ ✅ Healthy Tools             │        8 │      66.7% │
│ ⚠️  Warnings                 │        3 │      25.0% │
│ 🚨 Critical Issues           │        1 │       8.3% │
│ ℹ️  Recommendations          │        5 │      41.7% │
└──────────────────────────────┴──────────┴────────────┘

🎯 Treatment Recommendations:
   1. Add descriptions to 1 tool missing documentation
   2. Improve parameter naming for 3 tools with generic names
   3. Add usage context to 2 tools for better agent understanding
   4. Simplify technical jargon in 2 tool descriptions
```

## 📋 CLI Reference

### `analyze` Command
Main diagnostic command for MCP servers.

```bash
mcp-doctor analyze [OPTIONS]
```

**Options:**
- `--target TEXT` (required): MCP server URL or NPX command to diagnose
- `--check {descriptions,schemas,performance,all}`: Type of diagnosis to run (default: descriptions)
- `--output-format {table,json,yaml}`: Output format (default: table)
- `--verbose / --no-verbose`: Show detailed diagnostic output (default: False)
- `--timeout INTEGER`: Request timeout in seconds (default: 30)
- `--env-vars TEXT`: Environment variables for NPX command (JSON format)
- `--working-dir TEXT`: Working directory for NPX command

### `version` Command
Show version and diagnostic capabilities.

```bash
mcp-doctor version
```

## 🏗️ Development

### Project Structure
```
mcp-doctor/
├── src/mcp_analyzer/       # Main package
│   ├── cli.py              # CLI interface
│   ├── mcp_client.py       # MCP server communication
│   ├── mcp_stdio_client.py # STDIO transport client
│   ├── npx_launcher.py     # NPX server management
│   ├── reports.py          # Output formatting
│   └── checkers/           # Diagnostic modules
│       └── descriptions.py # Description analysis
└── tests/                  # Test suite
```

### Development Setup
```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=mcp_analyzer
```

### Code Quality & Linting
This project uses automated code formatting and linting:

```bash
# Auto-format code (black + isort)
./scripts/format.sh

# Check code quality (black + isort + mypy)
./scripts/lint.sh

# Or run individual tools
black src/ tests/
isort src/ tests/
mypy src/
```

**Pre-commit Setup:**
The project includes a GitHub Actions workflow that runs on every pull request to ensure code quality. Make sure to run `./scripts/format.sh` before committing changes.

## 🤝 Contributing

We welcome contributions to MCP Doctor! Whether you're:
- 🐛 Reporting bugs
- 💡 Suggesting new diagnostic features  
- 🔧 Improving existing analysis
- 📚 Enhancing documentation

Please see our contributing guidelines and feel free to open issues or pull requests.

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🔗 Related Projects

- [Model Context Protocol](https://github.com/modelcontextprotocol/servers) - Official MCP servers
- [Anthropic's MCP Guide](https://www.anthropic.com/engineering/writing-tools-for-agents) - Best practices reference

## 🏥 Support

- 🐛 [Report Issues](https://github.com/destilabs/mcp-doctor/issues)
- 💬 [Discussions](https://github.com/destilabs/mcp-doctor/discussions)  
- 🌐 [Destilabs](https://destilabs.com) - AI engineering and consulting

---

**Built with ❤️ by [Destilabs](https://destilabs.com) for the AI agent development community**

*Keep your MCP servers healthy! 🩺*