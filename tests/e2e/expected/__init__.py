"""Platform-specific expected outputs for E2E testing.

This module provides platform-aware expected values by dynamically importing
the appropriate platform module based on sys.platform detection.

Usage:
    from tests.e2e.expected import EXPECTED_FILES, EXPECTED_PATHS

The module exports:
    - EXPECTED_FILES: List of expected file path templates relative to fixture directories
    - EXPECTED_PATHS: Dict mapping logical names to expected path templates
    - COMMON_FILES: List of files common to all platforms
    - EXPECTED_JSON_KEYS: Dict of expected keys in generated JSON files

Path templates use fixture key placeholders ({claude_dir}, {local_bin}, etc.)
and {cmd} for the command name.
"""

import sys

# Import common values available on all platforms
from .common import COMMON_FILES
from .common import EXPECTED_JSON_KEYS

# Platform detection and dynamic import
# Type checkers understand these conditional imports
if sys.platform == 'win32':
    from .windows import EXPECTED_FILES
    from .windows import EXPECTED_PATHS
elif sys.platform == 'darwin':
    from .macos import EXPECTED_FILES
    from .macos import EXPECTED_PATHS
else:
    # Linux and other Unix-like systems
    from .linux import EXPECTED_FILES
    from .linux import EXPECTED_PATHS

__all__ = [
    'COMMON_FILES',
    'EXPECTED_FILES',
    'EXPECTED_JSON_KEYS',
    'EXPECTED_PATHS',
]
