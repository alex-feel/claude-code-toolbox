#!/usr/bin/env python3
"""E2E test status line script.

Generates status line content for Claude Code's status bar.
Receives config file path as first argument.
"""

import json
import sys
from pathlib import Path


def main() -> int:
    """Generate status line content."""
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    config_loaded = 'true' if config_path and config_path.exists() else 'false'

    status = {
        'icon': 'test',
        'text': 'E2E Test',
        'tooltip': 'E2E Testing Environment Active',
        'config_loaded': config_loaded,
    }

    print(json.dumps(status))
    return 0


if __name__ == '__main__':
    sys.exit(main())
