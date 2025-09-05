# Claude Code Sub-agents

This directory contains example sub-agents and templates for Claude Code.

## What are Sub-agents?

Sub-agents are specialized AI assistants that operate in isolated contexts within Claude Code. They are Markdown files with YAML frontmatter that define custom prompts, tool permissions, thinking modes, and invocation patterns. Each agent is designed for specific tasks and can be invoked proactively or on-demand based on defined triggers.

## Directory Structure

```text
agents/
├── library/         # Ready-to-use sub-agents
└── templates/       # Templates for creating new sub-agents
```

## Using These Sub-agents

### Option 1: Project-level (Recommended for teams)

Copy sub-agents to your project:

```bash
# Create .claude/agents directory in your project
mkdir -p .claude/agents

# Copy desired sub-agents
cp agents/library/code-reviewer.md .claude/agents/
cp agents/library/test-generator.md .claude/agents/
```

### Option 2: User-level (Personal use)

Install sub-agents for all projects:

```bash
# Windows
mkdir -p %USERPROFILE%\.claude\agents
copy agents\library\*.md %USERPROFILE%\.claude\agents\

# Unix/Mac
mkdir -p ~/.claude/agents
cp agents/library/*.md ~/.claude/agents/
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
   - `name`: Identifier for the sub-agent (kebab-case)
   - `description`: Multi-line description (3-4 sentences):
     - First 2-3 sentences describe capabilities
     - **CRITICAL**: Last sentence MUST contain either "It should be used proactively" with specific triggers
   - `tools`: Comma-separated tool list (start with no-permission tools, add others as needed)
     - MCP server shortcuts supported (e.g., `mcp__context7` for all Context7 tools)
     - **IMPORTANT**: If using Write, must also include Edit and MultiEdit
   - `model`: Optional model preference (opus, sonnet, haiku) - most agents use opus
   - `color`: Optional agent color (red, blue, green, yellow, purple, orange, pink, cyan)

2. **System Prompt**: Markdown content with:
   - Mission statement
   - Cognitive framework with thinking mode (Think, Think more, Think a lot, Think longer, Ultrathink)
   - Operating rules and constraints
   - Execution workflow
   - Concurrent execution patterns (CRITICAL)
   - Error handling protocol
   - Quality metrics

3. **File Extension**: Must be `.md`

## Available Sub-agents

The `library/` directory contains production-ready sub-agents for various development tasks including:

- **Code Review** - Security, performance, and best practices analysis
- **Test Generation** - Comprehensive test suite creation
- **Documentation** - Technical writing and API documentation
- **Implementation Guidance** - Library usage and best practices
- **Performance Optimization** - Profiling and optimization
- **Security Auditing** - Vulnerability assessment and compliance
- **Refactoring** - Code restructuring and clean architecture
- **Research** - Deep code analysis and web research

Each sub-agent is carefully crafted with:
- Specific purpose and invocation triggers
- Appropriate tool permissions
- Optimized cognitive modes
- Concurrent execution patterns

## Best Practices

1. **Single Responsibility**: Each sub-agent should focus on one domain
2. **Clear Invocation Triggers**: Last sentence of description MUST specify "It should be used proactively" with specific conditions
3. **Appropriate Tools**: Start with no-permission tools, add others only as needed
4. **Thinking Modes**: Choose appropriate cognitive depth (Think, Think more, Think a lot, Think longer, Ultrathink)
5. **Concurrent Execution**: ALWAYS batch related operations in single messages for performance
6. **Detailed Prompts**: Include mission statement, workflows, and quality metrics
7. **Version Control**: Commit project sub-agents to your repository

## Tool Permissions

Common tool configurations used by actual agents:

- **Analysis-only** (code-reviewer): `Glob, Grep, LS, Read, NotebookRead, Task, TodoWrite, BashOutput`
- **Content creation** (doc-writer): `Glob, Grep, LS, Read, NotebookRead, Task, TodoWrite, BashOutput, Write, Edit, MultiEdit, WebFetch, WebSearch`
- **Full development** (test-generator, refactoring): `Glob, Grep, LS, Read, NotebookRead, Task, TodoWrite, BashOutput, Write, Edit, MultiEdit, Bash`
- **Research-focused** (implementation-guide): Includes `mcp__context7` for library documentation access

**CRITICAL**: Always start with no-permission tools (Glob, Grep, LS, Read, NotebookRead, Task, TodoWrite, BashOutput), then add others as needed.

### MCP Server Tools

When using MCP (Model Context Protocol) tools, you can specify either individual tools or entire servers:

- **Individual MCP tools**: `mcp__serverName__toolName` (e.g., `mcp__context7__get-library-docs`)
- **All tools from MCP server**: `mcp__serverName` (e.g., `mcp__context7`)

Example allowing all Context7 tools:
```yaml
tools: Glob, Grep, LS, Read, NotebookRead, mcp__context7
```

This is equivalent to listing all Context7 tools individually but is more concise and maintainable.

## Documentation

For detailed documentation on creating and using sub-agents, see:
- [Official Claude Code Sub-agents Documentation](https://docs.anthropic.com/en/docs/claude-code/sub-agents)

## Contributing

To contribute new sub-agents:

1. Create a well-tested sub-agent
2. Place it in `agents/library/`
3. Update this README
4. Submit a pull request
