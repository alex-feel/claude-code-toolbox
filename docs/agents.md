# Claude Code Sub-agents Guide

Sub-agents are specialized AI assistants within Claude Code that can be delegated specific tasks. They operate in isolated contexts and can be configured with custom prompts and tool permissions.

## Overview

Sub-agents allow you to:
- Create specialized assistants for specific domains
- Preserve context by operating in separate windows
- Configure different tool access levels
- Reuse expertise across projects

## Sub-agent Structure

Sub-agents are **Markdown files with YAML frontmatter** stored in specific directories:

```markdown
---
name: your-sub-agent-name
description: When this sub-agent should be invoked
tools: Read, Write, Bash  # Optional: specific tools (comma-separated)
model: opus  # Optional: specific model to use (opus, sonnet, haiku)
color: blue  # Optional: color for the agent (blue, green, red, purple, orange, cyan, yellow)
---

# System prompt defining the sub-agent's role

You are a specialized assistant focused on [specific domain].

Your responsibilities include:
- Specific task 1
- Specific task 2
- Specific task 3

Follow these guidelines:
- Guideline 1
- Guideline 2
```

### Frontmatter Fields

- **name** (required): Unique identifier for the sub-agent (lowercase, hyphens for spaces)
- **description** (required): Multi-line description with specific requirements:
  - Must be 3-4 sentences describing the agent's specialization and capabilities
  - The LAST sentence MUST contain either:
    - "Use PROACTIVELY [when/after/for specific situations]"
    - "MUST BE USED [when/after/for specific situations]"
  - These keywords (PROACTIVELY/MUST BE USED) must be in CAPS
- **tools** (required): Comma-separated list of allowed tools
  - Should include ALL no-permission tools as baseline: `Glob, Grep, LS, Read, NotebookRead, Task, TodoWrite, BashOutput`
  - Add permission-required tools as needed: `Write, Edit, MultiEdit, Bash, WebFetch, WebSearch, etc.`
  - **CRITICAL**: If including `Write`, you MUST also include `Edit` and `MultiEdit` for corrections
- **model** (optional): Specific Claude model to use (e.g., `opus`, `sonnet`, `haiku`)
- **color** (optional): Visual color for the sub-agent in the UI. Available colors:
  - `blue`, `green`, `red`, `purple`, `orange`, `cyan`, `yellow`

## Storage Locations

Sub-agents can be stored at two levels:

1. **Project-level**: `.claude/agents/` (highest priority)
   - Specific to the current project
   - Version controlled with your code
   - Shared with team members

2. **User-level**: `~/.claude/agents/` (lower priority)
   - Available across all projects
   - Personal workflow optimizations
   - Not shared with others

## Creating Sub-agents

### Quick Creation with Claude

The easiest way to create a sub-agent:

```bash
/agents
```

Claude will help you:
1. Choose project or user level
2. Define the sub-agent's purpose
3. Configure tool access
4. Generate the system prompt

### Manual Creation

1. Create the directory structure:
```bash
# For project-level
mkdir -p .claude/agents

# For user-level (Windows)
mkdir -p %USERPROFILE%\.claude\agents

# For user-level (Unix)
mkdir -p ~/.claude/agents
```

2. Create a Markdown file with the sub-agent name:
```bash
# Example: code-reviewer.md
```

3. Add YAML frontmatter and system prompt (see examples below)

## Pre-built Sub-agent Examples

The `agents/examples/` directory contains production-ready sub-agents following best practices:

### 1. Code Reviewer

**File**: `agents/examples/code-reviewer.md`

- **Purpose**: Reviews code for quality, security, and best practices
- **Tools**: Full no-permission suite plus Bash for running linters
- **When to use**: Code review requests, PR reviews, quality assessments
- **Key features**: Security vulnerability detection, performance analysis, maintainability scoring

### 2. Test Generator

**File**: `agents/examples/test-generator.md`

- **Purpose**: Creates comprehensive unit, integration, and end-to-end test suites
- **Tools**: Full suite including Write, Edit, MultiEdit for test creation, Bash for execution
- **When to use**: After writing new code, before refactoring, when coverage is below 80%
- **Key features**: TDD/BDD principles, >90% coverage targets, proper mocking, edge case handling

### 3. Documentation Writer

**File**: `agents/examples/doc-writer.md`

- **Purpose**: Creates and maintains technical documentation
- **Tools**: Full suite with Write, Edit, MultiEdit for documentation creation
- **When to use**: API documentation, README creation, architecture docs, user guides
- **Key features**: Multiple documentation types, audience-specific writing, example generation

### 4. Performance Optimizer

**File**: `agents/examples/performance-optimizer.md`

- **Purpose**: Analyzes and optimizes code performance
- **Tools**: Full suite with Write, Edit, MultiEdit for optimization, Bash for profiling
- **When to use**: Performance issues, optimization requests, scalability improvements
- **Key features**: Profiling, bottleneck identification, caching strategies, concurrency optimization

### 5. Security Auditor

**File**: `agents/examples/security-auditor.md`

