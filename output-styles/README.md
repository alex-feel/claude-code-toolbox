# Claude Code Output Styles

Output styles allow you to adapt Claude Code's behavior and communication style for different purposes while maintaining core capabilities like file operations, script execution, and task tracking.

## Overview

Output styles completely modify Claude Code's system prompt to change how it:
- Communicates with users
- Structures responses
- Approaches problem-solving
- Presents information

Unlike agents (which handle specific delegated tasks), output styles change Claude Code's entire personality and approach.

**Note**: Claude Code has built-in output styles (default, explanatory, learning) available via the `/output-style` command. This repository provides additional custom output styles for specialized use cases beyond software engineering.

## Key Differences from Other Features

| Feature | Purpose | Scope |
|---------|---------|-------|
| **Output Styles** | Change entire communication style | Complete system prompt replacement |
| **Agents** | Delegate specific tasks | Task-specific with tool restrictions |
| **CLAUDE.md** | Add project context | Appends to existing prompt |
| **Slash Commands** | Quick actions | Specific command execution |

## Directory Structure

```text
output-styles/
├── README.md           # This file
├── library/            # Ready-to-use output styles
└── templates/          # Templates for creating new styles
```

## Using Output Styles

### Changing Output Style

Use the `/output-style` command in Claude Code to:
1. View available styles
2. Switch to a different style
3. Create new custom styles

### Storage Locations

Output styles can be stored at two levels:

1. **User-level**: `~/.claude/output-styles/` (available across all projects)
2. **Project-level**: `.claude/output-styles/` (specific to current project)

## Creating Custom Output Styles

Use the template in `templates/basic-template.md` as a starting point. Each output style requires:

1. **YAML frontmatter** with name and description
2. **System prompt** defining the new behavior
3. **Core capability preservation** (file operations, etc.)

### Example Structure

```markdown
---
name: my-custom-style
description: Brief description of what this style does
---

# System Prompt Title

You are Claude Code with [specific characteristics].

## Communication Style
[Define how to communicate]

## Problem-Solving Approach
[Define approach to tasks]

## Response Structure
[Define how to structure responses]
```

## Best Practices

1. **Preserve Core Functionality**: Always maintain file operations, script execution, and task tracking
2. **Clear Purpose**: Define a specific use case for each style
3. **Consistent Behavior**: Ensure predictable responses within the style
4. **User-Friendly**: Make the style intuitive and helpful
5. **Documentation**: Include examples of how the style changes behavior

## Available Output Styles

The `library/` directory contains ready-to-use output styles for various professional domains:

- **Business Analysis** - Requirements gathering and process documentation
- **Content Creation** - Marketing content and copywriting
- **Creative Writing** - Fiction and storytelling
- **Data Science** - Statistical analysis and machine learning
- **Research Analysis** - Evidence-based reporting
- **System Administration** - Infrastructure and operations

Each style completely transforms Claude's communication and problem-solving approach while maintaining core functionality.

## Contributing

To contribute a new output style:

1. Create a new file in `library/` following the template
2. Test the style thoroughly
3. Document specific use cases
4. Submit a pull request

## Testing Output Styles

Before using an output style in production:

1. Test with various task types
2. Verify core functionality remains intact
3. Ensure consistent behavior
4. Validate user experience

## See Also

- [Output Styles Documentation](https://docs.anthropic.com/en/docs/claude-code/output-styles)
