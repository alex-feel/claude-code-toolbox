#!/usr/bin/env bash

# Install-Claude-macOS.sh
# Purpose: Install Node.js and Claude Code CLI on macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh | bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[FAIL]${NC} $1" >&2; }

# Minimum Node.js version
MIN_NODE_VERSION="18.0.0"

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Claude Code macOS Installer${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# Check if running on macOS
check_macos() {
    if [[ "$OSTYPE" != "darwin"* ]]; then
        error "This script is for macOS only"
        exit 1
    fi
}

# Check Node.js version
check_node_version() {
    if command -v node >/dev/null 2>&1; then
        local current_version
        current_version=$(node --version | sed 's/v//')
        if [ "$(printf '%s\n' "$MIN_NODE_VERSION" "$current_version" | sort -V | head -n1)" = "$MIN_NODE_VERSION" ]; then
            success "Node.js $current_version meets minimum requirement (>= $MIN_NODE_VERSION)"
            return 0
        else
            warning "Node.js $current_version is below minimum required version $MIN_NODE_VERSION"
            return 1
        fi
    else
        info "Node.js not found"
        return 1
    fi
}

# Install Homebrew if not present
install_homebrew() {
    if ! command -v brew >/dev/null 2>&1; then
        info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add Homebrew to PATH for Apple Silicon Macs
        if [[ -f "/opt/homebrew/bin/brew" ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi

        success "Homebrew installed"
    else
        info "Homebrew already installed"
    fi
}

# Install Node.js using Homebrew
install_node_homebrew() {
    info "Installing Node.js LTS using Homebrew..."

    # Update Homebrew
    brew update

    # Install Node.js
    if brew list node >/dev/null 2>&1; then
        info "Upgrading Node.js..."
        brew upgrade node
    else
        brew install node
    fi

    success "Node.js installed via Homebrew"
}

# Install Node.js using official installer
install_node_official() {
    info "Installing Node.js using official installer..."

    # Detect architecture
    ARCH=$(uname -m)
    if [[ "$ARCH" == "arm64" ]]; then
        NODE_ARCH="arm64"
    else
        NODE_ARCH="x64"
    fi

    # Get latest LTS version info
    LTS_INFO=$(curl -s https://nodejs.org/dist/index.json | grep -A 10 '"lts":' | head -11)
    VERSION=$(echo "$LTS_INFO" | grep '"version":' | head -1 | sed 's/.*"v\([^"]*\)".*/\1/')

    if [ -z "$VERSION" ]; then
        error "Could not determine latest LTS version"
        return 1
    fi

    # Download and install
    PKG_URL="https://nodejs.org/dist/v${VERSION}/node-v${VERSION}-darwin-${NODE_ARCH}.pkg"
    TEMP_PKG="/tmp/node-installer.pkg"

    info "Downloading Node.js v${VERSION} for ${NODE_ARCH}..."
    curl -fsSL "$PKG_URL" -o "$TEMP_PKG"

    info "Installing Node.js (may require password)..."
    sudo installer -pkg "$TEMP_PKG" -target /

    rm -f "$TEMP_PKG"

    success "Node.js installed via official installer"
}

# Install Claude Code
install_claude() {
    info "Installing Claude Code CLI..."

    # Check if npm is available
    if ! command -v npm >/dev/null 2>&1; then
        error "npm not found. Please install Node.js with npm"
        exit 1
    fi

    # Install Claude Code globally
    if npm install -g @anthropic-ai/claude-code; then
        success "Claude Code installed successfully"
        return 0
    else
        # Try with sudo if permission denied
        warning "Trying with sudo..."
        if sudo npm install -g @anthropic-ai/claude-code; then
            success "Claude Code installed successfully"
            return 0
        else
            error "Failed to install Claude Code"
            return 1
        fi
    fi
}

# Configure shell PATH
configure_path() {
    local npm_prefix
    npm_prefix=$(npm config get prefix)
    local npm_bin="$npm_prefix/bin"

    # Check if npm bin is in PATH
    if [[ ":$PATH:" != *":$npm_bin:"* ]]; then
        warning "npm global bin directory not in PATH"

        # Detect shell and update config
        if [[ "$SHELL" == *"zsh"* ]]; then
            local shell_config="$HOME/.zshrc"
        else
            local shell_config="$HOME/.bash_profile"
        fi

        info "Adding npm bin to PATH in $shell_config"
        echo "" >> "$shell_config"
        echo "# Added by Claude Code installer" >> "$shell_config"
        echo "export PATH=\"\$PATH:$npm_bin\"" >> "$shell_config"

        # Apply to current session
        export PATH="$PATH:$npm_bin"

        success "PATH updated"
    fi
}

# Verify installation
verify_installation() {
    info "Verifying Claude Code installation..."

    if command -v claude >/dev/null 2>&1; then
        success "Claude Code CLI is installed and available"
        return 0
    else
        warning "claude command not found"
        info "Please restart your terminal or run: source ~/.zshrc (or ~/.bash_profile)"
        return 1
    fi
}

# Main installation flow
main() {
    # Check macOS
    check_macos

    # Check for required tools
    if ! command -v curl >/dev/null 2>&1; then
        error "curl is required but not installed"
        exit 1
    fi

    # Step 1: Check/Install Node.js
    info "Step 1/4: Checking Node.js..."
    if ! check_node_version; then
        # Prefer Homebrew installation
        if command -v brew >/dev/null 2>&1 || { info "Homebrew not found"; install_homebrew; }; then
            install_node_homebrew
        else
            install_node_official
        fi

        # Verify Node.js installation
        if ! check_node_version; then
            error "Node.js installation failed or version still below minimum"
            exit 1
        fi
    fi

    # Step 2: Configure PATH
    info "Step 2/4: Configuring environment..."
    configure_path

    # Step 3: Install Claude Code
    info "Step 3/4: Installing Claude Code CLI..."
    if ! install_claude; then
        error "Claude Code installation failed"
        exit 1
    fi

    # Step 4: Verify installation
    info "Step 4/4: Verifying installation..."
    verify_installation

    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""

    if command -v claude >/dev/null 2>&1; then
        info "You can now start using Claude by running: claude"
    else
        info "Please restart your terminal, then run: claude"
    fi
    echo ""
}

# Run main function
main "$@"
