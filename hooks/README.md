# Claude Code Hooks

Event-driven automation scripts that enhance Claude Code's functionality by responding to various events during your coding sessions.

## 📋 Overview

Hooks are scripts that automatically run in response to specific events in Claude Code, such as file edits, tool usage, or notifications. They enable automatic linting, formatting, validation, and custom workflows.

## 🎯 Available Events

### PostToolUse
Triggered after Claude uses specific tools (Write, Edit, MultiEdit, etc.)

**Use cases:**
- Auto-format code after edits
- Run linters on changed files
- Validate syntax or schemas
- Update related files

### Notification
Triggered for system notifications

**Use cases:**
- Desktop notifications for long-running tasks
- Sound alerts
- Status updates to external systems

### Other Events
More events may be added in future versions of Claude Code.

## 📁 Directory Structure

```text
hooks/
├── examples/          # Ready-to-use hook scripts
│   └── python_ruff_lint.py    # Python linting with Ruff
└── README.md         # This file
```

## 🚀 Quick Start

### Using Existing Hooks

1. **Through Environment Configuration:**
   Include hooks in your environment YAML file:
   ```yaml
   hooks:
     - event: PostToolUse
       matcher: Edit|MultiEdit|Write
       type: command
       command: .claude/hooks/python_ruff_lint.py
       files:
         - hooks/examples/python_ruff_lint.py
   ```

2. **Manual Installation:**
   Copy hook files to `~/.claude/hooks/` and update `~/.claude/settings.json`:
   ```json
   {
     "hooks": {
       "PostToolUse": [
         {
           "matcher": "Edit|MultiEdit|Write",
           "hooks": [
             {
               "type": "command",
               "command": ".claude/hooks/python_ruff_lint.py"
             }
           ]
         }
       ]
     }
   }
   ```

## 📝 Example Hooks

### python_ruff_lint.py

Automatically formats and lints Python files using Ruff:
- Runs after any file edit operation
- Auto-fixes formatting issues silently
- Reports unfixable violations back to Claude
- Works cross-platform (Windows/macOS/Linux)

**Requirements:**
- Ruff installed (`uv tool install ruff` or `pip install ruff`)
- Python 3.8+

**Features:**
- Silent auto-formatting
- Error feedback to Claude
- Handles multiple file edits
- Filters only Python files

## 🛠️ Creating Custom Hooks

### Hook Script Structure

```python
#!/usr/bin/env python
"""
Hook description
"""
import json
import sys

# Read event data from stdin
event = json.load(sys.stdin)

# Extract relevant information
tool_name = event.get("tool_name")
tool_input = event.get("tool_input", {})
tool_response = event.get("tool_response", {})

# Your logic here
# ...

# Exit codes:
# 0 - Success
# 1 - Error (stops execution)
# 2 - Warning (sends feedback to Claude)
sys.exit(0)
```

### Event Data Structure

Each event receives JSON data via stdin containing:
- `tool_name`: The tool that was used (Write, Edit, MultiEdit, etc.)
- `tool_input`: Input parameters passed to the tool
- `tool_response`: Response from the tool execution

### Best Practices

1. **Fast Execution**: Keep hooks lightweight and fast
2. **Error Handling**: Always handle exceptions gracefully
3. **Cross-Platform**: Ensure compatibility across OS platforms
4. **Silent Operations**: Avoid unnecessary output to stdout
5. **Meaningful Feedback**: Use stderr and exit codes for feedback

## 🔧 Configuration

### Matcher Patterns

The `matcher` field supports regex patterns to filter when hooks run:
- `Edit|MultiEdit|Write` - Run on any file edit
- `\.py$` - Run only for Python files
- `test_.*\.js$` - Run only for JavaScript test files

### Hook Types

Currently supported type:
- `command`: Execute a shell command or script

### Environment Variables

Hooks have access to standard environment variables plus:
- Working directory is the project root
- PATH includes system and user paths

## 🐛 Troubleshooting

### Hook Not Running
- Check `~/.claude/settings.json` for correct configuration
- Ensure hook file has execute permissions (Unix/macOS)
- Verify the hook file path is correct

### Hook Errors
- Check hook script for syntax errors
- Ensure dependencies are installed
- Test the hook script manually with sample JSON input

### Debugging Tips
- Add logging to a file for debugging
- Use exit code 2 to send messages back to Claude
- Test with simple echo/print statements first

## 📚 Advanced Usage

### Chaining Hooks
Multiple hooks can run for the same event:

**In environment YAML configuration:**
```yaml
hooks:
  files:
    - hooks/examples/format_check.py
    - hooks/examples/type_check.py
    - hooks/examples/run_tests.py
  events:
    - event: PostToolUse
      matcher: "\.py$"
      type: command
      command: format_check.py
    - event: PostToolUse
      matcher: "\.py$"
      type: command
      command: type_check.py
    - event: PostToolUse
      matcher: "\.py$"
      type: command
      command: run_tests.py
```

**Resulting settings.json:**
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "\.py$",
        "hooks": [
          {"type": "command", "command": "py C:/Users/user/.claude/hooks/format_check.py"},
          {"type": "command", "command": "py C:/Users/user/.claude/hooks/type_check.py"},
          {"type": "command", "command": "py C:/Users/user/.claude/hooks/run_tests.py"}
        ]
      }
    ]
  }
}
```

### Conditional Execution
Use matchers and exit codes to create conditional workflows:
```python
if should_format:
    format_code()
    sys.exit(0)
else:
    sys.stderr.write("Skipping format\n")
    sys.exit(0)
```

## 🤝 Contributing

To contribute a new hook:
1. Create a well-documented script in `hooks/examples/`
2. Include usage instructions and requirements
3. Test on multiple platforms
4. Submit a pull request

## 📄 License

Hook scripts in this repository are provided under the MIT License.
