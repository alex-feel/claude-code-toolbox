#!/usr/bin/env bash

# Install-Claude-Linux.sh
# Purpose: Install Node.js and Claude Code CLI on Linux
# Usage: curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash

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
echo -e "${CYAN}  Claude Code Linux Installer${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# Detect Linux distribution
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    elif [ -f /etc/debian_version ]; then
        echo "debian"
    elif [ -f /etc/redhat-release ]; then
        echo "rhel"
    else
        echo "unknown"
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

# Install Node.js for Debian/Ubuntu
install_node_debian() {
    info "Installing Node.js LTS for Debian/Ubuntu..."

    # Install prerequisites
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg

    # Add NodeSource repository
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -

    # Install Node.js
    sudo apt-get install -y nodejs

    success "Node.js installed via NodeSource"
}

# Install Node.js for RHEL/Fedora/CentOS
install_node_rhel() {
    info "Installing Node.js LTS for RHEL/Fedora/CentOS..."

    # Install prerequisites
    sudo dnf install -y curl

    # Add NodeSource repository
    curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -

    # Install Node.js
    sudo dnf install -y nodejs

    success "Node.js installed via NodeSource"
}

# Install Node.js for Arch Linux
install_node_arch() {
    info "Installing Node.js LTS for Arch Linux..."

    # Install Node.js and npm
    sudo pacman -Sy --noconfirm nodejs npm

    success "Node.js installed via pacman"
}

# Generic Node.js installation using nvm
install_node_generic() {
    info "Installing Node.js using nvm..."

    # Install nvm if not present
    if ! command -v nvm >/dev/null 2>&1; then
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

        # Source nvm
        export NVM_DIR="$HOME/.nvm"
        [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    fi

    # Install and use LTS Node.js
    nvm install --lts
    nvm use --lts

    success "Node.js installed via nvm"
}

# Install Node.js based on distribution
install_node() {
    local distro
    distro=$(detect_distro)

    case "$distro" in
        ubuntu|debian|linuxmint|pop)
            install_node_debian
            ;;
        fedora|rhel|centos|rocky|almalinux)
            install_node_rhel
            ;;
        arch|manjaro)
            install_node_arch
            ;;
        *)
            warning "Unknown distribution: $distro"
            install_node_generic
            ;;
    esac
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

# Verify installation
verify_installation() {
    info "Verifying Claude Code installation..."

    if command -v claude >/dev/null 2>&1; then
        success "Claude Code CLI is installed and available"
        return 0
    else
        warning "claude command not found. You may need to add npm global bin to PATH"
        echo ""
        info "Add this to your ~/.bashrc or ~/.zshrc:"
        echo 'export PATH="$PATH:$(npm config get prefix)/bin"'
        echo ""
        info "Then reload your shell and run: claude"
        return 1
    fi
}

# Main installation flow
main() {
    # Check for required tools
    if ! command -v curl >/dev/null 2>&1; then
        error "curl is required but not installed"
        exit 1
    fi

    # Step 1: Check/Install Node.js
    info "Step 1/3: Checking Node.js..."
    if ! check_node_version; then
        install_node

        # Verify Node.js installation
        if ! check_node_version; then
            error "Node.js installation failed or version still below minimum"
            exit 1
        fi
    fi

    # Step 2: Install Claude Code
    info "Step 2/3: Installing Claude Code CLI..."
    if ! install_claude; then
        error "Claude Code installation failed"
        exit 1
    fi

    # Step 3: Verify installation
    info "Step 3/3: Verifying installation..."
    verify_installation

    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    info "You can now start using Claude by running: claude"
    echo ""
}

# Run main function
main "$@"