- **Purpose**: Vulnerability assessment, threat modeling, and compliance verification
- **Tools**: Full suite with Write, Edit, MultiEdit for remediation, WebFetch/WebSearch for CVE lookups
- **When to use**: Before production deployment, after security incidents, regular assessments
- **Key features**: OWASP Top 10 coverage, CVE scanning, compliance checking, remediation guidance

### 6. Refactoring Assistant

**File**: `agents/examples/refactoring-assistant.md`

- **Purpose**: Code restructuring, clean architecture, and design pattern implementation
- **Tools**: Full suite with Write, Edit, MultiEdit for safe incremental refactoring
- **When to use**: Code smells detected, before adding features to legacy code, maintainability improvements
- **Key features**: Safe refactoring with test validation, SOLID principles, design patterns

## Using Sub-agents

### Delegation Patterns

When working with Claude Code, delegate to sub-agents for specialized tasks:

```bash
# Example: Asking Claude to use a sub-agent
"Review this code using the security-auditor sub-agent"
"Generate tests for this module using test-generator"
"Optimize the performance of this function"
```

### Sub-agent Collaboration

Sub-agents can work together on complex tasks:

1. Security audit → Code review → Documentation update
2. Performance analysis → Refactoring → Test generation
3. Bug fix → Test creation → Documentation update

## Best Practices

### 1. Single Responsibility
Each sub-agent should focus on one domain or task type.

### 2. Clear Descriptions
The `description` field must:
- Be 3-4 sentences describing specialization and capabilities
- End with "Use PROACTIVELY" or "MUST BE USED" (in CAPS) with specific triggers
- Clearly indicate when Claude should invoke the agent

### 3. Tool Selection Strategy
- **Always include** all no-permission tools as baseline: `Glob, Grep, LS, Read, NotebookRead, Task, TodoWrite, BashOutput`
- **Add permission-required tools** based on agent's needs
- **Critical bundling rule**: If using `Write`, MUST also include `Edit` and `MultiEdit`

### 4. Detailed Prompts
System prompts should:
- Define a clear mission statement
- Include cognitive framework with thinking modes
- Specify operating rules and constraints
- Provide structured output schemas
- Include concurrent execution patterns

### 5. Version Control
Store project sub-agents in version control for team consistency.

### 6. Testing
Test sub-agents with various scenarios before deploying.

### 7. Performance Guidelines
- Use concurrent execution patterns ("1 MESSAGE = ALL RELATED OPERATIONS")
- Batch all related tool calls in single messages
- Maximize parallelism for reduced latency

## Customization Tips

### Tool Restrictions

Limit tool access for safety:
```yaml
tools: Read, Grep  # Read-only access
```

Full access for trusted operations:
```yaml
tools: Read, Write, Bash, Edit  # Full toolkit
```

### Domain-Specific Sub-agents

Create sub-agents for your specific needs:
- Database migration specialist
- API design expert
- DevOps automation assistant
- Data analysis expert
- UI/UX reviewer

### Project Conventions

Embed project-specific rules in sub-agents:
- Coding standards
- Architecture patterns
- Testing requirements
- Documentation formats

## Directory Structure

Recommended organization:

```text
claude-code-toolbox/
├── agents/
│   ├── README.md           # Sub-agent documentation
│   ├── examples/           # Production-ready example sub-agents
│   │   ├── code-reviewer.md
│   │   ├── test-generator.md
│   │   ├── doc-writer.md
│   │   ├── performance-optimizer.md
│   │   ├── security-auditor.md
│   │   └── refactoring-assistant.md
│   └── templates/          # Templates for creating new sub-agents
│       └── basic-template.md  # Comprehensive template with all features
```

## Templates

The `agents/templates/` directory contains templates for creating new sub-agents:

### Basic Template

**File**: `agents/templates/basic-template.md`

The basic template provides a comprehensive structure including:
- Complete YAML frontmatter with all fields and requirements
- Cognitive framework with thinking mode selection
- Operating rules and constraints
- Execution workflow pipeline
- Structured output schemas (YAML format)
- Performance and concurrency guidelines
- Error handling protocols
- Quality metrics and confidence calibration
- Domain-specific patterns and best practices

Use this template as a starting point when creating new sub-agents to ensure consistency and completeness.

## Integration with Projects

### Setting Up Project Sub-agents

1. Create `.claude/agents/` in your project root
2. Add relevant sub-agents for your project
3. Commit to version control
4. Team members automatically get the same sub-agents

### Example Project Structure

```text
your-project/
├── .claude/
│   ├── agents/
│   │   ├── api-reviewer.md      # Project-specific
│   │   ├── db-migrator.md       # Project-specific
│   │   └── deploy-assistant.md  # Project-specific
│   └── commands/                 # Custom slash commands
├── src/
├── tests/
└── README.md
```

## Troubleshooting

### Sub-agent Not Found
- Check file location (`.claude/agents/` or `~/.claude/agents/`)
- Verify file has `.md` extension
- Ensure YAML frontmatter is valid

### Tool Access Issues
- Verify tools are correctly listed in frontmatter
- Use comma-separated list for multiple tools
- Check tool names match Claude Code's tool names

### Prompt Not Working
- Ensure system prompt is after frontmatter
- Keep prompts focused and specific
- Test with simpler prompts first

---

For more examples and templates, explore the `agents/` directory in this repository.
