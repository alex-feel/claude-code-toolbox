#!/usr/bin/env bash

# Setup-Environment-macOS.sh
# Purpose: Bootstrap uv and run the cross-platform environment setup
# Usage: curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash
# To specify configuration:
#   CLAUDE_ENV_CONFIG=python curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

set -euo pipefail

# Colors for output
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Claude Code Environment Setup (Bootstrap)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}[FAIL]${NC} This script is for macOS only"
    exit 1
fi

# Check if uv is installed
if ! command -v uv >/dev/null 2>&1; then
    echo -e "${CYAN}[INFO]${NC} Installing uv (Python package manager)..."

    # Install uv using the official installer
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        # Add uv to PATH for current session
        export PATH="$HOME/.local/bin:$PATH"
        echo -e "${GREEN}[OK]${NC}   uv installed successfully"
    else
        echo -e "${RED}[FAIL]${NC} Failed to install uv"
        echo ""
        echo -e "${YELLOW}Please install uv manually from: https://docs.astral.sh/uv/${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}[OK]${NC}   uv is already installed"
fi

# Run the setup script
echo -e "${CYAN}[INFO]${NC} Running environment setup..."
echo ""

SCRIPT_URL="https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/setup_environment.py"

# Check if configuration is specified
CONFIG="${CLAUDE_ENV_CONFIG:-$1}"

if [ -z "$CONFIG" ]; then
    echo -e "${RED}[ERROR]${NC} No configuration specified!"
    echo -e "${YELLOW}Usage: setup-environment.sh <config_name>${NC}"
    echo -e "${YELLOW}   or: CLAUDE_ENV_CONFIG=python ./setup-environment.sh${NC}"
    exit 1
fi

# Download and run the Python script with uv
# uv will handle Python installation automatically
if curl -fsSL "$SCRIPT_URL" | uv run --python '>=3.12' - "$CONFIG"; then
    exit 0
else
    echo -e "${RED}[FAIL]${NC} Setup failed"
    exit 1
fi
