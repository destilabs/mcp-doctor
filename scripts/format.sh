#!/bin/bash

# Auto-formatting script for mcp-analyzer
# Run this script to automatically format your code

set -e

echo "🔧 Auto-formatting code..."

echo "📝 Formatting code with black..."
black src/ tests/

echo "📦 Sorting imports with isort..."
isort src/ tests/

echo "✅ Code formatting completed!"
