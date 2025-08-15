# Claude Code Output Styles Guide

Output styles allow you to completely transform Claude Code's personality and behavior for different professional domains while maintaining core capabilities like file operations, script execution, and task tracking.

## Overview

Output styles **completely replace** Claude Code's default system prompt, transforming it from a software engineering assistant into entirely different professional tools. This is more comprehensive than agents (which handle specific tasks) or CLAUDE.md (which adds context).

## Key Concepts

### What Output Styles Change

- **Communication style**: From concise code-focused to domain-specific language
- **Problem-solving approach**: From software development to other professional methodologies
- **Response structure**: From code generation to reports, analyses, or creative content
- **Task priorities**: From testing and efficiency to domain-specific goals

### What Remains Constant

- File read/write operations
- Command execution capabilities
- Task tracking with TODOs
- Tool access (Read, Write, Bash, etc.)

## Using Output Styles

### Changing Styles

Use the `/output-style` command in Claude Code to:
1. List available styles
2. Switch to a different style
3. Create custom styles

### Storage Locations

Output styles can be stored at two levels:

| Level | Location | Purpose | Priority |
|-------|----------|---------|----------|
| **User** | `~/.claude/output-styles/` | Personal styles across all projects | Lower |
| **Project** | `.claude/output-styles/` | Project-specific styles | Higher |

## Available Output Styles

### Built-in Styles

Claude Code includes these pre-configured styles:

1. **Default**: Standard software engineering assistance
2. **Explanatory**: Educational mode with detailed insights
3. **Learning**: Collaborative mode with TODO(human) markers

### Example Custom Styles

The `output-styles/examples/` directory contains ready-to-use professional transformations:

#### Creative Writer
**Purpose**: Transform into a literary assistant for novels, scripts, and creative content
**Use Cases**:
- Manuscript management
- Character development
- World-building
- Story structure planning

#### Research Analyst
**Purpose**: Systematic research, evidence gathering, and report generation
**Use Cases**:
- Academic research
- Market analysis
- Competitive intelligence
- Literature reviews

#### Data Scientist
**Purpose**: Statistical analysis, machine learning, and data visualization
**Use Cases**:
- Exploratory data analysis
- Model development
- Statistical testing
- Results visualization

#### Content Creator
**Purpose**: Marketing content, social media, and content strategy
**Use Cases**:
- Blog post creation
- Social media campaigns
- Email marketing
- SEO optimization

#### Business Analyst
**Purpose**: Requirements gathering, process documentation, and business cases
**Use Cases**:
- Requirements documentation
- Process improvement
- Stakeholder management
- Business case development

#### System Administrator
**Purpose**: Infrastructure management, automation, and operations
**Use Cases**:
- Server management
- Backup automation
- Monitoring setup
- Security hardening

## Creating Custom Output Styles

### Structure

Each output style is a Markdown file with YAML frontmatter:

```markdown
---
name: style-name
description: Brief description for user selection
---

# System Prompt Title

[Complete system prompt that replaces Claude Code's default]
```

### Using the Template

The `output-styles/templates/basic-template.md` provides a comprehensive structure:

1. **Core Identity**: Define the fundamental character
2. **Communication Style**: Specify tone, voice, and structure
3. **Problem-Solving Approach**: Define methodology
4. **Special Behaviors**: Unique features of this style
5. **Task Management**: How to use TODOs
6. **Examples**: Sample interactions
7. **Constraints**: Boundaries and limitations

### Best Practices

#### DO
- Preserve file operation capabilities
- Maintain clear, consistent behavior
- Define specific use cases
- Include example interactions
- Document unique features

#### DON'T
- Remove core functionality
- Create conflicting behaviors
- Use for malicious purposes
- Ignore user safety
- Forget documentation

## Key Differences from Other Features

| Feature | Scope | Purpose | Modification Type |
|---------|-------|---------|------------------|
| **Output Styles** | Entire assistant | Complete transformation | Full replacement |
| **Agents** | Specific tasks | Delegated work | Additional capability |
| **CLAUDE.md** | Project context | Add information | Append to prompt |
| **Slash Commands** | Single actions | Quick operations | Temporary execution |

## Creating Your First Output Style

### Step 1: Identify the Domain

Choose a professional domain that would benefit from Claude Code's file operations:
- Technical writing
- Project management
- Quality assurance
- UX research
- DevOps automation

### Step 2: Define Core Behaviors

Determine how this style should:
- Communicate with users
- Approach problems
- Structure responses
- Use available tools

### Step 3: Create the File

1. Copy the template:
```bash
cp output-styles/templates/basic-template.md ~/.claude/output-styles/my-style.md
```

2. Edit the frontmatter:
```yaml
---
name: my-style
description: What this style does
---
```

3. Write the system prompt focusing on the new domain

### Step 4: Test and Refine

1. Switch to your new style using `/output-style`
2. Test various scenarios
3. Verify core functionality works
4. Refine based on experience

## Advanced Patterns

### Domain-Specific File Organization

Each style can define its own file structure patterns:

```markdown
# Research projects use:
research/
├── literature/
├── data/
└── analysis/

# Creative projects use:
manuscript/
├── chapters/
├── characters/
└── worldbuilding/
```

### Tool Usage Transformation

Same tools, different purposes:

| Tool | Software Development | Creative Writing | Data Science |
|------|---------------------|------------------|--------------|
| **Write** | Generate code | Create chapters | Save analyses |
| **Read** | Review code | Read manuscripts | Load datasets |
| **Bash** | Run tests | Word counts | Execute Python |
| **Grep** | Find functions | Search themes | Find patterns |

### Response Pattern Customization

Define unique response structures:

**Software Developer**: Code → Test → Document
**Creative Writer**: Inspire → Draft → Revise
**Data Scientist**: Explore → Analyze → Visualize
**Business Analyst**: Understand → Document → Recommend

## Common Use Cases

### Switching Between Projects

Use different styles for different project types:
```bash
# Morning: Data analysis project
/output-style data-scientist

# Afternoon: Content creation
/output-style content-creator

# Evening: System maintenance
/output-style system-administrator
```

### Team Collaboration

Share project-specific styles:
```bash
# In project repository
.claude/output-styles/project-analyst.md

# Team members automatically get the right style
```

### Specialized Workflows

Create styles for specific workflows:
- Migration projects
- Audit processes
- Documentation sprints
- Research phases

## Troubleshooting

### Style Not Available
- Check file location (`.claude/output-styles/` or `~/.claude/output-styles/`)
- Verify `.md` extension
- Ensure valid YAML frontmatter

### Unexpected Behavior
- Verify core functionality is preserved
- Check for conflicting instructions
- Test with simpler prompts

### Performance Issues
- Simplify complex instructions
- Focus on essential behaviors
- Remove redundant patterns

## Examples Directory

Explore the `output-styles/examples/` directory for:
- Production-ready styles
- Implementation patterns
- Domain-specific examples
- Response structures

## Contributing

To contribute a new output style:

1. Create a well-tested style
2. Document use cases clearly
3. Include example interactions
4. Submit a pull request

## See Also

- [Output Styles Repository](../output-styles/)
- [Basic Template](../output-styles/templates/basic-template.md)
- [Example Styles](../output-styles/examples/)
- [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code/output-styles)
