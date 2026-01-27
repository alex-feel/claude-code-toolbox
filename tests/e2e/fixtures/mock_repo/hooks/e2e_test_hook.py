#!/usr/bin/env python3
"""E2E test hook script for validation.

This hook is triggered by PostToolUse events for Edit/MultiEdit/Write operations.
It receives a config file path as the first argument.
"""

import json
import sys
from pathlib import Path


def main() -> int:
    """Process hook invocation and validate input."""
    # Read config if provided
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    # Read stdin (Claude Code passes event data via stdin)
    input_data = sys.stdin.read()

    try:
        event = json.loads(input_data) if input_data.strip() else {}
    except json.JSONDecodeError:
        event = {}

    # Simple validation: just pass through
    # In real hooks, you would process the event and return modified data
    config_loaded = False
    if config_path is not None and config_path.exists():
        config_loaded = True

    result = {
        'continue': True,
        'message': 'E2E test hook executed successfully',
        'config_loaded': config_loaded,
        'event_type': event.get('type', 'unknown'),
    }

    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
