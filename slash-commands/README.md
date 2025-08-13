# Claude Code Slash Commands

This directory contains example slash commands and templates for Claude Code.

## What are Slash Commands?

Slash commands are shortcuts that control Claude's behavior during interactive sessions. They are simple Markdown files that define custom prompts and workflows.

## Directory Structure

```text
slash-commands/
├── examples/        # Ready-to-use command examples
│   ├── review.md    # Code review command
│   ├── test.md      # Test generation command
│   ├── document.md  # Documentation command
│   ├── refactor.md  # Refactoring command
│   ├── debug.md     # Debugging command
│   └── commit.md    # Git commit command
└── templates/       # Templates for new commands
    └── basic-template.md
```

## Using These Commands

### Option 1: Project-level (Recommended for teams)

Copy commands to your project:

```bash
# Create .claude/commands directory
mkdir -p .claude/commands

# Copy desired commands
cp slash-commands/examples/review.md .claude/commands/
cp slash-commands/examples/test.md .claude/commands/
```

### Option 2: User-level (Personal use)

Install commands for all projects:

```bash
# Windows
mkdir -p %USERPROFILE%\.claude\commands
copy slash-commands\examples\*.md %USERPROFILE%\.claude\commands\

# Unix/Mac
mkdir -p ~/.claude/commands
cp slash-commands/examples/*.md ~/.claude/commands/
```

## Command Format

Commands are simple Markdown files:

1. **Filename**: The command name (without `.md` extension)
2. **Content**: Markdown with instructions
3. **Arguments**: Use `$ARGUMENTS` for dynamic content

## Example Commands

### /review
Reviews code for quality, security, and best practices.

### /test
Generates comprehensive test suites.

### /document
Creates technical documentation.

### /refactor
Refactors code for better structure.

### /debug
Debugs and fixes issues.

### /commit
Creates proper git commits.

## Creating Custom Commands

1. Start with the template:
   ```bash
   cp slash-commands/templates/basic-template.md my-command.md
   ```

2. Write the command content using `$ARGUMENTS`

4. Save to `.claude/commands/` or `~/.claude/commands/`

## Best Practices

1. **Clear Names**: Use descriptive command names
2. **Arguments**: Always use `$ARGUMENTS` for input
3. **Testing**: Test commands before sharing
4. **Documentation**: Write clear instructions in the command

## Advanced Features

### Bash Commands

Execute shell commands with `!`:
```markdown
!npm test
```

### File References

Reference files with `@`:
```markdown
Review @src/main.py
```

### Extended Thinking

For complex analysis:
```markdown
[Extended thinking required]
Analyze the architecture...
```

## Documentation

For detailed documentation, see [docs/slash-commands.md](../docs/slash-commands.md)

## Contributing

To contribute new commands:

1. Create a well-tested command
2. Place it in `slash-commands/examples/`
3. Update this README
4. Submit a pull request

## License

These commands are provided under the MIT License.
