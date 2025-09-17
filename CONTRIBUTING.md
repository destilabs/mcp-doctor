# Contributing to MCP Doctor 🤝

Thank you for your interest in contributing to MCP Doctor! We welcome contributions from everyone.

## 🚀 Quick Start

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/mcp-doctor.git
   cd mcp-doctor
   ```
3. **Set up development environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e ".[dev]"
   ```

## 🧪 Development Workflow

### Running Tests
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_descriptions.py -v

# Run with coverage
coverage run -m pytest tests/
coverage report -m
```

### Code Formatting
```bash
# Format code
black src/ tests/
isort src/ tests/

# Check formatting
black --check --diff src/ tests/
isort --check-only --diff src/ tests/
```

### Type Checking
```bash
mypy src/ --ignore-missing-imports --no-strict-optional --allow-untyped-defs
```

## 📝 Contribution Guidelines

### Code Style
- Follow PEP 8 guidelines
- Use Black for code formatting
- Use isort for import sorting
- Add type hints where possible
- Write descriptive docstrings

### Testing
- Write tests for new features
- Maintain or improve test coverage
- Test both success and error cases
- Use descriptive test names

### Commit Messages
Use conventional commit format:
```
type(scope): description

feat(checker): add new diagnostic for parameter validation
fix(client): handle connection timeout gracefully
docs(readme): update installation instructions
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## 🐛 Reporting Issues

Before creating an issue, please:
1. **Search existing issues** to avoid duplicates
2. **Use the issue templates** provided
3. **Include reproduction steps** for bugs
4. **Provide context** about your use case

## 💡 Feature Requests

We love new ideas! When suggesting features:
1. **Explain the problem** you're trying to solve
2. **Describe your proposed solution**
3. **Consider the scope** - does it fit MCP Doctor's goals?
4. **Think about implementation** - are you willing to contribute?

## 🔄 Pull Request Process

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the guidelines above

3. **Test your changes**:
   ```bash
   python -m pytest tests/ -v
   black --check src/ tests/
   isort --check-only src/ tests/
   ```

4. **Update documentation** if needed

5. **Create a pull request** with:
   - Clear title and description
   - Reference any related issues
   - Include screenshots/demos if relevant

6. **Respond to feedback** from maintainers

## 🏗️ Development Setup Details

### Project Structure
```
mcp-doctor/
├── src/mcp_analyzer/          # Main package
│   ├── checkers/              # Diagnostic checkers
│   ├── cli.py                 # Command-line interface
│   ├── mcp_client.py         # MCP client implementations
│   └── reports.py            # Report generation
├── tests/                     # Test suite
├── docs/                      # Documentation
└── scripts/                   # Development scripts
```

### Key Components
- **Checkers**: Implement diagnostic logic
- **Clients**: Handle MCP server communication
- **Reports**: Generate output in various formats
- **CLI**: Command-line interface using Typer

### Adding New Diagnostics

1. **Create checker class** in `src/mcp_analyzer/checkers/`
2. **Implement analysis logic** following existing patterns
3. **Add comprehensive tests** in `tests/`
4. **Update CLI integration** if needed
5. **Document the new diagnostic** in README

## 🤔 Questions?

- **GitHub Discussions**: For general questions and ideas
- **Issues**: For bugs and specific feature requests
- **Email**: mykhailo.kushnir@destilabs.com for private matters

## 📜 Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please:
- Be respectful and constructive
- Focus on what's best for the community
- Show empathy towards other contributors
- Accept constructive criticism gracefully

## 🙏 Recognition

Contributors will be recognized in:
- GitHub contributors list
- Release notes for significant contributions
- README acknowledgments section (coming soon)

Thank you for helping make MCP Doctor better! 🎉
