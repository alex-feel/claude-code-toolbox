"""E2E tests proving that a slash command passed to a profile launcher reaches the real Claude Code binary.

On Windows the launcher runs under Git Bash, which rewrites an argument that
looks like a POSIX path when it starts the native claude.exe. The real
binary runs one non-interactive turn through the launcher
create_launcher_script() writes, against an offline fake API, with
``-p "/<command> scheduled OWNER/NAME"``: the command's body sentinel in the
recorded request shows that Claude Code received the slash command as typed
and expanded it, together with its arguments.

Skipped when the binary is absent; CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1
(set in CI) turns absence into a failure instead of a silent skip.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e import linked_entries_support as support
from tests.e2e.launcher_support import PATH_CONVERSION_VARIABLES
from tests.e2e.linked_entries_workspace import Workspace
from tests.e2e.linked_entries_workspace import open_workspace

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_PROFILE_NAME = 'e2e-slash'
_COMMAND_ARGUMENTS = 'scheduled OWNER/NAME'

pytestmark = [
    pytest.mark.real_binary,
    pytest.mark.skipif(
        support.CLAUDE_CMD is None and not _REQUIRE_REAL_BINARY,
        reason='claude binary not available',
    ),
]


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Workspace]:
    """Provide an isolated home, a populated source profile and a running fake API."""
    yield from open_workspace(tmp_path)


@pytest.mark.parametrize('mode', ['replace', 'append'])
def test_launcher_hands_slash_command_to_claude(workspace: Workspace, mode: str) -> None:
    """Claude Code runs the slash command the launcher received and sends its body with the arguments."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real')
    for variable in PATH_CONVERSION_VARIABLES:
        profile.env.pop(variable, None)

    run = profile.run_launcher(mode, f'/{support.COMMAND_NAME} {_COMMAND_ARGUMENTS}')

    assert run.returncode == 0, run.describe()
    assert len(run.bodies) == 1, run.describe()
    assert run.init is not None, run.describe()
    assert support.COMMAND_NAME in run.init['slash_commands'], run.describe()
    assert support.SENTINELS['commands'] in run.body_text, run.describe()
    assert _COMMAND_ARGUMENTS in run.body_text, run.describe()
    assert 'Program Files' not in run.body_text, run.describe()
