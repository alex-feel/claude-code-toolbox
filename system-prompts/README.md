# System Prompts for Claude Code

This directory contains comprehensive system prompts that can be used with Claude Code's `--append-system-prompt` flag to customize Claude's behavior for specific roles and workflows.

## 📁 Directory Structure

```text
system-prompts/
├── library/           # Ready-to-use system prompts for specific roles
├── templates/         # Templates for creating custom system prompts
└── README.md          # This file
```

## 🚀 Quick Start

### Automated Setup (Recommended)

Use our setup scripts to automatically configure Claude Code with system prompts:

#### Python Developer Environment
```bash
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-python-environment.ps1')"

# macOS
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-python-environment.sh | bash

# Linux
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-python-environment.sh | bash
```

This installs:
- Claude Code (if needed)
- Python developer system prompt
- All related subagents and commands
- Convenience launcher scripts

### Manual Usage

#### Using System Prompts in Interactive Mode

As of Claude Code v1.0.51, the `--append-system-prompt` flag works in interactive mode:

```bash
# Start Claude Code with a specific role
# Git Bash/Linux/macOS:
claude --append-system-prompt "$(cat system-prompts/library/python-developer.md)"

# Or reference the file directly (may not work on all systems)
claude --append-system-prompt @system-prompts/library/python-developer.md

# Windows (PowerShell/CMD) - use the automated setup script which creates working wrappers
```

**Windows Users**: The `$(cat file)` syntax works in Git Bash. For PowerShell and CMD, use the automated setup which creates proper wrappers.

### Using System Prompts in Non-Interactive Mode

```bash
# Execute a task with a specific system prompt
# Git Bash/Linux/macOS:
claude -p "Review this codebase for security issues" \
  --append-system-prompt "$(cat system-prompts/library/python-developer.md)"

# Windows users: Use the claude-python command after running setup

# Combine with other flags
claude -p "Optimize database queries" \
  --append-system-prompt "$(cat system-prompts/library/python-developer.md)" \
  --model opus \
  --max-turns 10
```

**Note**: The `@file` syntax may not work reliably. Use `$(cat file)` for better compatibility.

## 📚 Available System Prompts

The `library/` directory contains comprehensive system prompts for various development roles:

- **Python Developer** - Full-stack Python with subagent orchestration
- **Frontend Developer** - React/TypeScript specialist
- **DevOps Engineer** - Infrastructure and CI/CD expert

Each system prompt includes:
- Role-specific expertise and best practices
- Subagent integration patterns
- Tool mastery requirements
- Quality gates and standards
- Concurrent execution patterns

## 🛠️ Creating Custom System Prompts

### Using Templates

1. **Start with the base template:**
   - `base-template.md` - Full-featured template with all sections

2. **Copy the template:**
   ```bash
   cp system-prompts/templates/base-template.md system-prompts/library/my-role.md
   ```

3. **Customize the sections:**
   - Replace `[bracketed]` placeholders
   - Add domain-specific requirements
   - Define subagent usage patterns
   - Specify quality standards

### Key Sections to Customize

#### Role Definition
Define the agent's expertise and primary responsibilities:
```markdown
You are **Claude Code, a [Role Title]** specializing in [domain].
```

#### Core Practices
Establish mandatory workflows and standards:
```markdown
### CRITICAL: [Practice Name]
[Detailed requirements and procedures]
```

#### Subagent Integration
Define when to use specialized agents:
```markdown
#### Subagent: `agent-name`
- **Purpose** – [What this agent does]
- **Invocation trigger** – [When to use]
```

#### Domain-Specific Requirements
Add sections specific to your domain:
```markdown
## [Domain Area]
### [Specific Practice]
[Requirements and procedures]
```

## 🎯 Best Practices

### 1. Enforce Concurrent Execution
Always include concurrent execution patterns to maximize performance:
```markdown
### CRITICAL: CONCURRENT EXECUTION FOR ALL ACTIONS
Dispatch every set of logically related operations in a single message...
```

### 2. Define Clear Subagent Triggers
Specify exactly when subagents should be invoked:
```markdown
Use PROACTIVELY whenever you:
- Write or modify code
- Prepare for pull requests
- Need code quality assessment
```

