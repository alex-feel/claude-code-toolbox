#!/usr/bin/env bash

# Install-Claude-macOS.sh
# Purpose: Bootstrap uv and run the cross-platform Claude installer
# Usage: curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh | bash

set -euo pipefail

# Colors for output
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# The Python version the installer runs on, named once for the run, the
# interpreter check and the repair hint
PYTHON_VERSION="3.12"

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Claude Code macOS Installer (Bootstrap)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}[FAIL]${NC} This script is for macOS only"
    exit 1
fi

# Refuse to run as root unless explicitly allowed
if [ "$(id -u)" -eq 0 ] && [ "${CLAUDE_CODE_TOOLBOX_ALLOW_ROOT:-}" != "1" ]; then
    echo -e "${RED}[FAIL]${NC} This script should NOT be run as root or with sudo"
    echo ""
    echo -e "${YELLOW}[WARN]${NC} Running as root creates configuration under /root/,"
    echo -e "${YELLOW}[WARN]${NC} not for the regular user you intend to configure."
    echo ""
    echo -e "${CYAN}[INFO]${NC} Instead, run as your regular user:"
    echo -e "${CYAN}[INFO]${NC}   curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh | bash"
    echo ""
    echo -e "${CYAN}[INFO]${NC} The installer will request sudo only when needed (e.g., npm)."
    echo -e "${CYAN}[INFO]${NC} To force root execution: CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1 bash <script>"
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

# Run the Python installer script
echo -e "${CYAN}[INFO]${NC} Running Claude Code installer..."
echo ""

SCRIPT_URL="https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/install_claude.py"

# Download to temp file to avoid E2BIG (Argument list too long) error.
# When piped via stdin, uv constructs 'python -c "<entire_script>"' as a single
# execve() argument. Scripts exceeding Linux MAX_ARG_STRLEN (128 KiB) fail.
# See: https://github.com/astral-sh/uv/issues/11220
TEMP_DIR=$(mktemp -d /tmp/claude_install.XXXXXX)
trap 'rm -rf "$TEMP_DIR"' EXIT

if curl -fsSL "$SCRIPT_URL" -o "$TEMP_DIR/install_claude.py"; then
    EXIT_CODE=0
    uv run --no-project --python "$PYTHON_VERSION" "$TEMP_DIR/install_claude.py" || EXIT_CODE=$?
    if [ "$EXIT_CODE" -ne 0 ]; then
        echo -e "${RED}[FAIL]${NC} Installation failed"
    fi
    # uv python find never downloads, so after a failed run it tells whether uv
    # can provide the interpreter now; only its exit status is read, and the
    # wrapper still exits with the code uv run returned
    if [ "$EXIT_CODE" -ne 0 ] && ! uv python find "$PYTHON_VERSION" >/dev/null 2>&1; then
        echo ""
        echo -e "${RED}[FAIL]${NC} uv cannot provide Python ${PYTHON_VERSION}, which the installer runs on."
        echo -e "${RED}[FAIL]${NC} Install it with: uv python install --reinstall ${PYTHON_VERSION}"
        echo -e "${RED}[FAIL]${NC} This installs Python ${PYTHON_VERSION}, or replaces a uv-managed copy whose files are missing; then run this install command again."
    fi
else
    echo -e "${RED}[FAIL]${NC} Failed to download installer script"
    EXIT_CODE=1
fi

exit $EXIT_CODE
