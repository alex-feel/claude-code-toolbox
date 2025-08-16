# Claude Code Sub-agents

This directory contains example sub-agents and templates for Claude Code.

## What are Sub-agents?

Sub-agents are specialized AI assistants that operate in isolated contexts within Claude Code. They are Markdown files with YAML frontmatter that define custom prompts, tool permissions, thinking modes, and invocation patterns. Each agent is designed for specific tasks and can be invoked proactively or on-demand based on defined triggers.

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
   - `name`: Identifier for the sub-agent (kebab-case)
   - `description`: Multi-line description (3-4 sentences):
     - First 2-3 sentences describe capabilities
     - **CRITICAL**: Last sentence MUST contain either "Use PROACTIVELY" or "MUST BE USED" in CAPS with specific triggers
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

## Example Sub-agents

### Code Reviewer (model: opus, color: blue)
**Purpose**: Expert code review specialist focusing on security, performance, and best practices. Reviews code for bugs, vulnerabilities, and improvement opportunities with actionable feedback. Produces detailed reports with risk assessments and specific remediation steps.
**Invocation**: Use PROACTIVELY after writing or modifying code, for pull requests, or when code quality assessment is needed.
**Tools**: Read-only analysis tools (Glob, Grep, LS, Read, NotebookRead, Task, TodoWrite, BashOutput)

### Test Generator (model: opus, color: yellow)
**Purpose**: Test generation specialist creating comprehensive unit, integration, and end-to-end test suites. Develops tests following TDD/BDD principles with high coverage, proper mocking, and edge case handling. Ensures test maintainability through clear naming, isolated fixtures, and comprehensive assertions.
**Invocation**: Use PROACTIVELY after writing new code, before refactoring, or when test coverage is below 80%.
**Tools**: Full testing toolkit (includes Write, Edit, MultiEdit, Bash for test creation and execution)

### Documentation Writer (model: sonnet, color: green)
**Purpose**: Documentation specialist for technical writing and API documentation. Creates and maintains comprehensive documentation for codebases, APIs, and systems. Ensures documentation stays synchronized with code and follows industry best practices.
**Invocation**: MUST BE USED after implementing new features, making API changes, or when documentation gaps are detected.
**Tools**: Full documentation toolkit (includes Write, Edit, MultiEdit, WebFetch, WebSearch)

### Implementation Guide (model: opus, color: purple)
**Purpose**: Expert at finding and preparing comprehensive implementation guidance for any feature using existing libraries, frameworks, and modules. Retrieves up-to-date documentation, working code examples, and best practices from authoritative sources including Context7. Synthesizes multiple information sources to provide production-ready implementation strategies.
**Invocation**: Use PROACTIVELY when implementing new features, integrating libraries, or when you need authoritative guidance on how to correctly use any functionality.
**Tools**: Research and documentation tools (includes WebFetch, WebSearch, mcp__context7)

### Performance Optimizer (model: opus, color: red)
**Purpose**: Performance optimization expert specializing in profiling, bottleneck identification, and targeted optimization. Analyzes and optimizes application performance with measurable improvements and implementation strategies. Specializes in algorithm optimization, database tuning, caching strategies, and resource management.
**Invocation**: Use PROACTIVELY for performance issues, slow queries, high memory usage, or optimization requests.
**Tools**: Full optimization toolkit (includes Write, Edit, MultiEdit, Bash, WebFetch, WebSearch)

### Security Auditor (model: opus, color: orange)
**Purpose**: Security audit specialist for vulnerability assessment, threat modeling, and compliance verification. Identifies security vulnerabilities, configuration issues, and compliance gaps with actionable remediation guidance. Performs comprehensive security analysis including OWASP Top 10, dependency scanning, and penetration testing.
**Invocation**: MUST BE USED before deploying to production, after security incidents, or for regular security assessments.
**Tools**: Full security toolkit (includes Write, Edit, MultiEdit, Bash, WebFetch, WebSearch)

### Refactoring Assistant (model: opus, color: cyan)
**Purpose**: Refactoring specialist for code restructuring, clean architecture, and design pattern implementation. Transforms complex, legacy, or poorly structured code into maintainable, testable, and extensible systems. Ensures safe refactoring through incremental changes with comprehensive test coverage validation.
**Invocation**: Use PROACTIVELY when code smells are detected, before adding features to legacy code, or for maintainability improvements.
**Tools**: Full refactoring toolkit (includes Write, Edit, MultiEdit, Bash)

## Best Practices

1. **Single Responsibility**: Each sub-agent should focus on one domain
2. **Clear Invocation Triggers**: Last sentence of description MUST specify "Use PROACTIVELY" or "MUST BE USED" with specific conditions
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
2. Place it in `agents/examples/`
3. Update this README
4. Submit a pull request
