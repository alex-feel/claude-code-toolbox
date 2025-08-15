# Python Development Environment Setup Guide

Complete guide for setting up Claude Code as a powerful Python development environment with automated configuration, specialized subagents, and professional tooling.

## 🚀 Quick Start

Choose your platform and run one command:

### Windows
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-python-environment.ps1')"
```

### macOS
```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-python-environment.sh | bash
```

### Linux
```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-python-environment.sh | bash
```

## 📦 What Gets Installed

The Python environment setup provides a complete development ecosystem:

### 1. Claude Code CLI
- Latest version of Claude Code
- All required dependencies (Git, Node.js)
- Proper PATH configuration
- Environment variables setup

### 2. Python-Optimized Subagents (7 total)

| Subagent | Purpose | Invocation Trigger |
|----------|---------|-------------------|
| **code-reviewer** | Code quality analysis, bug detection, security review | "Review this code" |
| **doc-writer** | Generate documentation, docstrings, README files | "Document this" |
| **implementation-guide** | Library usage, best practices, API guidance | "How do I implement" |
| **performance-optimizer** | Profile code, identify bottlenecks, optimize | "Optimize performance" |
| **refactoring-assistant** | Code restructuring, design patterns, cleanup | "Refactor this" |
| **security-auditor** | Vulnerability assessment, security best practices | "Check security" |
| **test-generator** | Create unit tests, integration tests, fixtures | "Write tests" |

### 3. Custom Slash Commands (6 total)

| Command | Description | Usage |
|---------|-------------|-------|
| `/commit` | Smart Git commits with conventional format | `/commit fix: resolve issue` |
| `/debug` | Interactive debugging assistance | `/debug error in function` |
| `/document` | Generate comprehensive documentation | `/document this module` |
| `/refactor` | Code improvement suggestions | `/refactor for readability` |
| `/review` | In-depth code review | `/review security concerns` |
| `/test` | Generate test suites | `/test edge cases` |

### 4. Context7 MCP Server

Provides up-to-date documentation for Python libraries:
- FastAPI, Django, Flask
- NumPy, Pandas, SciPy
- LangChain, LangGraph
- PyTorch, TensorFlow
- And many more...

### 5. Python Developer System Prompt

A comprehensive 364-line system prompt that configures Claude Code as a senior Python developer with:
- Test-Driven Development (TDD) practices
- Async-first implementation
- Package management with `uv`
- Pre-commit hooks and quality gates
- Concurrent execution patterns
- Production-ready code standards

### 6. Convenience Launcher

Platform-specific launcher scripts for quick startup:
- **Windows**: `start-python-claude.ps1`
- **Linux/macOS**: `start-python-claude.sh`
- **macOS App**: `ClaudePython.app` (optional)

## 🎯 Features & Benefits

### Professional Python Development

- **Full-Stack Support**: Backend (FastAPI, Django) + Frontend (if needed)
- **Modern Tooling**: uv, pytest, pre-commit, ruff, mypy
- **Best Practices**: PEP 8, type hints, docstrings, clean architecture
- **Async-First**: asyncio, aiohttp, async database drivers

### Intelligent Assistance

- **Proactive Subagents**: Automatically triggered for relevant tasks
- **Context-Aware**: Understands your codebase and project structure
- **Library Expertise**: Real-time documentation from Context7
- **Error Prevention**: Catches issues before they reach production

### Workflow Optimization

- **Automated Testing**: Generate comprehensive test suites
- **Smart Commits**: Conventional commits with proper formatting
- **Documentation Generation**: From docstrings to full API docs
- **Performance Profiling**: Identify and fix bottlenecks

## 📋 Installation Details

### Prerequisites

#### All Platforms
- Internet connection
- 4GB+ RAM recommended
- 500MB free disk space

#### Windows Specific
- Windows 10/11
- PowerShell 5.1+
- Admin rights (auto-elevation)

#### macOS Specific
- macOS 10.15+ (Catalina or later)
- Xcode Command Line Tools
- Admin password for system packages

#### Linux Specific
- Bash 4.0+
- sudo privileges
- curl or wget

### Installation Process

The setup script performs these steps:

1. **System Check**
   - Verify OS compatibility
   - Check existing installations
   - Detect package managers

2. **Dependency Installation**
   - Git (if not present)
   - Node.js LTS (v18+)
   - Platform-specific tools

3. **Claude Code Installation**
   - Download latest version
   - Configure PATH
   - Verify with `claude doctor`

4. **Configuration Download**
   - Fetch subagents to `~/.claude/agents/`
   - Install commands to `~/.claude/commands/`
   - Set up prompts in `~/.claude/prompts/`

5. **MCP Server Setup**
   - Configure Context7 server
   - Test connectivity
   - Enable for all projects

6. **Final Setup**
   - Create launcher scripts
   - Update shell configuration
   - Display usage instructions

## 🔧 Configuration

### Directory Structure

After installation, your configuration lives in:

```text
~/.claude/                      # User-level Claude directory
├── agents/                     # Subagent configurations
│   ├── code-reviewer.md
│   ├── doc-writer.md
│   ├── implementation-guide.md
│   ├── performance-optimizer.md
│   ├── refactoring-assistant.md
│   ├── security-auditor.md
│   └── test-generator.md
├── commands/                   # Slash commands
│   ├── commit.md
│   ├── debug.md
│   ├── document.md
│   ├── refactor.md
│   ├── review.md
│   └── test.md
├── prompts/                    # System prompts
│   └── python-developer.md
├── settings.json               # User settings
├── mcp.json                    # MCP server config
└── start-python-claude.sh/ps1  # Launcher script
```

### Customization Options

#### Modify System Prompt

Edit `~/.claude/prompts/python-developer.md` to customize:
- Coding standards
- Framework preferences
- Testing approaches
- Documentation style

#### Add Custom Subagents

Create new agents in `~/.claude/agents/`:
```yaml
---
name: my-custom-agent
description: What this agent does
tools: Read, Write, Edit
---

