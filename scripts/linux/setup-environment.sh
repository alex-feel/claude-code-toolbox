#!/usr/bin/env bash

# Setup-Environment-Linux.sh
# Purpose: Bootstrap uv and run the cross-platform environment setup
# Usage: curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
# To specify configuration:
#   export CLAUDE_ENV_CONFIG=python
#   curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

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

# Check if running on Linux
if [[ "$OSTYPE" != "linux"* ]]; then
    echo -e "${RED}[FAIL]${NC} This script is for Linux only"
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

# Install Python 3.12 via uv (always ensure uv manages its own Python 3.12)
echo -e "${CYAN}[INFO]${NC} Ensuring Python 3.12 is available via uv..."
uv python install 3.12

# Ensure ~/.local/bin is in PATH for current session
export PATH="$HOME/.local/bin:$PATH"

# Run the setup script
echo -e "${CYAN}[INFO]${NC} Running environment setup..."
echo ""

SETUP_SCRIPT_URL="https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/setup_environment.py"
INSTALL_SCRIPT_URL="https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/install_claude.py"

# Check if configuration is specified
CONFIG="${CLAUDE_ENV_CONFIG:-${1:-}}"

if [ -z "$CONFIG" ]; then
    echo -e "${RED}[ERROR]${NC} No configuration specified!"
    echo -e "${YELLOW}Usage: setup-environment.sh <config_name>${NC}"
    echo -e "${YELLOW}   or: CLAUDE_ENV_CONFIG=python ./setup-environment.sh${NC}"
    exit 1
fi

# Build auth arguments
# GITHUB_TOKEN and GITLAB_TOKEN are read directly by Python for per-URL authentication
# Only pass --auth for explicit override (CLAUDE_ENV_AUTH) or generic token (REPO_TOKEN)
AUTH_ARGS=""
if [ -n "${CLAUDE_ENV_AUTH:-}" ]; then
    echo -e "${CYAN}[INFO]${NC} Using provided authentication"
    AUTH_ARGS="--auth $CLAUDE_ENV_AUTH"
elif [ -n "${REPO_TOKEN:-}" ]; then
    echo -e "${CYAN}[INFO]${NC} Generic repo token found, will use for authentication"
    AUTH_ARGS="--auth $REPO_TOKEN"
fi

# Download and run the Python scripts with uv
# Create temp directory to hold both scripts (required for module imports)
TEMP_DIR=$(mktemp -d /tmp/claude_setup.XXXXXX)
trap 'rm -rf "$TEMP_DIR"' EXIT

echo -e "${CYAN}[INFO]${NC} Downloading setup scripts..."
if curl -fsSL "$SETUP_SCRIPT_URL" -o "$TEMP_DIR/setup_environment.py" && \
   curl -fsSL "$INSTALL_SCRIPT_URL" -o "$TEMP_DIR/install_claude.py"; then
    # Change to temp directory so Python can resolve imports
    cd "$TEMP_DIR"
    if [ -n "$AUTH_ARGS" ]; then
        uv run --no-project --python 3.12 setup_environment.py "$CONFIG" $AUTH_ARGS
    else
        uv run --no-project --python 3.12 setup_environment.py "$CONFIG"
    fi
    EXIT_CODE=$?
else
    echo -e "${RED}[FAIL]${NC} Failed to download setup scripts"
    EXIT_CODE=1
fi

exit $EXIT_CODE
