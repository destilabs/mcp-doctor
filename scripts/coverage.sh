#!/bin/bash
set -e

echo "🧪 Running tests with coverage..."

python -m pytest --cov=src/mcp_analyzer \
                  --cov-report=term-missing \
                  --cov-report=html \
                  --cov-report=xml \
                  --cov-branch \
                  --cov-fail-under=29 \
                  -v

echo ""
echo "📊 Coverage reports generated:"
echo "  - Terminal: displayed above"
echo "  - HTML: htmlcov/index.html"
echo "  - XML: coverage.xml"

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo ""
    echo "🌐 Opening HTML coverage report..."
    open htmlcov/index.html
fi

echo ""
echo "✅ Coverage analysis complete!"
