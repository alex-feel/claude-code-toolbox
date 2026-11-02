"""E2E tests proving that the real Claude Code binary runs the apiKeyHelper setup writes on Windows.

Claude Code runs apiKeyHelper through cmd.exe on Windows and sends what the
helper prints as the request's API key. These tests write the helper command
with the toolbox's own writers -- write_user_settings() into the base
settings.json and create_profile_config() into an isolated profile's
config.json -- under a home folder whose name contains a space, and run one
non-interactive turn of the real binary against an offline fake API with no
API key in the environment: the x-api-key header of the request carries the
helper's output. The same config.json with the quotes taken out of the
command makes cmd.exe split the path at the space, the helper never starts,
and the request carries no key.

Skipped when the binary is absent; CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1
(set in CI) turns absence into a failure instead of a silent skip.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts import setup_environment
from tests.e2e import linked_entries_support as support
from tests.e2e.fake_anthropic_api import FakeAnthropicServer

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_PROFILE_NAME = 'e2e-key-helper'
_PROMPT = 'Reply with the single word READY.'
_HELPER_COMMAND = 'uv run --no-project --python 3.12 ~/.claude/scripts/key_helper.py'
_HELPER_KEY = 'sk-ant-api03-e2e-key-from-the-helper-0000000000000000000'

pytestmark = [
    pytest.mark.real_binary,
    pytest.mark.skipif(sys.platform != 'win32', reason='cmd.exe runs apiKeyHelper only on Windows'),
    pytest.mark.skipif(
        support.CLAUDE_CMD is None and not _REQUIRE_REAL_BINARY,
        reason='claude binary not available',
    ),
    pytest.mark.skipif(shutil.which('uv') is None, reason='uv is not on PATH'),
]


@dataclass
class HelperWorkspace:
    """A home folder whose name contains a space, the helper script inside it, and the fake API."""

    home: Path
    project_dir: Path
    server: FakeAnthropicServer

    def run(self, config_dir: Path, *settings_args: str) -> list[dict[str, str]]:
        """Run one turn of the real binary with ``config_dir`` as CLAUDE_CONFIG_DIR and no API key.

        Args:
            config_dir: The profile directory.
            settings_args: Extra claude arguments (``--settings <config.json>``).

        Returns:
            The headers of every request the turn sent.
        """
        assert support.CLAUDE_CMD is not None
        env = support.claude_child_env(config_dir=config_dir, home=self.home, api_url=self.server.url)
        for name in ('ANTHROPIC_API_KEY', 'UV_LOCKED'):
            env.pop(name, None)
        support.seed_global_config(config_dir, self.project_dir)
        first = len(self.server.headers)
        argv = [str(support.CLAUDE_CMD), *support.print_args(_PROMPT, *settings_args)]
        run = support.run_stream_json(argv, env=env, cwd=self.project_dir, server=self.server)
        assert run.returncode == 0, run.describe()
        headers = self.server.headers[first:]
        assert headers, run.describe()
        return headers


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HelperWorkspace]:
    """Provide the spaced home with the helper script, the toolbox's home lookups pointed at it, and the fake API."""
    root, cleanup = support.workspace_root(tmp_path)
    try:
        home = root / 'Test User'
        scripts = home / '.claude' / 'scripts'
        scripts.mkdir(parents=True)
        (scripts / 'key_helper.py').write_text(f'print({_HELPER_KEY!r})\n', encoding='utf-8')
        project_dir = root / 'project'
        project_dir.mkdir()
        monkeypatch.setattr(setup_environment, 'get_real_user_home', lambda: home)
        server = FakeAnthropicServer().start()
        try:
            yield HelperWorkspace(home=home, project_dir=project_dir, server=server)
        finally:
            server.stop()
    finally:
        cleanup()


def test_base_settings_json_helper_supplies_the_api_key(workspace: HelperWorkspace) -> None:
    """The helper write_user_settings() writes into settings.json runs, and its output is the request's key."""
    config_dir = workspace.home / '.claude'
    assert setup_environment.write_user_settings({'apiKeyHelper': _HELPER_COMMAND}, config_dir)

    headers = workspace.run(config_dir)

    assert [request.get('x-api-key') for request in headers] == [_HELPER_KEY] * len(headers)


def test_isolated_config_json_helper_supplies_the_api_key(workspace: HelperWorkspace) -> None:
    """The helper create_profile_config() writes into config.json runs, and its output is the request's key."""
    config_dir = workspace.home / '.claude' / _PROFILE_NAME
    assert setup_environment.create_profile_config({}, config_dir, user_settings={'apiKeyHelper': _HELPER_COMMAND})

    headers = workspace.run(config_dir, '--settings', str(config_dir / 'config.json'))

    assert [request.get('x-api-key') for request in headers] == [_HELPER_KEY] * len(headers)


def test_unquoted_helper_path_sends_no_key(workspace: HelperWorkspace) -> None:
    """The same config.json with the quotes taken out of the command never reaches the helper."""
    config_dir = workspace.home / '.claude' / _PROFILE_NAME
    assert setup_environment.create_profile_config({}, config_dir, user_settings={'apiKeyHelper': _HELPER_COMMAND})
    config_path = config_dir / 'config.json'
    settings = json.loads(config_path.read_text(encoding='utf-8'))
    assert settings['apiKeyHelper'].count('"') == 2, settings['apiKeyHelper']
    settings['apiKeyHelper'] = settings['apiKeyHelper'].replace('"', '')
    config_path.write_text(json.dumps(settings), encoding='utf-8')

    headers = workspace.run(config_dir, '--settings', str(config_path))

    assert all(request.get('x-api-key') != _HELPER_KEY for request in headers), headers
