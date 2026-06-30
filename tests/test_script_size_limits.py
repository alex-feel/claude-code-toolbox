"""Tests guarding against E2BIG ('Argument list too long') regressions in the installer.

The Linux kernel's MAX_ARG_STRLEN limit (131,072 bytes / 128 KiB) causes E2BIG when a
script is passed as a single execve() argument -- for example when piped via stdin and run
as `python -c "<entire script>"`. The bootstrap scripts avoid this by downloading
install_claude.py to a file and running `uv run <file>`, which is safe at any size.

Two guards live here:
- The real invariant: every Linux/macOS bootstrap script materializes install_claude.py to
  a file (curl -o ...) and never pipes it inline into an interpreter. This holds at any
  script size, so it is the authoritative protection -- not a byte ceiling.
- A size warning: install_claude.py size is monitored and warns past a comfortable
  threshold, since smaller scripts download faster and keep headroom under the kernel limit.

See: https://github.com/astral-sh/uv/issues/11220
"""

import re
import warnings
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / 'scripts'
INSTALL_CLAUDE = SCRIPTS_DIR / 'install_claude.py'

# Linux kernel MAX_ARG_STRLEN = 131,072 bytes (128 KiB). It binds only when a script is
# passed inline as an execve() argument; the download-to-file bootstrap avoids it entirely.
MAX_ARG_STRLEN = 128 * 1024         # 131,072
# Warn threshold: 100 KiB (smaller scripts download faster and keep headroom).
WARN_THRESHOLD_BYTES = 100 * 1024   # 102,400

# Bootstrap shell scripts that fetch and use install_claude.py. On Linux/macOS each must
# download it to a FILE and run that file, never pipe the script content into an interpreter
# (which would make it one execve() argument and risk E2BIG). This invariant holds at any
# script size, so it -- not a byte ceiling -- is the meaningful regression guard.
BOOTSTRAP_SHELL_SCRIPTS = (
    SCRIPTS_DIR / 'linux' / 'install-claude-linux.sh',
    SCRIPTS_DIR / 'macos' / 'install-claude-macos.sh',
    SCRIPTS_DIR / 'linux' / 'setup-environment.sh',
    SCRIPTS_DIR / 'macos' / 'setup-environment.sh',
)


def _strip_comments(shell_source: str) -> str:
    """Drop full-line shell comments so explanatory text (e.g. a 'python -c' example) is ignored."""
    return '\n'.join(
        line for line in shell_source.splitlines() if not line.lstrip().startswith('#')
    )


class TestInstallClaudeNotPipedInline:
    """The installer must reach the interpreter as a file, never as an inline execve() argument."""

    @pytest.mark.parametrize(
        'script_path',
        BOOTSTRAP_SHELL_SCRIPTS,
        ids=lambda p: f'{p.parent.name}/{p.name}',
    )
    def test_bootstrap_downloads_install_claude_to_file(self, script_path: Path) -> None:
        """Each bootstrap downloads install_claude.py to a file and never pipes it into an interpreter.

        Passing the script inline as a single execve() argument is what risks E2BIG on Linux
        (MAX_ARG_STRLEN). Downloading to a file and running `uv run <file>` avoids that at any
        size, so this is the invariant worth guarding instead of a byte ceiling.
        """
        assert script_path.exists(), f'Bootstrap script missing: {script_path}'
        code = _strip_comments(script_path.read_text(encoding='utf-8'))

        # install_claude.py must be written to a file via `curl ... -o <path>install_claude.py`.
        assert re.search(r'-o\s+\S*install_claude\.py', code), (
            f'{script_path} must download install_claude.py to a file '
            '(curl -o ...install_claude.py) rather than piping it inline, to avoid E2BIG on Linux.'
        )

        # It must never pipe a fetched script straight into an interpreter (the inline
        # anti-pattern that passes the whole script as one execve() argument).
        assert not re.search(r'\|\s*(?:uv run|python[0-9.]*)\b', code), (
            f'{script_path} must not pipe a downloaded script into uv/python; that risks E2BIG. '
            'Download to a file and run `uv run <file>` instead.'
        )


class TestScriptSizeLimits:
    """Monitor install_claude.py size (informational; the download-to-file guard is authoritative)."""

    def test_install_claude_below_warn_threshold(self) -> None:
        """install_claude.py SHOULD stay below 100 KiB for comfortable headroom."""
        size = INSTALL_CLAUDE.stat().st_size
        if size >= WARN_THRESHOLD_BYTES:
            warnings.warn(
                f'install_claude.py is {size:,} bytes ({size / 1024:.1f} KiB), '
                f'approaching the Linux MAX_ARG_STRLEN limit of {MAX_ARG_STRLEN:,} bytes (128 KiB). '
                f'Warning threshold: {WARN_THRESHOLD_BYTES:,} bytes ({WARN_THRESHOLD_BYTES / 1024:.0f} KiB). '
                f'Consider reducing script size.',
                stacklevel=1,
            )
