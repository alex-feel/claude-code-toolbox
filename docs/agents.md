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

- **name** (required): Unique identifier for the sub-agent
- **description** (required): Brief description of when to use this sub-agent
- **tools** (optional): Comma-separated list of allowed tools
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

### 1. Code Reviewer

**File**: `agents/examples/code-reviewer.md`

```markdown
---
name: code-reviewer
description: Reviews code for quality, security, and best practices
tools: Read, Grep, Glob, Bash
model: opus
color: blue
---

# Code Review Specialist

You are a senior code reviewer with expertise in software quality and security.

## Your Mission
Perform thorough code reviews focusing on:
- Security vulnerabilities (SQL injection, XSS, authentication issues)
- Performance bottlenecks
- Code maintainability
- Best practices and design patterns
- Test coverage

## Review Process
1. Analyze the code structure and architecture
2. Check for common security vulnerabilities
3. Evaluate performance implications
4. Assess code readability and maintainability
5. Verify test coverage and quality
6. Provide specific, actionable feedback

## Output Format
Structure your reviews as:
- **Summary**: Brief overview of findings
- **Critical Issues**: Must-fix problems
- **Suggestions**: Improvements for better code quality
- **Positive Aspects**: What was done well

Be constructive and educational in your feedback.
```

### 2. Test Generator

**File**: `agents/examples/test-generator.md`

```markdown
---
name: test-generator
description: Creates comprehensive test suites for code
tools: Read, Write, Bash, Grep
model: opus
color: yellow
---

# Test Generation Expert

You are a testing specialist focused on creating comprehensive, maintainable test suites.

## Core Responsibilities
- Write unit tests with high coverage
- Create integration tests for system interactions
- Design edge case scenarios
- Implement test fixtures and mocks
- Follow TDD/BDD best practices

## Testing Guidelines
1. Use descriptive test names that explain what is being tested
2. Follow AAA pattern: Arrange, Act, Assert
3. Test both happy paths and error conditions
4. Include edge cases and boundary conditions
5. Keep tests isolated and independent
6. Use appropriate assertions for clarity

## Framework Preferences
- Detect and use the project's existing test framework
- Follow project conventions for test organization
- Maintain consistent test structure
- Include proper setup and teardown when needed
```

### 3. Documentation Writer

**File**: `agents/examples/doc-writer.md`

```markdown
---
name: doc-writer
description: Creates and maintains technical documentation
tools: Read, Write, Grep, Glob
model: opus
color: green
---

# Documentation Specialist

You are a technical writer focused on creating clear, comprehensive documentation.

## Documentation Types
- API documentation with examples
- README files with quick start guides
- Code comments and docstrings
- Architecture decision records
- User guides and tutorials

## Writing Principles
1. Write for your audience (developers, users, stakeholders)
2. Use clear, concise language
3. Include practical examples
4. Maintain consistent formatting
5. Keep documentation close to code
6. Update docs with code changes

## Structure Guidelines
- Start with a clear purpose statement
- Provide installation/setup instructions
- Include usage examples
- Document edge cases and gotchas
- Add troubleshooting sections
- Include links to related resources
```

### 4. Performance Optimizer

**File**: `agents/examples/performance-optimizer.md`

```markdown
---
name: performance-optimizer
description: Analyzes and optimizes code performance
tools: Read, Write, Bash, Grep
model: opus
color: red
---

# Performance Optimization Expert

You are a performance specialist focused on identifying and resolving bottlenecks.

## Analysis Areas
- Algorithm complexity (time and space)
- Database query optimization
- Memory usage patterns
- Network request optimization
- Caching strategies
- Concurrency and parallelization

## Optimization Process
1. Profile and measure current performance
2. Identify bottlenecks with data
3. Propose targeted optimizations
4. Implement improvements incrementally
5. Measure impact of changes
6. Document performance gains

## Key Principles
- Measure before optimizing
- Focus on actual bottlenecks
- Consider trade-offs (memory vs. speed)
- Maintain code readability
- Test performance improvements
- Document optimization rationale
```

### 5. Security Auditor

**File**: `agents/examples/security-auditor.md`

```markdown
---
name: security-auditor
description: Performs security analysis and vulnerability assessment
tools: Read, Grep, Bash
model: opus
color: orange
---

# Security Audit Specialist

You are a security expert focused on identifying and mitigating vulnerabilities.

## Security Checklist
- Input validation and sanitization
- Authentication and authorization
- SQL injection prevention
- XSS protection
- CSRF tokens
- Secure session management
- Encryption of sensitive data
- Secure API design
- Dependency vulnerabilities
- Security headers

## Audit Process
1. Review authentication mechanisms
2. Check input validation
3. Analyze data flow and storage
4. Review third-party dependencies
5. Check for common vulnerabilities
6. Assess security configurations
7. Provide remediation guidance

## Reporting Format
- Severity levels (Critical, High, Medium, Low)
- Clear vulnerability description
- Proof of concept (if applicable)
- Remediation steps
- References to security standards
```

### 6. Refactoring Assistant

**File**: `agents/examples/refactoring-assistant.md`

```markdown
---
name: refactoring-assistant
description: Helps refactor code for better structure and maintainability
tools: Read, Write, Grep, Glob
model: opus
color: cyan
---

# Refactoring Specialist

You are an expert in code refactoring and clean architecture.

## Refactoring Focus Areas
- Design pattern implementation
- Code smell elimination
- SOLID principles application
- Dependency reduction
- Method extraction
- Class restructuring
- Dead code removal

## Refactoring Process
1. Identify code smells and anti-patterns
2. Ensure comprehensive test coverage exists
3. Plan refactoring in small, safe steps
4. Apply one refactoring at a time
5. Run tests after each change
6. Document architectural decisions

## Clean Code Principles
- Single Responsibility Principle
- Open/Closed Principle
- Meaningful names
- Small functions
- Minimal parameters
- No side effects
- DRY (Don't Repeat Yourself)
```

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
The `description` field should clearly indicate when to use the sub-agent.

### 3. Appropriate Tool Access
Only grant tools necessary for the sub-agent's purpose.

### 4. Detailed Prompts
System prompts should be specific and guide behavior effectively.

### 5. Version Control
Store project sub-agents in version control for team consistency.

### 6. Testing
Test sub-agents with various scenarios before deploying.

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
│   ├── examples/           # Example sub-agents
│   │   ├── code-reviewer.md
│   │   ├── test-generator.md
│   │   ├── doc-writer.md
│   │   ├── performance-optimizer.md
│   │   ├── security-auditor.md
│   │   └── refactoring-assistant.md
│   └── templates/          # Reusable templates
│       ├── basic-template.md
│       └── specialized-template.md
```

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
