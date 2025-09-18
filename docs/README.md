# MCP Doctor Documentation

Welcome to the comprehensive documentation for MCP Doctor - the diagnostic tool for MCP (Model Context Protocol) servers.

## 📚 Documentation Index

### Core Concepts
- [Token Efficiency Arguments](./token-efficiency-arguments.md) - How MCP Doctor automatically generates test arguments for tools
- [Technical Architecture](./token-efficiency-architecture.md) - Deep dive into implementation details and algorithms

### Features
- **Tool Description Analysis** - Static analysis of tool descriptions and parameters
- **Token Efficiency Analysis** - Dynamic testing of tool response sizes and optimization
- **CLI Interface** - Command-line usage and options
- **Python API** - Programmatic usage in Python applications

### Advanced Topics
- **Architecture Overview** - How MCP Doctor works internally
- **Custom Checkers** - Creating your own diagnostic modules
- **Performance Optimization** - Tips for faster analysis
- **Security Considerations** - Safe handling of sensitive data

### Troubleshooting
- [Token Efficiency Troubleshooting](./troubleshooting-token-efficiency.md) - Solutions for token efficiency analysis issues
- **Common Issues** - Solutions to frequent problems
- **Debugging Guide** - How to debug analysis issues
- **FAQ** - Frequently asked questions

## 🚀 Quick Start

```bash
# Install MCP Doctor
pip install mcp-doctor

# Analyze tool descriptions
mcp-doctor analyze --target "npx your-mcp-server"

# Analyze token efficiency
mcp-doctor analyze --target "npx your-mcp-server" --check token_efficiency

# Run all available checks
mcp-doctor analyze --target "npx your-mcp-server" --check all
```

## 🎯 Key Features

### 📝 Tool Description Analysis
Evaluates MCP tools for AI agent compatibility:
- Description clarity and completeness
- Parameter naming conventions
- Usage context and examples
- Technical jargon detection

### 🔢 Token Efficiency Analysis
Measures actual tool performance:
- Response size measurement (following Anthropic's 25k token guideline)
- Pagination and filtering capability detection
- Verbose identifier flagging
- Performance metrics collection

## 🏗️ Architecture

MCP Doctor is built with a modular architecture:

```
mcp-doctor/
├── src/mcp_analyzer/
│   ├── cli.py              # Command-line interface
│   ├── mcp_client.py       # MCP server communication
│   ├── mcp_stdio_client.py # STDIO transport
│   ├── mcp_sse_client.py   # SSE transport
│   ├── reports.py          # Output formatting
│   └── checkers/           # Diagnostic modules
│       ├── descriptions.py      # Description analysis
│       └── token_efficiency.py  # Token efficiency analysis
└── tests/                  # Test suite
```

## 🤝 Contributing

MCP Doctor is open source and welcomes contributions:

1. **Bug Reports** - Found an issue? Please report it
2. **Feature Requests** - Have an idea? We'd love to hear it
3. **Code Contributions** - Pull requests are welcome
4. **Documentation** - Help improve these docs

## 🔗 Related Resources

- [Anthropic's Tool Writing Guide](https://www.anthropic.com/engineering/writing-tools-for-agents) - Best practices for AI agent tools
- [Model Context Protocol](https://github.com/modelcontextprotocol/servers) - Official MCP specification and servers
- [MCP Doctor GitHub](https://github.com/destilabs/mcp-doctor) - Source code and issue tracker

## 📞 Support

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/destilabs/mcp-doctor/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/destilabs/mcp-doctor/discussions)
- 🌐 **Professional Support**: [Destilabs](https://destilabs.com)

---

**Built with ❤️ by [Destilabs](https://destilabs.com) for the AI agent development community**