Your agent instructions here...
```

#### Configure MCP Servers

Edit `~/.claude/mcp.json` to add more servers:
```json
{
  "servers": {
    "context7": {
      "transport": "http",
      "url": "https://mcp.context7.com/mcp"
    }
  }
}
```

## 💻 Usage Examples

### Starting Claude Code

#### ⚠️ CRITICAL: You MUST Load the System Prompt

After setup, you have two options to use Claude with the Python configuration:

##### Option 1: Use the Global Command (RECOMMENDED)
```bash
# Just run (works on all platforms):
claude-python
```
The setup script automatically registers this command globally.

##### Option 2: Manually Specify the System Prompt
```bash
# Every time you start Claude, include the prompt:
claude --append-system-prompt "@$HOME/.claude/prompts/python-developer.md"

# With additional options
claude --append-system-prompt "@$HOME/.claude/prompts/python-developer.md" --model opus --max-turns 20
```

#### ❌ THIS WILL NOT WORK
```bash
# WRONG - This does NOT use the Python system prompt!
claude "Create a FastAPI project"  # ❌ No system prompt loaded!
```

#### Basic Commands (After Starting with System Prompt)
```bash
# Check installation (run before starting Claude)
claude doctor

# After starting with launcher or system prompt:
/help           # List available commands
/agents         # Show configured agents
Task: Show me FastAPI streaming response docs  # This will work
```

### Python Development Workflows

#### ⚡ IMPORTANT: Start Claude First

Always start Claude with the Python system prompt BEFORE running these commands:

```bash
# STEP 1: Start Claude with Python configuration
claude-python

# STEP 2: Now you can use these commands inside Claude:
```

#### Creating a New Project
```python
# Inside Claude (after starting with system prompt):
Create a new FastAPI project with async SQLAlchemy, Alembic migrations, and pytest setup
```

#### Code Review
```python
# Inside Claude:
Review api/endpoints/users.py for security and performance

# Or use slash command:
/review focus on SQL injection vulnerabilities
```

#### Test Generation
```python
# Inside Claude:
Write tests for the UserService class with mocking and edge cases

