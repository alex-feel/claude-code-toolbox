#!/usr/bin/env bash

#######################################################
# Claude Code Python Environment Setup for macOS
#
# Sets up a complete Python development environment
# with Claude Code, including:
# - Claude Code installation
# - Subagents
# - Custom slash commands
# - MCP server configuration
# - System prompts for Python development
#######################################################

set -euo pipefail

# Configuration
REPO_BASE_URL="https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main"
CLAUDE_USER_DIR="$HOME/.claude"
AGENTS_DIR="$CLAUDE_USER_DIR/agents"
COMMANDS_DIR="$CLAUDE_USER_DIR/commands"
PROMPTS_DIR="$CLAUDE_USER_DIR/prompts"

# List of subagents mentioned in python-developer.md
AGENTS=(
    "code-reviewer"
    "doc-writer"
    "implementation-guide"
    "performance-optimizer"
    "refactoring-assistant"
    "security-auditor"
    "test-generator"
)

# List of slash commands from slash-commands/examples/
COMMANDS=(
    "commit"
    "debug"
    "document"
    "refactor"
    "review"
    "test"
)

# Color codes for macOS Terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Parse command line arguments
SKIP_INSTALL=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-install)
            SKIP_INSTALL=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-install    Skip Claude Code installation"
            echo "  --force          Force overwrite existing files"
            echo "  --help           Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                     # Full setup"
            echo "  $0 --skip-install      # Update configuration only"
            echo "  $0 --force             # Overwrite existing files"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Utility functions
write_step() {
    echo -e "\n${CYAN}🔷 $1${NC}"
}

write_success() {
    echo -e "  ${GREEN}✅ $1${NC}"
}

write_info() {
    echo -e "  ${YELLOW}ℹ️  $1${NC}"
}

write_error() {
    echo -e "  ${RED}❌ $1${NC}"
}

write_header() {
    echo -e "\n${BLUE}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                                                                      ║${NC}"
    echo -e "${BLUE}║       Claude Code Python Environment Setup for macOS                ║${NC}"
    echo -e "${BLUE}║                                                                      ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════════╝${NC}\n"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

ensure_directory() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        write_success "Created directory: $dir"
    fi
}

download_file() {
    local url="$1"
    local destination="$2"
    local filename
    filename=$(basename "$destination")

    # Check if file exists and handle force parameter
    if [[ -f "$destination" ]] && [[ "$FORCE" != "true" ]]; then
        write_info "File already exists: $filename (use --force to overwrite)"
        return
    fi

    # Download the file using curl (standard on macOS)
    if curl -fsSL "$url" -o "$destination"; then
        write_success "Downloaded: $filename"
    else
        write_error "Failed to download: $filename"
        return 1
    fi
}

detect_shell() {
    # Detect user's shell for RC file updates
    if [[ -n "${SHELL:-}" ]]; then
        case "$SHELL" in
            */zsh)
                echo "zsh"
                ;;
            */bash)
                echo "bash"
                ;;
            */fish)
                echo "fish"
                ;;
            *)
                echo "unknown"
                ;;
        esac
    else
        echo "unknown"
    fi
}

# Main script
write_header

# Check macOS version
if [[ "$OSTYPE" != "darwin"* ]]; then
    write_error "This script is designed for macOS only"
    write_info "Please use the appropriate script for your platform:"
    write_info "  - Linux: setup-python-environment.sh"
    write_info "  - Windows: setup-python-environment.ps1"
    exit 1
fi

# Step 1: Install Claude Code if needed
if [[ "$SKIP_INSTALL" != "true" ]]; then
    write_step "Installing Claude Code and dependencies..."

    # Check if Homebrew is installed (common on macOS)
    if command_exists brew; then
        write_info "Homebrew detected, using optimized installation"
    fi

    if curl -fsSL "$REPO_BASE_URL/scripts/macos/install-claude-macos.sh" | bash; then
        write_success "Claude Code installation complete"

        # Source shell config to update PATH
        USER_SHELL=$(detect_shell)
        case "$USER_SHELL" in
            zsh)
                # shellcheck disable=SC1090
                [[ -f ~/.zshrc ]] && source ~/.zshrc
                ;;
            bash)
                # shellcheck disable=SC1090
                [[ -f ~/.bash_profile ]] && source ~/.bash_profile
                # shellcheck disable=SC1090
                [[ -f ~/.bashrc ]] && source ~/.bashrc
                ;;
        esac
    else
        write_error "Failed to install Claude Code"
        write_info "You can retry manually or use --skip-install if Claude Code is already installed"
        exit 1
    fi
else
    write_step "Skipping Claude Code installation (already installed)"

    # Verify Claude Code is available
    if ! command_exists claude; then
        write_error "Claude Code is not available in PATH"
        write_info "Please install Claude Code first or remove the --skip-install flag"
        exit 1
    fi
fi

# Step 2: Download subagents
write_step "Downloading Python-optimized subagents..."
ensure_directory "$AGENTS_DIR"

for agent in "${AGENTS[@]}"; do
    url="$REPO_BASE_URL/agents/examples/${agent}.md"
    destination="$AGENTS_DIR/${agent}.md"
    download_file "$url" "$destination"
done

# Step 3: Download slash commands
write_step "Downloading custom slash commands..."
ensure_directory "$COMMANDS_DIR"

for command in "${COMMANDS[@]}"; do
    url="$REPO_BASE_URL/slash-commands/examples/${command}.md"
    destination="$COMMANDS_DIR/${command}.md"
    download_file "$url" "$destination"
done

# Step 4: Setup MCP servers (Context7)
write_step "Configuring MCP servers..."

# Run in a new shell to ensure Claude Code is available
MCP_COMMAND="claude mcp add --transport http context7 https://mcp.context7.com/mcp"

