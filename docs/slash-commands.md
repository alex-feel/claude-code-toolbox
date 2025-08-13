# Claude Code Slash Commands Guide

Slash commands provide quick access to common tasks and custom workflows in Claude Code. They help control Claude's behavior during interactive sessions.

## Overview

Slash commands are special commands that:
- Start with `/` in Claude Code sessions
- Can accept arguments and parameters
- Provide shortcuts for common operations
- Can be customized per project or user

## Built-in Commands

Claude Code includes several built-in slash commands:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear the current conversation |
| `/model` | Change the AI model |
| `/agents` | Create or manage sub-agents |
| `/commands` | List available commands |

## Custom Slash Commands

### Structure

Custom slash commands are **simple Markdown files** without frontmatter. The filename (without `.md`) becomes the command name:

```markdown
# Command content

The actual prompt or instructions that will be executed when the command is invoked.

Use $ARGUMENTS to reference any arguments passed to the command.
```

### Storage Locations

Commands can be stored at two levels:

1. **Project-level**: `.claude/commands/` (highest priority)
   - Project-specific workflows
   - Team-shared commands
   - Version controlled

2. **User-level**: `~/.claude/commands/` (lower priority)
   - Personal shortcuts
   - Cross-project utilities
   - Private workflows

## Creating Custom Commands

### Quick Creation

Create a simple command:

```bash
# Create project command directory
mkdir -p .claude/commands

# Create a review command
echo "Review this code for quality issues: $ARGUMENTS" > .claude/commands/review.md
```

### Advanced Command

Create a more complex command:

```bash
cat > .claude/commands/optimize.md << 'EOF'
# Performance Optimization

Analyze and optimize the following code for performance:

$ARGUMENTS

Focus on:
1. Algorithm complexity
2. Memory usage
3. Database queries
4. Caching opportunities

Provide before/after comparisons and explain the improvements.
EOF
```

## Command Examples

### 1. Code Review Command

**File**: `slash-commands/examples/review.md`

```markdown
# Code Review Request

Please review the following code:

$ARGUMENTS

Check for:
- Security vulnerabilities
- Performance issues
- Code quality and maintainability
- Best practices
- Test coverage

Provide actionable feedback with specific line references.
```

### 2. Test Generation Command

**File**: `slash-commands/examples/test.md`

```markdown
# Test Generation

Generate comprehensive tests for:

$ARGUMENTS

Include:
- Unit tests for all public methods
- Edge cases and error conditions
- Integration tests where appropriate
- Test fixtures and mocks
- Clear test descriptions

Use the project's existing test framework and conventions.
```

### 3. Documentation Command

**File**: `slash-commands/examples/document.md`

```markdown
# Documentation Generation

Create documentation for:

$ARGUMENTS

Include:
- Purpose and overview
- Installation/setup (if applicable)
- Usage examples
- API reference
- Configuration options
- Troubleshooting section
```

### 4. Refactor Command

**File**: `slash-commands/examples/refactor.md`

```markdown
# Refactoring Request

Refactor the following code:

$ARGUMENTS

Focus on:
- Improving code structure
- Applying design patterns
- Reducing complexity
- Enhancing readability
- Following SOLID principles

Ensure all tests pass after refactoring.
```

### 5. Debug Command

**File**: `slash-commands/examples/debug.md`

```markdown
# Debug Analysis

Debug the following issue:

$ARGUMENTS

Steps:
1. Identify the root cause
2. Explain why the issue occurs
3. Provide a fix
4. Add tests to prevent regression
5. Document the solution
```

### 6. Commit Command

**File**: `slash-commands/examples/commit.md`

```markdown
# Git Commit

Create a git commit for the current changes.

$ARGUMENTS

Follow these guidelines:
- Use conventional commit format
- Write clear, concise commit messages
- Include relevant issue numbers
- Separate subject from body with blank line
- Explain what and why, not how
```

## Using Commands

### Basic Usage

```bash
# Use a command
/review src/main.py

# Pass multiple arguments
/test module1 module2

# Use with specific content
/document "API endpoints in routes.py"
```

### Command Discovery

Commands are automatically discovered from:
1. `.claude/commands/` in current project
2. `~/.claude/commands/` in user directory
3. MCP servers (if configured)

### Command Chaining

Commands can reference other commands:

```markdown
---
description: Complete workflow
---

First, run tests to ensure stability.
Then apply the requested changes: $ARGUMENTS
Finally, run tests again to verify.
```

## Advanced Features

### Bash Commands

Execute shell commands with `!` prefix:

```markdown
!npm test
!git status
```

### File References

Reference files with `@` prefix:

```markdown
Review @src/main.py and @src/utils.py
```

### Extended Thinking

Trigger deep analysis:

```markdown
[Extended thinking required]

Analyze the architecture and provide recommendations:
$ARGUMENTS
```

## Best Practices

### 1. Clear Naming
Use descriptive command names that indicate their purpose.

### 2. Documentation
Use clear, descriptive filenames for discoverability.

### 3. Arguments Handling
Always use `$ARGUMENTS` for dynamic content.

### 4. Validation
Test commands before committing to version control.

### 5. Organization
Group related commands with consistent naming:
- `test-unit.md`
- `test-integration.md`
- `test-e2e.md`

## Directory Structure

Recommended organization:

```text
claude-code-toolbox/
├── slash-commands/
│   ├── README.md           # Commands documentation
│   ├── examples/           # Example commands
│   │   ├── review.md
│   │   ├── test.md
│   │   ├── document.md
│   │   ├── refactor.md
│   │   ├── debug.md
│   │   └── commit.md
│   └── templates/          # Command templates
│       └── basic-template.md
```

## Project Integration

### Setting Up Project Commands

1. Create `.claude/commands/` in your project
2. Add relevant commands
3. Commit to version control
4. Team members get the same commands

### Example Project Structure

```text
your-project/
├── .claude/
│   ├── commands/           # Custom commands
│   │   ├── deploy.md       # Deployment workflow
│   │   ├── migrate.md      # Database migrations
│   │   └── release.md      # Release process
│   └── agents/             # Sub-agents
├── src/
└── tests/
```

## Command Templates

### Basic Template

```markdown
# Command content here

$ARGUMENTS
```

### Advanced Template

```markdown
# Command Title

Detailed instructions for the command.

## Input
$ARGUMENTS

## Process
1. Step one
2. Step two
3. Step three

## Output
Expected format and results.
```

## Troubleshooting

### Command Not Found
- Check file location (`.claude/commands/` or `~/.claude/commands/`)
- Verify file has `.md` extension
- Ensure filename matches command name

### Arguments Not Working
- Use `$ARGUMENTS` (all caps)
- Place anywhere in the command content
- Arguments are passed as-is

### Frontmatter Issues
- YAML must be valid
- Frontmatter must be at file start
- Use `---` delimiters

## Tips and Tricks

### 1. Workflow Commands
Create commands that combine multiple operations:

```markdown
1. Create feature branch
2. Implement changes: $ARGUMENTS
3. Write tests
4. Update documentation
5. Create pull request
```

### 2. Template Commands
Create reusable templates:

```markdown
Generate a new component named $ARGUMENTS with:
- Component file
- Test file
- Story file
- Documentation
```

### 3. Analysis Commands
Commands for code analysis:

```markdown
Analyze complexity of $ARGUMENTS and suggest simplifications.
```

---

For more examples, see the `slash-commands/` directory in this repository.
