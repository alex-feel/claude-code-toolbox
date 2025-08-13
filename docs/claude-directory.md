# .claude Directory Structure

The `.claude` directory is used to store project-specific configurations for Claude Code, including custom sub-agents, slash commands, and other settings.

## Overview

The `.claude` directory allows you to:
- Define project-specific sub-agents
- Create custom slash commands
- Store project configurations
- Share team workflows via version control

## Directory Structure

```text
your-project/
├── .claude/
│   ├── agents/           # Project-specific sub-agents
│   │   ├── api-expert.md
│   │   ├── db-migrator.md
│   │   └── deploy-assistant.md
│   ├── commands/         # Custom slash commands
│   │   ├── deploy.md
│   │   ├── migrate.md
│   │   └── release.md
│   └── CLAUDE.md         # Project context and instructions
├── src/
├── tests/
└── README.md
```

## Components

### 1. Sub-agents (.claude/agents/)

Store project-specific sub-agents as Markdown files with YAML frontmatter:

```markdown
---
name: api-expert
description: API design and implementation specialist for this project
tools: Read, Write, Bash
model: opus
color: blue
---

# API Development Expert

You are an expert in this project's API architecture...
```

### 2. Slash Commands (.claude/commands/)

Define custom commands for common project workflows:

```markdown
---
description: Deploy to staging environment
allowed-tools: Bash
---

# Deploy to Staging

Deploy the current branch to staging:

$ARGUMENTS

1. Run tests
2. Build the application
3. Deploy to staging server
4. Run smoke tests
```

### 3. Project Context (CLAUDE.md)

Optional file providing Claude with project-specific context:

```markdown
# Project Context

This is a microservices-based e-commerce platform...

## Architecture
- Frontend: React + TypeScript
- Backend: Node.js + Express
- Database: PostgreSQL

## Conventions
- Use conventional commits
- Follow ESLint rules
- Write tests for all features
```

## Setting Up .claude

### Initial Setup

```bash
# Create the directory structure
mkdir -p .claude/agents
mkdir -p .claude/commands

# Add to version control
git add .claude/
git commit -m "Add Claude Code configuration"
```

### Example: API Project

```bash
# Create project structure
mkdir -p .claude/agents .claude/commands

# Create an API specialist sub-agent
cat > .claude/agents/api-specialist.md << 'EOF'
---
name: api-specialist
description: REST API development for this project
tools: Read, Write, Bash
model: opus
color: blue
---

# API Development Specialist

You are an expert in this project's API architecture.

## Guidelines
- Follow OpenAPI 3.0 specification
- Use consistent error responses
- Implement proper validation
- Include comprehensive tests
EOF

# Create a migration command
cat > .claude/commands/migrate.md << 'EOF'
---
description: Run database migrations
allowed-tools: Bash
---

Run database migrations for: $ARGUMENTS

Execute: npm run migrate:$ARGUMENTS
EOF
```

## Priority and Resolution

Claude Code resolves configurations in this order:

1. **Project-level** (`.claude/`): Highest priority
2. **User-level** (`~/.claude/`): Lower priority
3. **Built-in**: Lowest priority

If the same sub-agent or command exists at multiple levels, the project-level version takes precedence.

## Best Practices

### 1. Version Control

Always commit `.claude/` to version control:

```gitignore
# Include Claude configurations
!.claude/
```

### 2. Team Consistency

Share sub-agents and commands with your team:
- Document each sub-agent's purpose
- Use clear, descriptive names
- Include usage examples

### 3. Project-Specific Rules

Embed project conventions in sub-agents:
- Coding standards
- Architecture patterns
- Testing requirements
- Deployment procedures

### 4. Security

Be careful with tool permissions:
- Limit Bash access for sensitive operations
- Use read-only tools when possible
- Never store secrets in configurations

## Examples

### Web Application

```text
.claude/
├── agents/
│   ├── frontend-dev.md      # React/TypeScript specialist
│   ├── backend-dev.md       # Node.js API developer
│   └── db-admin.md          # Database administrator
└── commands/
    ├── dev.md               # Start development server
    ├── test.md              # Run test suite
    └── build.md             # Build for production
```

### Python Package

```text
.claude/
├── agents/
│   ├── test-writer.md       # pytest specialist
│   ├── doc-generator.md    # Sphinx documentation
│   └── package-builder.md  # PyPI packaging
└── commands/
    ├── format.md            # Run black and isort
    ├── lint.md              # Run flake8 and mypy
    └── publish.md           # Publish to PyPI
```

### Mobile App

```text
.claude/
├── agents/
│   ├── ios-dev.md          # Swift/iOS specialist
│   ├── android-dev.md      # Kotlin/Android specialist
│   └── ui-designer.md      # UI/UX specialist
└── commands/
    ├── simulator.md         # Launch simulators
    ├── test-device.md       # Deploy to test device
    └── archive.md           # Create release build
```

## Integration with CI/CD

Include Claude Code configurations in CI/CD:

```yaml
# .github/workflows/claude.yml
name: Validate Claude Configurations

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate YAML frontmatter
        run: |
          for file in .claude/**/*.md; do
            # Extract and validate frontmatter
            head -n 20 "$file" | grep -E "^(name|description|tools|allowed-tools):"
          done
```

## Migration from Other Formats

If you have configurations in other formats:

### From JSON to Markdown

```bash
# Convert JSON configs to Markdown
for json in old-configs/*.json; do
  name=$(jq -r .name "$json")
  desc=$(jq -r .description "$json")
  content=$(jq -r .content "$json")

  cat > ".claude/commands/$name.md" << EOF
---
description: $desc
---

$content
EOF
done
```

## Troubleshooting

### Sub-agents Not Found

Check:
- Files are in `.claude/agents/`
- Files have `.md` extension
- YAML frontmatter is valid

### Commands Not Working

Verify:
- Files are in `.claude/commands/`
- Command name matches filename
- `$ARGUMENTS` is properly used

### Priority Issues

If wrong version loads:
1. Check project `.claude/` first
2. Check user `~/.claude/`
3. Remove conflicting files

## Advanced Usage

### Dynamic Sub-agents

Create sub-agents that adapt to project state:

```markdown
---
name: pr-reviewer
description: Reviews pull requests with project conventions
tools: Read, Bash
model: opus
color: blue
---

# PR Review Specialist

Review based on:
- Project's CONTRIBUTING.md
- Team's code review checklist
- Recent PR feedback patterns
```

### Workflow Commands

Chain multiple operations:

```markdown
---
description: Complete release workflow
---

1. Run tests: !npm test
2. Update version: $ARGUMENTS
3. Build: !npm run build
4. Create tag: !git tag v$ARGUMENTS
5. Generate changelog
```

---

For more information, see:
- [Sub-agents Guide](agents.md)
- [Slash Commands Guide](slash-commands.md)
- [Claude Code Documentation](https://docs.anthropic.com/claude-code)