# Use a subshell with updated PATH
if (export PATH="$HOME/.local/bin:$PATH"; $MCP_COMMAND) 2>/dev/null; then
    write_success "Context7 MCP server configured successfully"
else
    write_info "MCP server may already be configured or requires manual setup"
    write_info "You can manually run: $MCP_COMMAND"
fi

# Step 5: Download system prompt
write_step "Downloading Python developer system prompt..."
ensure_directory "$PROMPTS_DIR"

prompt_url="$REPO_BASE_URL/system-prompts/examples/python-developer.md"
prompt_destination="$PROMPTS_DIR/python-developer.md"
download_file "$prompt_url" "$prompt_destination"

# Step 6: Create a convenience script for starting Claude with the Python prompt
write_step "Creating convenience launcher..."

launcher_path="$CLAUDE_USER_DIR/start-python-claude.sh"
cat > "$launcher_path" << 'EOF'
#!/usr/bin/env bash
# Convenience script to start Claude Code with Python developer prompt

PROMPT_FILE="$HOME/.claude/prompts/python-developer.md"

if [[ -f "$PROMPT_FILE" ]]; then
    echo -e "\033[0;32mStarting Claude Code with Python Developer configuration...\033[0m"
    claude --append-system-prompt "@$PROMPT_FILE" "$@"
else
    echo -e "\033[0;31mPython developer prompt not found at: $PROMPT_FILE\033[0m"
    echo -e "\033[1;33mPlease run setup-python-environment.sh first\033[0m"
    exit 1
fi
EOF

chmod +x "$launcher_path"
write_success "Created launcher script: start-python-claude.sh"

# Step 7: Create macOS-specific app launcher (optional)
write_step "Creating macOS app launcher (optional)..."

applescript_path="$CLAUDE_USER_DIR/ClaudePython.app"
if [[ ! -d "$applescript_path" ]]; then
    osascript << EOF 2>/dev/null || true
tell application "Script Editor"
    set newDoc to make new document with properties {contents:"on run
        do shell script \"$launcher_path\"
    end run"}
    save newDoc as application in POSIX file "$applescript_path"
    close newDoc
end tell
EOF
    if [[ -d "$applescript_path" ]]; then
        write_success "Created macOS app: ClaudePython.app"
        write_info "You can double-click this app to start Claude with Python config"
    fi
fi

# Final message
echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                                      ║${NC}"
echo -e "${GREEN}║                    ✨ Setup Complete! ✨                            ║${NC}"
echo -e "${GREEN}║                                                                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${CYAN}📌 Next Steps:${NC}"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -e "\n1. Open a ${YELLOW}NEW terminal window${NC} (to ensure PATH is updated)"
echo -e "   ${MAGENTA}Tip: Press ⌘+N in Terminal or iTerm2${NC}"

echo -e "\n2. Start Claude Code with Python configuration using ONE of these methods:"
echo -e "\n   ${CYAN}Option A - Using the convenience script:${NC}"
echo -e "   ${BOLD}   $launcher_path${NC}"

echo -e "\n   ${CYAN}Option B - Direct command:${NC}"
echo -e "   ${BOLD}   claude --append-system-prompt \"@$PROMPTS_DIR/python-developer.md\"${NC}"

echo -e "\n   ${CYAN}Option C - With additional flags:${NC}"
echo -e "   ${BOLD}   claude --append-system-prompt \"@$PROMPTS_DIR/python-developer.md\" --model opus --max-turns 20${NC}"

if [[ -d "$applescript_path" ]]; then
    echo -e "\n   ${CYAN}Option D - Double-click the app:${NC}"
    echo -e "   ${BOLD}   $applescript_path${NC}"
fi

echo -e "\n3. ${CYAN}Available features:${NC}"
echo "   • 7 Python-optimized subagents (code review, testing, docs, etc.)"
echo "   • 6 custom slash commands (/commit, /debug, /test, etc.)"
echo "   • Context7 MCP server for up-to-date library documentation"
echo "   • Comprehensive Python development system prompt"

echo -e "\n4. ${CYAN}Test the setup:${NC}"
echo "   After starting Claude, try these commands:"
echo -e "   • ${YELLOW}/help${NC} - See all available commands"
echo -e "   • ${YELLOW}/agents${NC} - List available subagents"
echo -e "   • ${YELLOW}Task: Review this code for quality${NC} - Trigger code-reviewer subagent"

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "\n${CYAN}📁 Configuration locations:${NC}"
echo "   Agents:   $AGENTS_DIR"
echo "   Commands: $COMMANDS_DIR"
echo "   Prompts:  $PROMPTS_DIR"

# Shell-specific alias suggestions
USER_SHELL=$(detect_shell)
echo -e "\n${YELLOW}💡 Add an alias for quick access:${NC}"
case "$USER_SHELL" in
    zsh)
        echo -e "   Add to ${BOLD}~/.zshrc${NC}:"
        echo -e "   ${BOLD}alias claude-python='$launcher_path'${NC}"
        ;;
    bash)
        echo -e "   Add to ${BOLD}~/.bash_profile${NC}:"
        echo -e "   ${BOLD}alias claude-python='$launcher_path'${NC}"
        ;;
    fish)
        echo -e "   Add to ${BOLD}~/.config/fish/config.fish${NC}:"
        echo -e "   ${BOLD}alias claude-python '$launcher_path'${NC}"
        ;;
    *)
        echo -e "   Add to your shell config:"
        echo -e "   ${BOLD}alias claude-python='$launcher_path'${NC}"
        ;;
esac

echo -e "\n${MAGENTA}🍎 macOS Tip: You can add the ClaudePython app to your Dock for easy access!${NC}"
echo ""
