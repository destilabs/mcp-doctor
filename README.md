# MCP Doctor 🩺

**A comprehensive diagnostic tool for MCP (Model Context Protocol) servers**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI](https://github.com/destilabs/mcp-doctor/workflows/CI/badge.svg)](https://github.com/destilabs/mcp-doctor/actions)
[![codecov](https://codecov.io/gh/destilabs/mcp-doctor/graph/badge.svg)](https://codecov.io/gh/destilabs/mcp-doctor)
[![Coverage Status](https://coveralls.io/repos/github/destilabs/mcp-doctor/badge.svg?branch=main)](https://coveralls.io/github/destilabs/mcp-doctor?branch=main)
[![GitHub stars](https://img.shields.io/github/stars/destilabs/mcp-doctor?style=social)](https://github.com/destilabs/mcp-doctor/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/destilabs/mcp-doctor)](https://github.com/destilabs/mcp-doctor/issues)

## 🚀 **30-Day Development Sprint**

I'm committing to **30 Pull Requests in 30 Days** to rapidly evolve MCP Doctor based on community feedback and real-world usage!

**Progress:** 7/30 PRs completed
```
[██████                        ] 23% (7/30)
```
**Days Remaining:** 23 | **Started:** September 17, 2025 | **Ends:** October 17, 2025

---

MCP Doctor is your go-to diagnostic tool for analyzing MCP servers and ensuring they follow best practices for AI agent integration. Just like a medical doctor diagnoses health issues, MCP Doctor diagnoses your MCP servers to ensure they're agent-friendly, performant, and compliant with [Anthropic's best practices](https://www.anthropic.com/engineering/writing-tools-for-agents).

## 🎯 What is MCP Doctor?

MCP Doctor performs comprehensive health checks on your MCP servers, whether they're running as traditional HTTP services or launched via NPX commands. It analyzes tool descriptions, parameter schemas, and server behavior to provide actionable recommendations for improving AI agent compatibility.

## ✨ Key Features

- 🔍 **Deep Analysis** - Comprehensive evaluation of MCP server health
- 🌐 **Universal Support** - Works with HTTP servers and NPX-launched packages
- 🔧 **Environment Handling** - Secure API key and environment variable management
- 📊 **Rich Reports** - Beautiful terminal output with detailed diagnostics
- 🔒 **Security Audit** - Detects authentication gaps, exposed credentials, and insecure configurations
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

# Run token efficiency analysis
mcp-doctor analyze --target "npx firecrawl-mcp" --check token_efficiency

# Run all available checks
mcp-doctor analyze --target "npx firecrawl-mcp" --check all

# Run the security audit
mcp-doctor analyze --target http://localhost:8000/mcp --check security

# Inspect an NPX-launched server for risky tools
mcp-doctor analyze --target "npx firecrawl-mcp" --check security

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

### 🔢 Token Efficiency Analysis
- **Response Size Measurement** - Analyzes actual tool response token counts
- **Pagination Detection** - Identifies tools that need pagination support
- **Filtering Capabilities** - Checks for response filtering options
- **Format Control** - Evaluates response format customization
- **Verbose Identifier Detection** - Flags technical IDs that could be simplified
- **Performance Metrics** - Measures response times and sizes

### 🔮 Future Diagnostics (Roadmap)
- **Schema Validation** - Parameter schema compatibility checks
- **Performance Analysis** - Response time and resource usage evaluation
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

### NPX Dependency Audit (Snyk)
Audit the npm package behind an NPX server using Snyk:

```bash
mcp-doctor audit-npx --target "npx firecrawl-mcp"

# JSON output for tooling
mcp-doctor audit-npx --target "npx @scope/server --cli" --output-format json

# Only show high+ severity
mcp-doctor audit-npx --target "npx firecrawl-mcp" --severity-threshold high
```

Requirements:
- Install the Snyk CLI (`snyk`) and run `snyk auth` beforehand.
- Optionally, set `--snyk-path` if `snyk` is not on PATH.

#### Install Snyk CLI

Choose one method that fits your environment:

- macOS (Homebrew):
  ```bash
  brew tap snyk/tap
  brew install snyk
  # verify
  snyk --version
  ```

- Any OS (Node.js/npm):
  ```bash
  npm install -g snyk
  snyk --version
  ```

- Linux/macOS (install script):
  ```bash
  curl -sL https://snyk.io/install.sh | sh
  snyk --version
  ```

- Windows (Chocolatey):
  ```powershell
  choco install snyk -y
  snyk --version
  ```

- Windows (Scoop):
  ```powershell
  scoop bucket add snyk https://github.com/snyk/scoop-snyk
  scoop install snyk
  snyk --version
  ```

Then authenticate the CLI once:

```bash
snyk auth
```

This opens a browser window to complete login; afterwards, you can run
`mcp-doctor audit-npx ...` and Snyk will be able to fetch advisories.

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

### Token Efficiency Analysis Example

```
🩺 MCP Doctor - Server Diagnosis
NPX Command: npx firecrawl-mcp

✅ NPX server launched at http://localhost:3001
✅ Connected! Found 8 tools

🔢 Token Efficiency Analysis
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric                       ┃ Value         ┃ Status                    ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Average Response Size        │ 3,250 tokens  │ ✅ Efficient             │
│ Largest Response             │ 28,500 tokens │ 🚨 Oversized             │
│ Tools Over 25k Tokens        │ 1             │ 🚨 1                     │
│ Tools Successfully Analyzed  │ 8/8           │ ✅ Complete              │
└──────────────────────────────┴───────────────┴───────────────────────────┘

🚨 Token Efficiency Issues Found:
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Tool                         ┃ Severity ┃ Issue                                                                        ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ scrape_url                   │ ⚠️       │ Response contains 28,500 tokens (>25,000 recommended)                       │
│ scrape_url                   │ ℹ️       │ Tool would benefit from filtering capabilities to reduce response size       │
│ list_crawl_jobs              │ ℹ️       │ Tool likely returns collections but doesn't support pagination              │
│ get_crawl_status             │ ℹ️       │ Responses contain verbose technical identifiers (UUIDs, hashes)             │
└──────────────────────────────┴──────────┴──────────────────────────────────────────────────────────────────────────┘

🎯 Token Efficiency Recommendations:
   1. Implement response size limits for 1 tool with oversized responses (>25k tokens)
   2. Add pagination support to 1 tool that returns collections
   3. Add filtering capabilities to 1 tool to reduce response size
   4. Replace verbose technical identifiers with semantic ones in 1 tool
```

## 📋 CLI Reference

### `analyze` Command
Main diagnostic command for MCP servers.

```bash
mcp-doctor analyze [OPTIONS]
```

**Options:**
- `--target TEXT` (required): MCP server URL or NPX command to diagnose
- `--check {descriptions,token_efficiency,all}`: Type of diagnosis to run (default: descriptions)
- `--output-format {table,json,yaml}`: Output format (default: table)
- `--verbose / --no-verbose`: Show detailed diagnostic output (default: False)
- `--timeout INTEGER`: Request timeout in seconds (default: 30)
- `--env-vars TEXT`: Environment variables for NPX command (JSON format)
- `--working-dir TEXT`: Working directory for NPX command
- `--env-file PATH`: Optional .env file loaded before running the command

### `generate-dataset` Command
Create synthetic datasets of MCP tool use cases using Claude or GPT models.

```bash
# Generate 8 tasks using tools fetched from a running server
export ANTHROPIC_API_KEY=sk-ant-example
mcp-doctor generate-dataset --target http://localhost:8000/mcp --num-tasks 8 --llm-timeout 90 --output dataset.json

# Generate 8 tasks using tools from an NPX command
export OPENAI_API_KEY=sk-open-example
mcp-doctor generate-dataset --target "npx firecrawl-mcp" --num-tasks 8 --output dataset.json

# Generate tasks from a local JSON definition using OpenAI
export OPENAI_API_KEY=sk-open-example
mcp-doctor generate-dataset --tools-file tools.json --num-tasks 5

# Generate tasks and upload them to LangSmith
export LANGSMITH_API_KEY=ls-example
mcp-doctor generate-dataset --target http://localhost:8000/mcp --num-tasks 5 \
  --push-to-langsmith --langsmith-project "MCP Evaluation" \
  --langsmith-dataset-name "MCP Doctor Synthetic"
```

Set either `ANTHROPIC_API_KEY` (Claude 4 Sonnet) or `OPENAI_API_KEY` (GPT-4.1) before
running the command. The output is a JSON array containing `prompt`, `tools_called`,
`tools_args`, `retrieved_contexts`, `response`, and `reference` entries ready for
downstream evaluations. Use `--llm-timeout` to extend the wait for slower model responses
when needed (defaults to 60 seconds).

Add `--push-to-langsmith` to stream the generated data straight into your LangSmith
workspace. Provide a key via `--langsmith-api-key` or the `LANGSMITH_API_KEY` environment
variable and optionally customize the dataset name (`--langsmith-dataset-name`), project
tag (`--langsmith-project`), description (`--langsmith-description`), and API endpoint
(`--langsmith-endpoint`). Use `--env-file path/to/.env` when you prefer file-based secrets
over inline JSON.

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

# Run tests with coverage (using pytest-cov)
pytest --cov=src/mcp_analyzer --cov-report=html --cov-report=term

# Or use coverage directly
coverage run -m pytest
coverage report -m
coverage html  # Generate HTML report in htmlcov/
```

### Code Coverage
This project maintains comprehensive test coverage to ensure code quality and reliability:

```bash
# Run tests with coverage reporting
pytest

# Generate detailed HTML coverage report
pytest --cov-report=html
open htmlcov/index.html  # View coverage report

# Check coverage percentage
pytest --cov-report=term-missing

# Set minimum coverage threshold (configured to 29% in pyproject.toml)
pytest
```

**Coverage Features:**
- **Line and branch coverage** - Tracks both line execution and conditional branches
- **Multiple report formats** - HTML, XML, JSON, and terminal reports
- **Coverage thresholds** - Automatic failure if coverage drops below 29% (configurable in pyproject.toml)
- **CI integration** - Automated coverage reporting on pull requests
- **Coverage badges** - Real-time coverage status in README
- **Trend tracking** - Historical coverage data through Codecov and Coveralls

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

## 📚 Documentation

For comprehensive documentation, see the [`docs/`](./docs/) directory:

- **[Token Efficiency Arguments](./docs/token-efficiency-arguments.md)** - How MCP Doctor generates test arguments
- **[Technical Architecture](./docs/token-efficiency-architecture.md)** - Deep dive into implementation details
- **[Documentation Index](./docs/README.md)** - Complete documentation overview

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
