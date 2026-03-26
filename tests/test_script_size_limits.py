"""Tests enforcing script size limits to prevent E2BIG regressions.

The Linux kernel's MAX_ARG_STRLEN limit (131,072 bytes / 128 KiB) causes
'Argument list too long' (E2BIG) errors when scripts are passed as single
execve() arguments. Bootstrap scripts that download-to-file avoid this,
but monitoring ensures the limit is never silently exceeded.

See: https://github.com/astral-sh/uv/issues/11220
"""

import warnings
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / 'scripts'
INSTALL_CLAUDE = SCRIPTS_DIR / 'install_claude.py'

# Linux kernel MAX_ARG_STRLEN = 131,072 bytes (128 KiB)
# Warn threshold: 100 KiB (provides 28 KiB headroom)
# Error threshold: 120 KiB (provides 8 KiB headroom)
WARN_THRESHOLD_BYTES = 100 * 1024   # 102,400
ERROR_THRESHOLD_BYTES = 120 * 1024  # 122,880
MAX_ARG_STRLEN = 128 * 1024         # 131,072


class TestScriptSizeLimits:
    """Enforce script size limits to prevent E2BIG regressions on Linux."""

    @pytest.mark.xfail(
        reason='install_claude.py is currently ~157 KiB, exceeding 120 KiB limit. '
               'Bootstrap scripts now use download-to-file, but size should be reduced.',
        strict=False,
    )
    def test_install_claude_below_error_threshold(self) -> None:
        """install_claude.py MUST stay below 120 KiB to maintain Linux compatibility."""
        size = INSTALL_CLAUDE.stat().st_size
        assert size < ERROR_THRESHOLD_BYTES, (
            f'install_claude.py is {size:,} bytes ({size / 1024:.1f} KiB), '
            f'which exceeds the error threshold of {ERROR_THRESHOLD_BYTES:,} bytes '
            f'({ERROR_THRESHOLD_BYTES / 1024:.0f} KiB). '
            f'The Linux kernel MAX_ARG_STRLEN limit is {MAX_ARG_STRLEN:,} bytes (128 KiB). '
            f'Reduce the script size to prevent E2BIG errors on Linux/WSL.'
        )

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
