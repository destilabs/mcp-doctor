#!/bin/bash

# Linting script for mcp-analyzer
# Run this script to check code formatting and style

set -e

echo "🔍 Running linting checks..."

echo "🧹 Static analysis with ruff..."
ruff check src/ tests/

echo "📝 Checking code formatting with black..."
black --check --diff src/ tests/

echo "📦 Checking import sorting with isort..."
isort --check-only --diff src/ tests/

echo "🔍 Running type checks with mypy..."
mypy src/ --ignore-missing-imports --no-strict-optional --allow-untyped-defs || {
    echo "⚠️  Mypy found type issues but this won't fail the script yet"
    echo "   Consider fixing these gradually as you work on the code"
}

echo "✅ All linting checks completed!"
