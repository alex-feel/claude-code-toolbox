# Shared POSIX Script Approach for Cross-Shell Claude Launcher

## Executive Summary

This document explains the **shared POSIX script** approach for launching Claude Code with custom system prompts and settings across all Windows shells (PowerShell, CMD, Git Bash). This solution eliminates the multi-level command escaping issues that plagued earlier attempts and ensures reliable flag passing, particularly for the critical `--settings` flag needed for hooks.

## The Problem

When launching Claude with both a system prompt file and additional settings (for hooks), the command needs to:

1. Read a multi-line prompt file (possibly with Windows CRLF endings)
2. Pass it as a single argument to `--append-system-prompt`
3. Pass a Windows-compatible path to `--settings`
4. Work consistently across PowerShell, CMD, and Git Bash

Initial attempts using `bash -lc "complex command"` failed because:
- The `--settings` flag was getting lost in multi-level shell transitions
- Complex quoting and escaping caused parse errors
- Different shells had different escaping rules

## The Solution: Shared POSIX Script

Instead of passing complex command strings through multiple shell layers, we create a single POSIX script that all launchers call directly:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROMPT_PATH="$HOME/.claude/prompts/{system_prompt_file}"
if [ ! -f "$PROMPT_PATH" ]; then
  echo "Error: System prompt not found at $PROMPT_PATH" >&2
  exit 1
fi

# Read prompt and get Windows path for settings
PROMPT_CONTENT=$(tr -d '\r' < "$PROMPT_PATH")
# Try to get Windows path format; fallback to Unix path if cygpath is not available
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/additional-settings.json" 2>/dev/null ||
  echo "$HOME/.claude/additional-settings.json")"

exec claude --append-system-prompt "$PROMPT_CONTENT" --settings "$SETTINGS_WIN" "$@"
```

This script is saved as `~/.claude/launch-{command_name}.sh` and called by all launchers.

## Implementation for Each Shell

### PowerShell Launcher (`start-claude-python.ps1`)

```powershell
# Find Git Bash
$bashPath = $null
if (Test-Path "C:\Program Files\Git\bin\bash.exe") {
    $bashPath = "C:\Program Files\Git\bin\bash.exe"
} elseif (Test-Path "C:\Program Files (x86)\Git\bin\bash.exe") {
    $bashPath = "C:\Program Files (x86)\Git\bin\bash.exe"
}

# Call the shared script instead of building complex command
$scriptPath = Join-Path $claudeUserDir "launch-claude-python.sh"

if ($args.Count -gt 0) {
    & $bashPath --login $scriptPath @args
} else {
    & $bashPath --login $scriptPath
}
```

### CMD Launcher (`start-claude-python.cmd`)

```batch
set "BASH_EXE=C:\Program Files\Git\bin\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\Program Files (x86)\Git\bin\bash.exe"

set "SCRIPT_WIN=%USERPROFILE%\.claude\launch-claude-python.sh"

if "%~1"=="" (
    "%BASH_EXE%" --login "%SCRIPT_WIN%"
) else (
    "%BASH_EXE%" --login "%SCRIPT_WIN%" %*
)
```

### Git Bash Global Wrapper (`~/.local/bin/claude-python`)

```bash
#!/bin/bash
# Direct execution of the shared script
exec "$HOME/.claude/launch-claude-python.sh" "$@"
```

## Why This Approach Works

### 1. Single Point of Truth
All shells execute the **same** POSIX script, ensuring identical behavior across environments.

### 2. No Multi-Level Escaping
By calling a script file directly instead of passing command strings with `-c`, we avoid:
- PowerShell's `$` expansion and backtick processing
- CMD's metacharacter interpretation (`&`, `|`, `(`, `)`)
- Multiple layers of quote escaping

### 3. Proper Argument Passing
Arguments flow cleanly through the chain:
```text
User command → Shell launcher → bash --login script.sh args → exec claude with proper flags
```

Compare to the failed approach:
```text
User command → Shell launcher → bash -lc "complex string" → shell parsing → claude
                                    ↑ FLAGS LOST HERE ↑
