# MCP (Model Context Protocol) Configuration Guide

This directory contains documentation and configuration guides for MCP servers used with Claude Code.

## What is MCP?

MCP (Model Context Protocol) is an open-source standard for AI-tool integrations that allows Claude Code to connect with external tools, databases, and APIs. It enables Claude to interact with hundreds of tools and services, extending its capabilities beyond the base functionality.

## Official Documentation

- **Claude Code MCP Documentation**: <https://docs.anthropic.com/en/docs/claude-code/mcp>
- **MCP Servers Repository**: <https://github.com/modelcontextprotocol/servers>
- **MCP Protocol Specification**: <https://modelcontextprotocol.io>

## MCP Server Types

Claude Code supports three types of MCP server connections:

1. **Local stdio servers** - Run on your local machine
2. **Remote SSE (Server-Sent Events) servers** - Connect to remote services
3. **Remote HTTP servers** - Connect via HTTP protocol

## Platform-Specific Installation Instructions

### Windows

On Windows, adding MCP servers requires special handling for `npx` commands:

```bash
# For HTTP servers (like Context7)
claude mcp add --transport http context7 https://mcp.context7.com/mcp

# For stdio servers using npx (requires cmd /c wrapper)
claude mcp add --transport stdio my-server cmd /c "npx -y @modelcontextprotocol/server-example"
```

**Important Windows Notes:**
- Use `cmd /c` wrapper for `npx` commands
- PowerShell may require different escaping for quotes
- Environment variables should be set using Windows format

### macOS / Linux

On Unix-based systems, MCP servers can be added directly:

```bash
# For HTTP servers (like Context7)
claude mcp add --transport http context7 https://mcp.context7.com/mcp

# For stdio servers using npx
claude mcp add --transport stdio my-server npx -y @modelcontextprotocol/server-example

# For servers with environment variables
claude mcp add --transport stdio slack npx -y @modelcontextprotocol/server-slack --env SLACK_TOKEN=your-token
```

## Required MCP Servers for This Project

### Context7 - Documentation & Code Examples

Context7 provides up-to-date, version-specific documentation and working code examples for libraries. It's used extensively in our agents and slash commands.

**Installation:**

```bash
# All platforms - HTTP transport
claude mcp add --transport http context7 https://mcp.context7.com/mcp
```

**Features:**
- Real-time documentation retrieval
- Version-specific code examples
- Support for major libraries (FastAPI, LangChain, LangGraph, ChromaDB, etc.)
- Prevents hallucinated or outdated code

**Used by:**
- `implementation-guide` agent - For comprehensive library documentation
- Various slash commands that need technical documentation

**Verification:**
After installation, test with:
```bash
# List installed MCP servers
claude mcp list

# Test Context7 is working
# In Claude Code, try: "use context7 to show FastAPI documentation"
```

## Configuration Scopes

MCP servers can be configured at different scopes:

### 1. Local Scope
Personal, project-specific servers configured in `.claude/mcp_settings.json`:
```json
{
  "mcpServers": {
    "context7": {
      "transport": "http",
      "url": "https://mcp.context7.com/mcp"
    }
  }
}
```

### 2. Project Scope
Team-shared configurations for consistency across team members.

### 3. User Scope
Cross-project utility servers configured globally for your user.

## Adding Custom MCP Servers

### Step 1: Find or Create an MCP Server

Browse available servers at: <https://github.com/modelcontextprotocol/servers>

Popular MCP servers include:
- **Filesystem** - File operations
- **Git** - Version control operations
- **Slack** - Slack integration
- **PostgreSQL** - Database operations
- **Memory** - Persistent memory across sessions

### Step 2: Install the Server

```bash
# Generic HTTP server
claude mcp add --transport http <name> <url>

# Generic stdio server (Unix)
claude mcp add --transport stdio <name> <command> <args>

# Generic stdio server (Windows)
claude mcp add --transport stdio <name> cmd /c "<command> <args>"
```

### Step 3: Configure Authentication (if needed)

For servers requiring authentication:
```bash
# OAuth authentication
claude mcp add --transport http <name> <url>
# Then use: /mcp command in Claude Code to authenticate

# Environment variable authentication
claude mcp add --transport stdio <name> <command> --env API_KEY=your-key
```

## Security Considerations

⚠️ **Important Security Notes:**

1. **Third-party Risk**: Use third-party MCP servers at your own risk. Anthropic has not verified the correctness or security of all servers.

2. **Permission Control**: MCP servers have access to:
   - Execute commands on your system (stdio servers)
   - Access external services (HTTP/SSE servers)
   - Read/write files (depending on server capabilities)

3. **Best Practices**:
   - Only install MCP servers from trusted sources
   - Review server code before installation
   - Use minimal necessary permissions
   - Regularly audit installed servers with `claude mcp list`
   - Remove unused servers with `claude mcp remove <name>`

## Troubleshooting

### Common Issues

1. **Server not responding**
   ```bash
   # Check server status
   claude mcp list

   # Restart Claude Code
   # Remove and re-add the server
   claude mcp remove <name>
   claude mcp add ...
   ```

2. **Windows npx issues**
   - Ensure Node.js is installed (v18.0.0+)
   - Use `cmd /c` wrapper for npx commands
   - Check PATH environment variable includes Node.js

3. **Authentication failures**
   - Use `/mcp` command in Claude Code for OAuth
   - Verify environment variables are set correctly
   - Check API keys/tokens are valid

### Getting Help

- Claude Code MCP issues: <https://github.com/anthropics/claude-code/issues>
- MCP Protocol issues: <https://github.com/modelcontextprotocol/>
- Context7 issues: <https://github.com/upstash/context7/issues>

## MCP Tools in Code

When using MCP tools in agents or slash commands, the naming convention is:
```text
mcp__<serverName>__<toolName>
```

For example:
- `mcp__context7__resolve-library-id`
- `mcp__context7__get-library-docs`
- `mcp__slack__send-message`
- `mcp__git__commit`

## Quick Start Checklist

- [ ] Install Node.js v18.0.0 or higher
- [ ] Install Claude Code
- [ ] Add Context7 MCP server (required for this project)
- [ ] Test Context7 with "use context7" in a prompt
- [ ] Review security considerations
- [ ] Configure any additional MCP servers needed

## Contributing

When adding new agents or slash commands that use MCP servers:

1. Document the required MCP server in this README
2. Include installation instructions
3. Add example usage in your agent/command documentation
4. Update the "Required MCP Servers" section if needed

## License

MCP is an open-source protocol. Individual MCP servers may have their own licenses.
