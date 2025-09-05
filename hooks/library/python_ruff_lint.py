#!/usr/bin/env python
"""
PostToolUse hook: automatically fixes Python files with Ruff, and sends any
unresolved violations back to Claude via stderr with exit code 2.

Works on Windows / macOS / Linux.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

event = json.load(sys.stdin)
tool = event.get('tool_name')  # "Write" | "Edit" | "MultiEdit"

# Collect affected paths, accounting for different input schemas
paths: set[Path] = set()

if tool == 'MultiEdit':  # array of edits
    for edit in event.get('tool_input', {}).get('edits', []):
        p = edit.get('file_path')
        if p:
            paths.add(Path(p))
else:  # Write or Edit
    p = (
        event.get('tool_input', {}).get('file_path')
        or event.get('tool_response', {}).get('filePath')
    )
    if p:
        paths.add(Path(p))

# Filter .py files
py_files = [str(p) for p in paths if p.suffix.lower() == '.py']
if not py_files:
    sys.exit(0)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


# Check for problems
result = run(['ruff', 'check', *py_files])  # exit code 1 if violations remain
if result.returncode:
    sys.stderr.write(result.stdout)
    sys.exit(2)  # feedback for Claude
sys.exit(0)