### 3. Include Quality Gates
Define mandatory quality checks:
```markdown
### CRITICAL: Static Analysis and Pre-Commit Quality Gate
- Run pre-commit hooks
- Zero warnings required
- All tests must pass
```

### 4. Specify Tool Usage
Define which tools to use and when:
```markdown
### CRITICAL: Package Management with `uv`
- Work only inside virtual environments
- Use `uv` for all operations
```

## 🤖 Automation and Integration

### Setup Scripts

Automated setup scripts are available for each system prompt:

#### Python Developer
- **Script**: `scripts/*/setup-python-environment.sh/ps1`
- **Installs**: System prompt + 7 subagents + 6 commands + MCP server

#### Future Additions
Setup scripts for other roles are planned:
- Frontend Developer setup
- DevOps Engineer setup
- Full-stack Developer setup

### CI/CD Integration

Use system prompts in automated workflows:

```yaml
# GitHub Actions example
- name: Code Review with Python Prompt
  run: |
    claude --append-system-prompt @system-prompts/library/python-developer.md \
      -p "Review the changes in this PR for Python best practices"
```

### Docker Integration

```dockerfile
# Include system prompt in container
FROM ubuntu:22.04
COPY system-prompts/library/python-developer.md /claude/prompts/
ENV CLAUDE_SYSTEM_PROMPT=/claude/prompts/python-developer.md
```

## 📖 Advanced Usage

### Combining Multiple Prompts

You can combine system prompts for hybrid roles:

```bash
# Create a combined prompt
cat system-prompts/library/python-developer.md > combined.md
echo "\n\n## Additional DevOps Responsibilities\n" >> combined.md
cat system-prompts/library/devops-engineer.md >> combined.md

# Use the combined prompt
claude --append-system-prompt @combined.md
```

### Environment-Specific Prompts

Create environment-specific variations:

```bash
# Development environment
claude --append-system-prompt @system-prompts/library/python-developer.md \
  --append-system-prompt "Focus on rapid prototyping and experimentation."

# Production environment
claude --append-system-prompt @system-prompts/library/python-developer.md \
  --append-system-prompt "Prioritize stability, security, and performance."
```

### Project-Specific Customization

Add project-specific requirements:

```bash
# Create project-specific prompt
echo "## Project-Specific Requirements" > project-prompt.md
echo "- Use FastAPI for all APIs" >> project-prompt.md
echo "- Follow company style guide" >> project-prompt.md
echo "- Target Python 3.11+" >> project-prompt.md

# Combine with role prompt
claude --append-system-prompt @system-prompts/library/python-developer.md \
  --append-system-prompt @project-prompt.md
```

## 🔍 Validation

### Testing Your System Prompt

1. **Start with a simple task:**
   ```bash
   claude -p "Create a hello world function" \
     --append-system-prompt @your-prompt.md
   ```

2. **Verify behavior changes:**
   - Check if specified practices are followed
   - Confirm subagents are invoked correctly
   - Validate output format and quality

3. **Test edge cases:**
   - Complex multi-step tasks
   - Error handling scenarios
   - Performance-critical operations

### Common Issues and Solutions

| Issue | Solution |
|-------|----------|
| Prompt too long | Split into focused sections, remove redundancy |
| Subagents not invoked | Add explicit "Use PROACTIVELY" triggers |
| Conflicting instructions | Prioritize with "CRITICAL" markers |
| Poor performance | Emphasize concurrent execution patterns |

## 🤝 Contributing

To contribute new system prompts:

1. Use the provided templates as a starting point
2. Follow the established structure and formatting
3. Include comprehensive documentation
4. Test thoroughly before submitting
5. Add examples of usage and expected outcomes

## 📝 Version Compatibility

- **Interactive mode support**: v1.0.51+
- **File reference syntax** (`@file`): All versions
- **Direct content**: All versions

## 🔗 Related Documentation

- [Claude Code CLI Reference](https://docs.anthropic.com/en/docs/claude-code/cli-reference)
- [SDK Usage](https://docs.anthropic.com/en/docs/claude-code/sdk)
- [Output Styles](https://docs.anthropic.com/en/docs/claude-code/output-styles)
- [Security Best Practices](https://docs.anthropic.com/en/docs/claude-code/security)
