#!/bin/bash
# scripts/local_test.sh

set -e

echo "🧪 Running local component tests..."

# Install project requirements
python -m pip install -q -r requirements.txt

# Ensure fakeredis is installed
python -m pip install -q fakeredis

# Syntax check
python -m py_compile $(git ls-files '*.py')

# Run unit tests
python -m unittest tests.test_components

echo "✅ Local component tests completed successfully"