# Or use slash command:
/test create integration tests for auth flow
```

#### Documentation
```python
# Inside Claude slash commands:
/document add comprehensive docstrings to all functions

# Or regular prompt:
Create a professional README with badges, examples, and API documentation
```

#### Performance Optimization
```python
# Inside Claude:
Profile and optimize the data processing pipeline in etl/transform.py
```

#### Debugging
```python
# Inside Claude slash command:
/debug AsyncIO warning: coroutine was never awaited
```

## 🔄 Updates and Maintenance

### Updating the Environment

#### Update Configuration Only
```bash
# Windows
.\setup-python-environment.ps1 -SkipInstall -Force

# Linux/macOS
bash setup-python-environment.sh --skip-install --force
```

#### Full Update
```bash
# Update Claude Code first
npm update -g claude-code

# Then update configuration
# Run the appropriate setup script for your platform
```

### Manual Component Updates

#### Update Subagents
```bash
# Download latest subagent
curl -o ~/.claude/agents/code-reviewer.md \
  https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/agents/examples/code-reviewer.md
```

#### Update System Prompt
```bash
# Download latest Python prompt
curl -o ~/.claude/prompts/python-developer.md \
  https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/system-prompts/examples/python-developer.md
```

## 🔍 Troubleshooting

### Common Issues

#### "Claude command not found"
```bash
# Refresh PATH
source ~/.bashrc  # or ~/.zshrc on macOS

# Verify installation
npm list -g claude-code
```

#### "MCP server connection failed"
```bash
# Test connectivity
curl https://mcp.context7.com/mcp

# Reconfigure
claude mcp add --transport http context7 https://mcp.context7.com/mcp
```

#### "Subagent not triggering"
```bash
# Check agent is loaded
ls ~/.claude/agents/

# Verify in Claude
/agents

# Use explicit invocation
Task: Use code-reviewer agent to review this file
```

#### "Permission denied" errors
```bash
# Windows: Run as Administrator
# Linux/macOS: Check file permissions
chmod +x ~/.claude/start-python-claude.sh
```

### Getting Help

1. **Check documentation**
   ```bash
   claude --help
   /help
   ```

2. **Review logs**
   ```bash
   # Windows
   type %TEMP%\claude-install.log

   # Linux/macOS
   cat /tmp/claude-install.log
   ```

3. **Community support**
   - [GitHub Issues](https://github.com/alex-feel/claude-code-toolbox/issues)
   - [Discussions](https://github.com/alex-feel/claude-code-toolbox/discussions)

## 🎓 Best Practices

### Project Organization

```text
my-project/
├── .claude/              # Project-specific Claude config
│   ├── agents/          # Custom project agents
│   └── settings.json    # Project settings
├── src/                 # Source code
├── tests/               # Test files
├── docs/                # Documentation
└── pyproject.toml       # Python project config
```

### Effective Prompting

```python
# Good: Specific and contextual
"Refactor the DatabaseConnection class to use async context managers and connection pooling"

# Better: With constraints
"Refactor the DatabaseConnection class to use async context managers and connection pooling. Maintain backward compatibility and add comprehensive tests."

# Best: With examples
"Refactor the DatabaseConnection class following the pattern in redis_client.py. Use async context managers, connection pooling, and maintain the existing public API."
```

### Leveraging Subagents

```python
# Chain multiple agents
"First review this code for issues, then refactor it, and finally generate tests"

# Specific agent targeting
"Task: Use performance-optimizer to analyze the data pipeline"

