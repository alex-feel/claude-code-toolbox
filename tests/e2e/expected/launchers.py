"""Default-layout renderings of every generated launcher and Windows wrapper.

Each value is the exact text setup writes for a profile in its default
directory, ``~/.claude/golden-cmd``, with the alias ``golden-alias`` and the
system prompt file ``golden-prompt.md``. Keys name the rendering:
``windows/start.ps1``, ``windows/start.cmd``, ``windows/launch.sh/<variant>``,
``unix/launch.sh/<variant>`` and ``windows-wrappers/<file name>``, where
``<variant>`` is ``no-prompt``, ``prompt-replace`` or ``prompt-append``.
``LAUNCHER_PATH_TOKEN`` stands for the absolute path of the profile's
``start.ps1``, which the PowerShell wrappers name.
"""

GOLDEN_COMMAND = 'golden-cmd'
GOLDEN_ALIAS = 'golden-alias'
GOLDEN_PROMPT = 'golden-prompt.md'
LAUNCHER_PATH_TOKEN = '@@LAUNCHER_PATH@@'

DEFAULT_RENDERINGS: dict[str, str] = {
    'unix/launch.sh/no-prompt': r'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/golden-cmd"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/golden-cmd/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

SETTINGS_PATH="$HOME/.claude/golden-cmd/config.json"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/golden-cmd/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_CONFIG_PATH"
fi

echo -e "\033[0;32mStarting Claude Code with golden-cmd configuration...\033[0m"

# Pass any additional arguments to Claude
claude $MCP_FLAGS "$@" --settings "$SETTINGS_PATH"
''',
    'unix/launch.sh/prompt-append': r'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/golden-cmd"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/golden-cmd/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

SETTINGS_PATH="$HOME/.claude/golden-cmd/config.json"
PROMPT_PATH="$HOME/.claude/golden-cmd/prompts/golden-prompt.md"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/golden-cmd/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_CONFIG_PATH"
fi

if [ ! -f "$PROMPT_PATH" ]; then
    echo -e "\033[0;31mError: System prompt not found at $PROMPT_PATH\033[0m"
    echo -e "\033[1;33mPlease run setup_environment.py first\033[0m"
    exit 1
fi

# Version detection function
get_claude_version() {
  claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# Version comparison function (checks if version1 >= version2)
version_ge() {
  local version1="$1"
  local version2="$2"

  # If version detection failed, return false (fallback to safe defaults)
  if [ -z "$version1" ]; then
    return 1
  fi

  # Try using sort -V if available (most reliable)
  if command -v sort >/dev/null 2>&1 && echo | sort -V >/dev/null 2>&1; then
    [ "$(printf '%s\n' "$version1" "$version2" | sort -V | tail -n1)" = "$version1" ]
  else
    # Manual comparison fallback
    local IFS='.'
    local i ver1=($version1) ver2=($version2)
    # Fill empty positions with zeros
    for ((i=0; i<3; i++)); do
      ver1[i]=${ver1[i]:-0}
      ver2[i]=${ver2[i]:-0}
    done
    # Compare each component
    for ((i=0; i<3; i++)); do
      if ((10#${ver1[i]} > 10#${ver2[i]})); then
        return 0
      elif ((10#${ver1[i]} < 10#${ver2[i]})); then
        return 1
      fi
    done
    return 0
  fi
}

# Detect Claude Code version
CLAUDE_VERSION=$(get_claude_version)

# File size detection function (cross-platform)
get_file_size() {
  local file="$1"
  # Try GNU/Linux syntax
  if stat -c %s "$file" 2>/dev/null; then
    return 0
  # Try BSD/macOS syntax
  elif stat -f %z "$file" 2>/dev/null; then
    return 0
  # Universal fallback
  else
    wc -c < "$file" | tr -d ' '
  fi
}

# Safe prompt size threshold (4KB)
SAFE_PROMPT_SIZE=4096

# Append mode: use --append-system-prompt-file if available (v2.0.34+)
echo -e "\033[0;32mStarting Claude Code with golden-cmd configuration...\033[0m"
if version_ge "$CLAUDE_VERSION" "2.0.34"; then
  claude $MCP_FLAGS --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
else
  # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
  PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
  if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
    # Small prompt: safe to use content-based flag
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    claude $MCP_FLAGS --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
  else
    # Large prompt: skip to prevent error
    echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
    echo "Skipping prompt to prevent 'Argument list too long' error" >&2
    echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
    claude $MCP_FLAGS "$@" --settings "$SETTINGS_PATH"
  fi
fi
''',
    'unix/launch.sh/prompt-replace': r'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/golden-cmd"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/golden-cmd/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

SETTINGS_PATH="$HOME/.claude/golden-cmd/config.json"
PROMPT_PATH="$HOME/.claude/golden-cmd/prompts/golden-prompt.md"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/golden-cmd/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_CONFIG_PATH"
fi

if [ ! -f "$PROMPT_PATH" ]; then
    echo -e "\033[0;31mError: System prompt not found at $PROMPT_PATH\033[0m"
    echo -e "\033[1;33mPlease run setup_environment.py first\033[0m"
    exit 1
fi

# Version detection function
get_claude_version() {
  claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# Version comparison function (checks if version1 >= version2)
version_ge() {
  local version1="$1"
  local version2="$2"

  # If version detection failed, return false (fallback to safe defaults)
  if [ -z "$version1" ]; then
    return 1
  fi

  # Try using sort -V if available (most reliable)
  if command -v sort >/dev/null 2>&1 && echo | sort -V >/dev/null 2>&1; then
    [ "$(printf '%s\n' "$version1" "$version2" | sort -V | tail -n1)" = "$version1" ]
  else
    # Manual comparison fallback
    local IFS='.'
    local i ver1=($version1) ver2=($version2)
    # Fill empty positions with zeros
    for ((i=0; i<3; i++)); do
      ver1[i]=${ver1[i]:-0}
      ver2[i]=${ver2[i]:-0}
    done
    # Compare each component
    for ((i=0; i<3; i++)); do
      if ((10#${ver1[i]} > 10#${ver2[i]})); then
        return 0
      elif ((10#${ver1[i]} < 10#${ver2[i]})); then
        return 1
      fi
    done
    return 0
  fi
}

# Detect Claude Code version
CLAUDE_VERSION=$(get_claude_version)

# File size detection function (cross-platform)
get_file_size() {
  local file="$1"
  # Try GNU/Linux syntax
  if stat -c %s "$file" 2>/dev/null; then
    return 0
  # Try BSD/macOS syntax
  elif stat -f %z "$file" 2>/dev/null; then
    return 0
  # Universal fallback
  else
    wc -c < "$file" | tr -d ' '
  fi
}

# Safe prompt size threshold (4KB)
SAFE_PROMPT_SIZE=4096

# Replace mode: Check for continuation flags
HAS_CONTINUE=false
for arg in "$@"; do
  if [[ "$arg" == "--continue" || "$arg" == "-c" || "$arg" == "--resume" || "$arg" == "-r" ]]; then
    HAS_CONTINUE=true
    break
  fi
done

# For v2.0.64+: bug #11641 is fixed, --system-prompt works correctly with --continue/--resume
if version_ge "$CLAUDE_VERSION" "2.0.64"; then
  if [ "$HAS_CONTINUE" = true ]; then
    echo -e "\033[0;32mResuming Claude Code session with golden-cmd configuration...\033[0m"
  else
    echo -e "\033[0;32mStarting Claude Code with golden-cmd configuration...\033[0m"
  fi
  # Fixed in v2.0.64: always use --system-prompt-file (no need for workaround)
  claude $MCP_FLAGS --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
elif [ "$HAS_CONTINUE" = true ]; then
  echo -e "\033[0;32mResuming Claude Code session with golden-cmd configuration...\033[0m"
  # Legacy workaround for v < 2.0.64: use --append-system-prompt for continuation
  # Continuation: use --append-system-prompt-file if available (v2.0.34+)
  if version_ge "$CLAUDE_VERSION" "2.0.34"; then
    claude $MCP_FLAGS --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
  else
    # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
    PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
    if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
      # Small prompt: safe to use content-based flag
      PROMPT_CONTENT=$(cat "$PROMPT_PATH")
      claude $MCP_FLAGS --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
    else
      # Large prompt: skip to prevent error
      echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
      echo "Skipping prompt to prevent 'Argument list too long' error" >&2
      echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
      claude $MCP_FLAGS "$@" --settings "$SETTINGS_PATH"
    fi
  fi
else
  echo -e "\033[0;32mStarting Claude Code with golden-cmd configuration...\033[0m"
  # New session: use --system-prompt-file (available in v2.0.14+)
  if version_ge "$CLAUDE_VERSION" "2.0.14"; then
    claude $MCP_FLAGS --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
  else
    # Fallback to content-based flag for very old versions
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    claude $MCP_FLAGS --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
  fi
fi
''',
    'windows-wrappers/golden-alias': r'''#!/bin/bash
# Bash wrapper for golden-alias (alias for golden-cmd)
exec "$HOME/.claude/golden-cmd/launch.sh" "$@"
''',
    'windows-wrappers/golden-alias.cmd': r'''@echo off
REM Global golden-alias command for CMD (alias for golden-cmd)
REM Source OS-level environment variables (if configured)
set "ENV_FILE=%USERPROFILE%\.claude\golden-cmd\env.cmd"
if exist "%ENV_FILE%" call "%ENV_FILE%"
set "BASH_EXE=C:\Program Files\Git\bin\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\Program Files (x86)\Git\bin\bash.exe"
set "SCRIPT_WIN=%USERPROFILE%\.claude\golden-cmd\launch.sh"
if "%~1"=="" (
    "%BASH_EXE%" --login "%SCRIPT_WIN%"
) else (
    "%BASH_EXE%" --login "%SCRIPT_WIN%" %*
)
''',
    'windows-wrappers/golden-alias.ps1': r'''# Global golden-alias command for PowerShell (alias for golden-cmd)
& "@@LAUNCHER_PATH@@" @args
''',
    'windows-wrappers/golden-cmd': r'''#!/bin/bash
# Bash wrapper for golden-cmd to work in Git Bash

# Call the shared launch script
exec "$HOME/.claude/golden-cmd/launch.sh" "$@"
''',
    'windows-wrappers/golden-cmd.cmd': r'''@echo off
REM Global golden-cmd command for CMD
REM Source OS-level environment variables (if configured)
set "ENV_FILE=%USERPROFILE%\.claude\golden-cmd\env.cmd"
if exist "%ENV_FILE%" call "%ENV_FILE%"
set "BASH_EXE=C:\Program Files\Git\bin\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\Program Files (x86)\Git\bin\bash.exe"
set "SCRIPT_WIN=%USERPROFILE%\.claude\golden-cmd\launch.sh"
if "%~1"=="" (
    "%BASH_EXE%" --login "%SCRIPT_WIN%"
) else (
    "%BASH_EXE%" --login "%SCRIPT_WIN%" %*
)
''',
    'windows-wrappers/golden-cmd.ps1': r'''# Global golden-cmd command for PowerShell
& "@@LAUNCHER_PATH@@" @args
''',
    'windows/launch.sh/no-prompt': r'''#!/usr/bin/env bash
set -euo pipefail

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/golden-cmd"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/golden-cmd/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/golden-cmd/config.json" 2>/dev/null ||
  echo "$HOME/.claude/golden-cmd/config.json")"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/golden-cmd/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_WIN="$(cygpath -m "$MCP_CONFIG_PATH" 2>/dev/null || echo "$MCP_CONFIG_PATH")"
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_WIN"
fi

exec claude $MCP_FLAGS "$@" --settings "$SETTINGS_WIN"
''',
    'windows/launch.sh/prompt-append': r'''#!/usr/bin/env bash
set -euo pipefail

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/golden-cmd"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/golden-cmd/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/golden-cmd/config.json" 2>/dev/null ||
  echo "$HOME/.claude/golden-cmd/config.json")"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/golden-cmd/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_WIN="$(cygpath -m "$MCP_CONFIG_PATH" 2>/dev/null || echo "$MCP_CONFIG_PATH")"
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_WIN"
fi

PROMPT_PATH="$HOME/.claude/golden-cmd/prompts/golden-prompt.md"
if [ ! -f "$PROMPT_PATH" ]; then
  echo "Error: System prompt not found at $PROMPT_PATH" >&2
  exit 1
fi

# Version detection function
get_claude_version() {
  claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# Version comparison function (checks if version1 >= version2)
version_ge() {
  local version1="$1"
  local version2="$2"

  # If version detection failed, return false (fallback to safe defaults)
  if [ -z "$version1" ]; then
    return 1
  fi

  # Try using sort -V if available (most reliable)
  if command -v sort >/dev/null 2>&1 && echo | sort -V >/dev/null 2>&1; then
    [ "$(printf '%s\n' "$version1" "$version2" | sort -V | tail -n1)" = "$version1" ]
  else
    # Manual comparison fallback
    local IFS='.'
    local i ver1=($version1) ver2=($version2)
    # Fill empty positions with zeros
    for ((i=0; i<3; i++)); do
      ver1[i]=${ver1[i]:-0}
      ver2[i]=${ver2[i]:-0}
    done
    # Compare each component
    for ((i=0; i<3; i++)); do
      if ((10#${ver1[i]} > 10#${ver2[i]})); then
        return 0
      elif ((10#${ver1[i]} < 10#${ver2[i]})); then
        return 1
      fi
    done
    return 0
  fi
}

# Detect Claude Code version
CLAUDE_VERSION=$(get_claude_version)

# File size detection function (cross-platform)
get_file_size() {
  local file="$1"
  # Try GNU/Linux syntax
  if stat -c %s "$file" 2>/dev/null; then
    return 0
  # Try BSD/macOS syntax
  elif stat -f %z "$file" 2>/dev/null; then
    return 0
  # Universal fallback
  else
    wc -c < "$file" | tr -d ' '
  fi
}

# Safe prompt size threshold (4KB)
SAFE_PROMPT_SIZE=4096

# Append mode: use --append-system-prompt-file if available (v2.0.34+)
if version_ge "$CLAUDE_VERSION" "2.0.34"; then
  exec claude $MCP_FLAGS --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
else
  # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
  PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
  if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
    # Small prompt: safe to use content-based flag
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    exec claude $MCP_FLAGS --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
  else
    # Large prompt: skip to prevent error
    echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
    echo "Skipping prompt to prevent 'Argument list too long' error" >&2
    echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
    exec claude $MCP_FLAGS "$@" --settings "$SETTINGS_WIN"
  fi
fi
''',
    'windows/launch.sh/prompt-replace': r'''#!/usr/bin/env bash
set -euo pipefail

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/golden-cmd"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/golden-cmd/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/golden-cmd/config.json" 2>/dev/null ||
  echo "$HOME/.claude/golden-cmd/config.json")"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/golden-cmd/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_WIN="$(cygpath -m "$MCP_CONFIG_PATH" 2>/dev/null || echo "$MCP_CONFIG_PATH")"
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_WIN"
fi

PROMPT_PATH="$HOME/.claude/golden-cmd/prompts/golden-prompt.md"
if [ ! -f "$PROMPT_PATH" ]; then
  echo "Error: System prompt not found at $PROMPT_PATH" >&2
  exit 1
fi

# Version detection function
get_claude_version() {
  claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# Version comparison function (checks if version1 >= version2)
version_ge() {
  local version1="$1"
  local version2="$2"

  # If version detection failed, return false (fallback to safe defaults)
  if [ -z "$version1" ]; then
    return 1
  fi

  # Try using sort -V if available (most reliable)
  if command -v sort >/dev/null 2>&1 && echo | sort -V >/dev/null 2>&1; then
    [ "$(printf '%s\n' "$version1" "$version2" | sort -V | tail -n1)" = "$version1" ]
  else
    # Manual comparison fallback
    local IFS='.'
    local i ver1=($version1) ver2=($version2)
    # Fill empty positions with zeros
    for ((i=0; i<3; i++)); do
      ver1[i]=${ver1[i]:-0}
      ver2[i]=${ver2[i]:-0}
    done
    # Compare each component
    for ((i=0; i<3; i++)); do
      if ((10#${ver1[i]} > 10#${ver2[i]})); then
        return 0
      elif ((10#${ver1[i]} < 10#${ver2[i]})); then
        return 1
      fi
    done
    return 0
  fi
}

# Detect Claude Code version
CLAUDE_VERSION=$(get_claude_version)

# File size detection function (cross-platform)
get_file_size() {
  local file="$1"
  # Try GNU/Linux syntax
  if stat -c %s "$file" 2>/dev/null; then
    return 0
  # Try BSD/macOS syntax
  elif stat -f %z "$file" 2>/dev/null; then
    return 0
  # Universal fallback
  else
    wc -c < "$file" | tr -d ' '
  fi
}

# Safe prompt size threshold (4KB)
SAFE_PROMPT_SIZE=4096

# Replace mode: Check for continuation flags
HAS_CONTINUE=false
for arg in "$@"; do
  if [[ "$arg" == "--continue" || "$arg" == "-c" || "$arg" == "--resume" || "$arg" == "-r" ]]; then
    HAS_CONTINUE=true
    break
  fi
done

# For v2.0.64+: bug #11641 is fixed, --system-prompt works correctly with --continue/--resume
if version_ge "$CLAUDE_VERSION" "2.0.64"; then
  # Fixed in v2.0.64: always use --system-prompt-file (no need for workaround)
  exec claude $MCP_FLAGS --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
elif [ "$HAS_CONTINUE" = true ]; then
  # Legacy workaround for v < 2.0.64: use --append-system-prompt for continuation
  # Continuation: use --append-system-prompt-file if available (v2.0.34+)
  if version_ge "$CLAUDE_VERSION" "2.0.34"; then
    exec claude $MCP_FLAGS --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
  else
    # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
    PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
    if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
      # Small prompt: safe to use content-based flag
      PROMPT_CONTENT=$(cat "$PROMPT_PATH")
      exec claude $MCP_FLAGS --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
    else
      # Large prompt: skip to prevent error
      echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
      echo "Skipping prompt to prevent 'Argument list too long' error" >&2
      echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
      exec claude $MCP_FLAGS "$@" --settings "$SETTINGS_WIN"
    fi
  fi
else
  # New session: use --system-prompt-file (available in v2.0.14+)
  if version_ge "$CLAUDE_VERSION" "2.0.14"; then
    exec claude $MCP_FLAGS --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
  else
    # Fallback to content-based flag for very old versions
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    exec claude $MCP_FLAGS --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
  fi
fi
''',
    'windows/start.cmd': r'''@echo off
REM Claude Code Environment Launcher for CMD
REM This script starts Claude Code with the configured environment

REM Source OS-level environment variables (if configured)
set "ENV_FILE=%USERPROFILE%\.claude\golden-cmd\env.cmd"
if exist "%ENV_FILE%" call "%ENV_FILE%"

echo Starting Claude Code with golden-cmd configuration...

REM Call shared script
set "BASH_EXE=C:\Program Files\Git\bin\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\Program Files (x86)\Git\bin\bash.exe"

set "SCRIPT_WIN=%USERPROFILE%\.claude\golden-cmd\launch.sh"

if "%~1"=="" (
    "%BASH_EXE%" --login "%SCRIPT_WIN%"
) else (
    echo Passing additional arguments: %*
    "%BASH_EXE%" --login "%SCRIPT_WIN%" %*
)
''',
    'windows/start.ps1': r'''# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

$claudeUserDir = Join-Path $env:USERPROFILE ".claude"

# Source OS-level environment variables (if configured)
$envFile = Join-Path (Join-Path $claudeUserDir "golden-cmd") "env.ps1"
if (Test-Path $envFile) { . $envFile }

Write-Host "Starting Claude Code with golden-cmd configuration..." -ForegroundColor Green

# Find Git Bash (required for Claude Code on Windows)
$bashPath = $null
if (Test-Path "C:\Program Files\Git\bin\bash.exe") {
    $bashPath = "C:\Program Files\Git\bin\bash.exe"
} elseif (Test-Path "C:\Program Files (x86)\Git\bin\bash.exe") {
    $bashPath = "C:\Program Files (x86)\Git\bin\bash.exe"
} else {
    Write-Host "Error: Git Bash not found! Please install Git for Windows." -ForegroundColor Red
    exit 1
}

# Call the shared launch script
$scriptPath = Join-Path (Join-Path $claudeUserDir "golden-cmd") "launch.sh"

if ($args.Count -gt 0) {
    Write-Host "Passing additional arguments: $args" -ForegroundColor Cyan
    & $bashPath --login $scriptPath @args
} else {
    & $bashPath --login $scriptPath
}
''',
}
