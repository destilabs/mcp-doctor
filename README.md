# MCP Analyzer

🔍 **CLI tool for analyzing MCP servers for agent-friendliness**

Based on Anthropic's best practices from ["Writing effective tools for agents — with agents"](https://www.anthropic.com/engineering/writing-tools-for-agents), this tool helps you evaluate and improve your MCP (Model Context Protocol) servers to make them more effective for AI agents.

## Features

- 📝 **AI-Readable Description Analysis** - Check tool descriptions for clarity, context, and agent-friendliness
- 🎯 **Actionable Recommendations** - Get specific suggestions for improving your tools
- 📊 **Rich Reports** - Beautiful terminal output with detailed statistics
- 🔄 **Multiple Output Formats** - Table, JSON, and YAML output options
- ⚡ **Fast Analysis** - Async connections and efficient processing

## Installation

### From PyPI (when published)
```bash
pip install mcp-analyzer
```

### Development Installation
```bash
# Clone and install in development mode
git clone <repository-url>
cd mcp-analyzer
pip install -e .
```

### Dependencies
- Python 3.8+
- typer (CLI framework)
- httpx (HTTP client)
- rich (Terminal UI)
- pydantic (Data validation)

## Quick Start

### Basic Analysis
```bash
# Analyze your local HTTP MCP server
mcp-analyzer analyze --target http://localhost:8000/mcp

# Analyze NPX-launched MCP server
mcp-analyzer analyze --target "npx firecrawl-mcp"

# Analyze NPX server with environment variables
mcp-analyzer analyze --target "export FIRECRAWL_API_KEY=your_key && npx firecrawl-mcp"

# Analyze with verbose output
mcp-analyzer analyze --target http://localhost:8000/mcp --verbose

```

### Output Formats
```bash
# Table output (default) - beautiful terminal display
mcp-analyzer analyze --target http://localhost:8000/mcp --output-format table

# JSON output - for programmatic use
mcp-analyzer analyze --target "npx firecrawl-mcp" --output-format json > analysis.json

# YAML output - human-readable structured data
mcp-analyzer analyze --target http://localhost:8000/mcp --output-format yaml
```

## Example Output

```
🔍 Analyzing MCP Server
Server: http://localhost:8000/mcp
Check Type: descriptions

✅ Connected! Found 45 tools

📝 AI-Readable Description Analysis
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Metric                       ┃    Count ┃ Percentage ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━┩
│ ✅ Passed                    │       23 │      51.1% │
│ ⚠️  Warnings                 │       15 │      68.2% │
│ ❌ Errors                    │        7 │      31.8% │
│ ℹ️  Info                     │        0 │       0.0% │
└──────────────────────────────┴──────────┴────────────┘

🎯 Top Recommendations:
   1. Add descriptions to 7 tools that are missing them entirely
   2. Rename 15 ambiguous parameters to be more descriptive  
   3. Expand descriptions for 8 tools that have very brief descriptions
   4. Add usage context to 12 tools to help agents understand when to use them
```

## API Reference

### CLI Commands

#### `analyze`
Main command to analyze an MCP server.

```bash
mcp-analyzer analyze [OPTIONS]
```

**Options:**
- `--target TEXT` (required): MCP server URL or NPX command to analyze
- `--check {descriptions,schemas,performance,all}`: Type of analysis to run (default: descriptions)
- `--output-format {table,json,yaml}`: Output format (default: table)
- `--verbose / --no-verbose`: Show detailed suggestions (default: False)
- `--timeout INTEGER`: Request timeout in seconds (default: 30)
- `--env-vars TEXT`: Environment variables for NPX command (JSON format)
- `--working-dir TEXT`: Working directory for NPX command


#### `version`
Show version information.

```bash
mcp-analyzer version
```

## Integration Examples

### CI/CD Pipeline
```yaml
# GitHub Actions example
- name: Analyze MCP Server
  run: |
    # Start your MCP server
    python main.py &
    sleep 5
    
    # Run analysis
    mcp-analyzer analyze --server-url http://localhost:8000/mcp --output-format json > mcp-analysis.json
    
    # Fail if critical issues found
    python -c "
    import json
    with open('mcp-analysis.json') as f:
        results = json.load(f)
    errors = results['checks']['descriptions']['statistics']['errors']
    if errors > 0:
        exit(1)
    "
```

### Programmatic Use

#### HTTP Server Analysis
```python
import asyncio
from mcp_analyzer.mcp_client import MCPClient
from mcp_analyzer.checkers.descriptions import DescriptionChecker

async def analyze_http_server():
    client = MCPClient("http://localhost:8000/mcp")
    
    try:
        tools = await client.get_tools()
        
        checker = DescriptionChecker()
        results = checker.analyze_tool_descriptions(tools)
        
        return results
    finally:
        await client.close()

# Run analysis
results = asyncio.run(analyze_http_server())
print(f"Found {len(results['issues'])} issues")
```


## Development

### Project Structure
```
mcp-analyzer/
├── pyproject.toml          # Project configuration
├── src/mcp_analyzer/       # Main package
│   ├── cli.py              # CLI interface
│   ├── mcp_client.py       # MCP server communication
│   ├── reports.py          # Output formatting
│   ├── utils.py            # Utility functions
│   └── checkers/           # Analysis modules
│       ├── descriptions.py # Description analysis
│       └── ...             # Future analyzers
└── tests/                  # Test suite
```

### Running Tests
```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=mcp_analyzer
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## Roadmap

### Version 0.2.0
- [ ] Schema validation analysis
- [ ] Performance benchmarking
- [ ] Tool interaction patterns

### Version 0.3.0
- [ ] Agent simulation testing
- [ ] Automated improvement suggestions
- [ ] Integration with popular MCP frameworks

### Version 1.0.0
- [ ] Complete evaluation framework
- [ ] Agent-driven optimization
- [ ] Production monitoring capabilities

## License

MIT License - see LICENSE file for details.

## Related Projects

- [Model Context Protocol](https://github.com/modelcontextprotocol/servers) - Official MCP servers
- [Anthropic's MCP Guide](https://www.anthropic.com/engineering/writing-tools-for-agents) - Best practices reference

## Support

- 🐛 [Report Issues](https://github.com/destilabs/mcp-analyzer/issues)
- 💬 [Discussions](https://github.com/destilabs/mcp-analyzer/discussions)
- 🌐 [Destilabs](https://destilabs.com) - AI engineering and consulting

---

**Built with ❤️ for the AI agent development community**