# Batch operations
"Review all files in src/api/ for security vulnerabilities"
```

## 🚀 Advanced Usage

### CI/CD Integration

```yaml
# GitHub Actions example
name: Claude Code Analysis
on: [push, pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Claude
        run: |
          curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-python-environment.sh | bash
      - name: Run Analysis
        run: |
          # MUST include the system prompt for Python-specific analysis!
          claude --append-system-prompt "@$HOME/.claude/prompts/python-developer.md" \
            -p "Review all changes for code quality and security" > analysis.md
      - uses: actions/upload-artifact@v3
        with:
          name: analysis
          path: analysis.md
```

### Custom Workflows

```bash
# Create custom command combining multiple operations
cat > ~/.claude/commands/deploy.md << 'EOF'
# Deploy Command
1. Run tests: pytest
2. Check code quality: Task review all modified files
3. Generate changelog: git log --oneline
4. Build: python -m build
5. Deploy: kubectl apply -f k8s/
EOF
```

### Integration with IDEs

**⚠️ IMPORTANT:** Configure your IDE to use the launcher script, not plain `claude`!

#### VS Code
```json
// .vscode/settings.json
{
  "terminal.integrated.defaultProfile.windows": "Claude Python",
  "terminal.integrated.profiles.windows": {
    "Claude Python": {
      "path": "powershell.exe",
      "args": ["-NoExit", "-File", "${env:USERPROFILE}\\.claude\\start-python-claude.ps1"]
    }
  },
  // For Linux/macOS:
  "terminal.integrated.profiles.linux": {
    "Claude Python": {
      "path": "bash",
      "args": ["-c", "~/.claude/start-python-claude.sh; exec bash"]
    }
  },
  "terminal.integrated.profiles.osx": {
    "Claude Python": {
      "path": "zsh",
      "args": ["-c", "~/.claude/start-python-claude.sh; exec zsh"]
    }
  }
}
```

**Usage:** Terminal → New Terminal → Select "Claude Python" profile

#### PyCharm
1. Settings → Tools → Terminal
2. Shell path:
   - **Windows:** `powershell.exe -NoExit -File %USERPROFILE%\.claude\start-python-claude.ps1`
   - **Linux/macOS:** `~/.claude/start-python-claude.sh`
3. Restart PyCharm

**Now the terminal always starts Claude with Python configuration!**

## 📚 Additional Resources

### Documentation
- [Claude Code Official Docs](https://docs.anthropic.com/claude-code)
- [System Prompts Guide](../system-prompts/README.md)
- [Subagents Guide](agents.md)
- [Slash Commands Guide](slash-commands.md)

### Examples
- [Python System Prompt](../system-prompts/examples/python-developer.md)
- [Agent Templates](../agents/templates/)
- [Command Templates](../slash-commands/templates/)

### Community
- [GitHub Repository](https://github.com/alex-feel/claude-code-toolbox)
- [Issue Tracker](https://github.com/alex-feel/claude-code-toolbox/issues)
- [Discussions](https://github.com/alex-feel/claude-code-toolbox/discussions)

## ❓ FAQ - Common Mistakes and Solutions

### Q: Why doesn't Claude use Python features after setup?

**A:** You're probably starting Claude without the system prompt!

```bash
# ❌ WRONG - No system prompt loaded:
claude "Create a FastAPI project"

# ✅ CORRECT - Use the global command:
claude-python
# Then type your request inside Claude

# ✅ ALSO CORRECT - Manual prompt:
claude --append-system-prompt "@$HOME/.claude/prompts/python-developer.md"
```

### Q: Do I need to use the launcher every time?

**A:** YES! The system prompt is not persistent. You must either:
1. Use the `claude-python` command (recommended)
2. Add `--append-system-prompt` flag manually every time
3. Configure your IDE to use `claude-python`

### Q: Can I make the Python prompt permanent?

**A:** No, Claude Code doesn't support permanent default prompts. You must load it each session.

### Q: Why do slash commands work but agents don't trigger?

**A:** Slash commands are loaded from `~/.claude/commands/`, but the system prompt (which enables agent behavior) must be loaded separately via the `claude-python` command.

### Q: How do I know if the Python prompt is loaded?

**A:** Start Claude and type:
```text
Are you configured as a Python developer?
```
If the prompt is loaded, Claude will confirm its Python-specific configuration.

### Q: Can I use multiple system prompts?

**A:** Yes, but only one at a time. The Python setup overwrites any previous prompt.

## 🤝 Contributing

Help improve the Python setup:

1. **Test on your platform**
2. **Report issues**
3. **Suggest improvements**
4. **Submit pull requests**

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - See [LICENSE](../LICENSE) for details.

---

*Transform your Python development with Claude Code - from idea to production-ready code in record time.*