```

### 4. CRLF Normalization
The `tr -d '\r'` command ensures Windows CRLF line endings don't corrupt the prompt:
```bash
PROMPT_CONTENT=$(tr -d '\r' < "$PROMPT_PATH")
```

### 5. Windows Path Compatibility
Using `cygpath -m` provides Windows-compatible paths with forward slashes:
```bash
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/additional-settings.json")"
# Result: C:/Users/username/.claude/additional-settings.json
```

## Technical Deep Dive

### The Problem with `bash -lc` Approach

When using `bash -lc "command"`, the command string undergoes parsing at multiple levels:

1. **First Shell (PowerShell/CMD)**: Interprets quotes, variables, escapes
2. **Bash `-c` parsing**: Re-interprets the string, expanding variables
3. **Command execution**: Final argv construction

Each level can mangle quotes and lose arguments. For example:

```powershell
# PowerShell attempt with -lc
& $bashPath -lc "claude --settings `"path`" --append-system-prompt `"$content`""
# Result: --settings flag lost in translation
```

### How Script Execution Differs

With `bash --login script.sh args`:

1. **First Shell**: Simply passes script path and args as-is
2. **Bash**: Loads and executes script directly (no string parsing)
3. **Script**: Has full control over argument construction

### The `exec` Command

Using `exec claude ...` replaces the bash process with Claude:
- No extra shell process in the background
- Terminal directly attached to Claude
- Clean process tree

## Edge Cases and Robustness

### Missing `cygpath`
The script handles environments without cygpath:
```bash
SETTINGS_WIN="$(cygpath -m "$path" 2>/dev/null || echo "$path")"
```

### Spaces in Paths
All paths are properly quoted throughout the chain:
- PowerShell: `Join-Path` handles spaces
- CMD: Quotes around `%USERPROFILE%`
- Bash: Quotes around all variable expansions

### Empty Prompt Files
The script validates file existence before reading:
```bash
if [ ! -f "$PROMPT_PATH" ]; then
  echo "Error: System prompt not found" >&2
  exit 1
fi
```

### Multi-Line Prompts with Special Characters
Because the prompt is read into a variable and passed as a single quoted argument, special characters (including `---` frontmatter) are preserved correctly:
```bash
exec claude --append-system-prompt "$PROMPT_CONTENT"
#                                   ↑ Double quotes preserve newlines and special chars
```

## Comparison with Direct One-Liner Approaches

The technical documents for [PowerShell](APPEND_SYSTEM_PROMPT_POWERSHELL.md) and [CMD](APPEND_SYSTEM_PROMPT_CMD.md) one-liners remain valid for direct command-line use. They use different techniques:

### PowerShell One-Liner (using `--%`)
```powershell
& 'C:\Program Files\Git\bin\bash.exe' --% -lc 'p=$(tr -d "\r" < ~/.claude/prompts/python-developer.md); exec claude --append-system-prompt="$p"'
```
- Uses `--%` stop-parsing token
- Good for one-time use
- Complex for settings integration

### CMD One-Liner
```cmd
"C:\Program Files\Git\bin\bash.exe" -lc "p=$(tr -d '\r' < ~/.claude/prompts/python-developer.md); exec claude --append-system-prompt=\"$p\""
```
- Embedded quote escaping with `\"`
- Works for simple cases
- Difficult to extend with additional flags

### Shared Script Approach (this document)
- **Maintainable**: Logic in one place
- **Extensible**: Easy to add new flags or features
- **Reliable**: No escaping complexity
- **Testable**: Script can be debugged independently

## Migration and Setup

The `setup_environment.py` script automatically creates:

1. The shared POSIX script in `~/.claude/launch-{command_name}.sh`
2. Shell-specific launchers that call this script
3. Global command wrappers in `~/.local/bin`

Users run:
```bash
uv run scripts/setup_environment.py python
```

Then can use:
```bash
claude-python  # Works in PowerShell, CMD, or Git Bash
```

## Troubleshooting

### Hooks Not Triggering
Verify the settings file is being loaded:
```bash
claude-python --debug 2>&1 | grep -i settings
```

### Path Issues
Check the resolved paths:
```bash
bash -c 'echo "Home: $HOME"; cygpath -m "$HOME/.claude/additional-settings.json"'
```

### Script Permissions
Ensure the script is executable:
```bash
chmod +x ~/.claude/launch-*.sh
```

## Conclusion

The shared POSIX script approach solves the complex problem of cross-shell Claude launching by:

1. **Eliminating** multi-level command escaping
2. **Centralizing** launch logic in one maintainable script
3. **Ensuring** consistent behavior across all Windows shells
4. **Preserving** all command-line arguments correctly

This design pattern—using a shared script instead of complex command strings—is recommended for any cross-shell tool integration on Windows where Git Bash is available as a POSIX compatibility layer.

## References

- [Bash Manual - Command Substitution](https://www.gnu.org/s/bash/manual/html_node/Command-Substitution.html)
- [Microsoft Learn - PowerShell Stop-Parsing Token](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing)
- [MSYS2 - Filesystem Paths](https://www.msys2.org/docs/filesystem-paths/)
- [GNU Coreutils - tr](https://www.gnu.org/software/coreutils/manual/html_node/tr-invocation.html)
