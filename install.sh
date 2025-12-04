#!/usr/bin/env bash
#
# Installation script for phenotype comparison pipeline using uv
#
# This script installs all dependencies needed to run run_pipeline.py
# using uv (https://github.com/astral-sh/uv)
#
# Usage:
#   ./install.sh

set -e

echo "==================================================================="
echo "Installing dependencies for phenotype comparison pipeline with uv"
echo "==================================================================="

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed."
    echo "Please install uv first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "Or visit: https://github.com/astral-sh/uv"
    exit 1
fi

echo "Found uv: $(uv --version)"
echo ""

# Create/sync virtual environment and install dependencies
echo "Creating virtual environment and installing dependencies..."
echo ""

# Install oaklib with semsimian support from git
# This matches the Jenkinsfile line 72:
# './venv/bin/pip install "oaklib[semsimian] @ git+https://github.com/INCATools/ontology-access-kit.git"'
echo "Installing oaklib[semsimian] from git..."
uv pip install "oaklib[semsimian] @ git+https://github.com/INCATools/ontology-access-kit.git"

echo ""
echo "==================================================================="
echo "Installation complete!"
echo "==================================================================="
echo ""
echo "You can now run the pipeline with:"
echo "  python run_pipeline.py"
echo ""
echo "Or use the Makefile targets:"
echo "  make setup    # Download tools and data"
echo "  make all      # Run full pipeline"
echo "  make hp-hp    # Run HP vs HP comparison only"
echo ""
echo "For more options, run:"
echo "  python run_pipeline.py --help"
echo "  make help"
echo ""
