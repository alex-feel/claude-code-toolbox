# System Prompts for Claude Code

This directory contains comprehensive system prompts that can be used with Claude Code's `--append-system-prompt` flag to customize Claude's behavior for specific roles and workflows.

## 📁 Directory Structure

```text
system-prompts/
├── examples/          # Ready-to-use system prompts for specific roles
│   ├── python-developer.md    # Comprehensive Python developer with subagent orchestration
│   ├── frontend-developer.md  # React/TypeScript/Vite specialist
│   └── devops-engineer.md     # Infrastructure and CI/CD expert
├── templates/         # Templates for creating custom system prompts
│   ├── base-template.md       # Full-featured template with all sections
│   └── minimal-template.md    # Simplified template for basic use cases
└── README.md         # This file
```

## 🚀 Quick Start

### Using System Prompts in Interactive Mode

As of Claude Code v1.0.51, the `--append-system-prompt` flag works in interactive mode:

```bash
# Start Claude Code with a specific role
claude --append-system-prompt "$(cat system-prompts/examples/python-developer.md)"

# Or reference the file directly
claude --append-system-prompt @system-prompts/examples/python-developer.md
```

### Using System Prompts in Non-Interactive Mode

```bash
# Execute a task with a specific system prompt
claude -p "Review this codebase for security issues" \
  --append-system-prompt @system-prompts/examples/python-developer.md

# Combine with other flags
claude -p "Optimize database queries" \
  --append-system-prompt @system-prompts/examples/python-developer.md \
  --model opus \
  --max-turns 10
```

## 📚 Available System Prompts

### Python Developer (`python-developer.md`)

A comprehensive system prompt for Python development that includes:

- **Full-stack capabilities**: Python backend + React/TypeScript frontend
- **Subagent orchestration**: Automatically delegates to specialized agents
- **Best practices enforcement**: TDD, async-first, modular architecture
- **Tool mastery**: uv package management, pytest, pre-commit hooks
- **Concurrent execution**: Maximizes performance through parallel operations

**Integrated Subagents:**
- `code-reviewer` - Code quality and security reviews
- `doc-writer` - Technical documentation
- `implementation-guide` - Library usage and best practices
- `performance-optimizer` - Performance profiling and optimization
- `refactoring-assistant` - Code restructuring
- `security-auditor` - Security vulnerability assessment
- `test-generator` - Comprehensive test suite creation
- `technical-docs-expert` - Library documentation retrieval
- `commits-expert` - Git commit workflow management

### Frontend Developer (`frontend-developer.md`)

Specialized for modern frontend development:

- **React expertise**: Hooks, context, concurrent features
- **TypeScript mastery**: Type-safe development
- **Performance focus**: Core Web Vitals optimization
- **Testing coverage**: Testing Library, Playwright
- **Accessibility**: WCAG compliance

### DevOps Engineer (`devops-engineer.md`)

Infrastructure and deployment specialist:

- **Infrastructure as Code**: Terraform, CloudFormation
- **CI/CD pipelines**: GitHub Actions, Jenkins
- **Container orchestration**: Kubernetes, Docker
- **Monitoring**: Prometheus, Grafana, ELK
- **Security**: Automated scanning, compliance

## 🛠️ Creating Custom System Prompts

### Using Templates

1. **Choose a template:**
   - `base-template.md` - Full-featured with all sections
   - `minimal-template.md` - Simplified for basic needs

2. **Copy the template:**
   ```bash
   cp system-prompts/templates/base-template.md system-prompts/examples/my-role.md
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

## 📖 Advanced Usage

### Combining Multiple Prompts

You can combine system prompts for hybrid roles:

```bash
# Create a combined prompt
cat system-prompts/examples/python-developer.md > combined.md
echo "\n\n## Additional DevOps Responsibilities\n" >> combined.md
cat system-prompts/examples/devops-engineer.md >> combined.md

# Use the combined prompt
claude --append-system-prompt @combined.md
```

### Environment-Specific Prompts

Create environment-specific variations:

```bash
# Development environment
claude --append-system-prompt @system-prompts/examples/python-developer.md \
  --append-system-prompt "Focus on rapid prototyping and experimentation."

# Production environment
claude --append-system-prompt @system-prompts/examples/python-developer.md \
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
claude --append-system-prompt @system-prompts/examples/python-developer.md \
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

## 📄 License

These system prompts are provided as examples and can be freely modified for your use cases.
