# Claude Code Sub-agents

This directory contains example sub-agents and templates for Claude Code.

## What are Sub-agents?

Sub-agents are specialized AI assistants that operate in isolated contexts within Claude Code. They are Markdown files with YAML frontmatter that define custom prompts and tool permissions.

## Directory Structure

```text
agents/
├── examples/        # Ready-to-use sub-agent examples
│   ├── code-reviewer.md
│   ├── test-generator.md
│   ├── doc-writer.md
│   ├── implementation-guide.md
│   ├── performance-optimizer.md
│   ├── security-auditor.md
│   └── refactoring-assistant.md
└── templates/       # Templates for creating new sub-agents
    └── basic-template.md
```

## Using These Sub-agents

### Option 1: Project-level (Recommended for teams)

Copy sub-agents to your project:

```bash
# Create .claude/agents directory in your project
mkdir -p .claude/agents

# Copy desired sub-agents
cp agents/examples/code-reviewer.md .claude/agents/
cp agents/examples/test-generator.md .claude/agents/
```

### Option 2: User-level (Personal use)

Install sub-agents for all projects:

```bash
# Windows
mkdir -p %USERPROFILE%\.claude\agents
copy agents\examples\*.md %USERPROFILE%\.claude\agents\

# Unix/Mac
mkdir -p ~/.claude/agents
cp agents/examples/*.md ~/.claude/agents/
```

## Creating Custom Sub-agents

1. Start with the template:
   ```bash
   cp agents/templates/basic-template.md my-agent.md
   ```

2. Edit the frontmatter:
   ```yaml
   ---
   name: my-agent
   description: What this agent does
   tools: Read, Write  # Optional
   model: opus  # Optional
   color: blue  # Optional
   ---
   ```

3. Write the system prompt below the frontmatter

4. Test your sub-agent in Claude Code

## Sub-agent Format

Sub-agents are Markdown files with three parts:

1. **YAML Frontmatter**: Metadata
   - `name`: Identifier for the sub-agent
   - `description`: When to use this sub-agent
   - `tools`: Optional comma-separated tool list
   - `model`: Optional model to use
   - `color`: Optional agent color

2. **System Prompt**: Markdown content defining the agent's behavior

3. **File Extension**: Must be `.md`

## Example Sub-agents

### Code Reviewer
Reviews code for quality, security, and best practices.

### Test Generator
Creates comprehensive test suites with high coverage.

### Documentation Writer
Generates and maintains technical documentation.

### Implementation Guide
Finds and prepares comprehensive implementation guidance using Context7 and authoritative sources.

### Performance Optimizer
Analyzes and optimizes code performance.

### Security Auditor
Performs security analysis and vulnerability assessment.

### Refactoring Assistant
Helps refactor code for better maintainability.

## Best Practices

1. **Single Responsibility**: Each sub-agent should focus on one domain
2. **Clear Descriptions**: Make it obvious when to use each sub-agent
3. **Appropriate Tools**: Only grant necessary tool access
4. **Detailed Prompts**: Provide specific guidance in system prompts
5. **Version Control**: Commit project sub-agents to your repository

## Tool Permissions

Common tool configurations:

- **Read-only**: `tools: Read, Grep, Glob`
- **Read-write**: `tools: Read, Write, Edit`
- **Full access**: `tools: Read, Write, Bash, Edit, Grep, Glob`

## Documentation

For detailed documentation, see [docs/agents.md](../docs/agents.md)

## Contributing

To contribute new sub-agents:

1. Create a well-tested sub-agent
2. Place it in `agents/examples/`
3. Update this README
4. Submit a pull request

## License

These sub-agents are provided under the MIT License.
