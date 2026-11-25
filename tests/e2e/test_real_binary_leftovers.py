"""E2E test of the MCP server leftovers against the real Claude CLI.

An isolated profile is installed through main() with Step 13 registering its
user-scope MCP servers through the real ``claude mcp add``, so the manifest
records the digest of the entry the CLI stored in the profile's own
.claude.json. The configuration then drops two of the servers and one of
their entries is edited by hand: a re-run lists the untouched one as a
leftover and the edited one as changed, and a run given --remove-leftovers
removes the untouched one through the real ``claude mcp remove`` in Step 23,
reads the profile's .claude.json again to record it as removed, and leaves
the edited entry and the declared server in place.

The CLI needs no authentication for these commands and every server points
at a closed local port, so nothing reaches the network. Skipped when the
binary is absent; CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1 (set in CI) turns
absence into a failure instead of a silent skip.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e.leftovers_support import SKIP
from tests.e2e.leftovers_support import leftover_rows
from tests.e2e.leftovers_support import printed
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config
from tests.e2e.validators import validate_manifest

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_CLAUDE_CMD = setup_environment.find_command('claude')
PROFILE = 'mcp-left'

pytestmark = [
    pytest.mark.real_binary,
    pytest.mark.skipif(
        _CLAUDE_CMD is None and not _REQUIRE_REAL_BINARY,
        reason='claude binary not available',
    ),
]


def _server(name: str) -> dict[str, Any]:
    return {'name': name, 'scope': 'user', 'transport': 'http', 'url': f'http://127.0.0.1:9/{name}'}


def _config(names: list[str]) -> dict[str, Any]:
    return {'name': 'MCP Leftovers', 'command-names': [PROFILE], 'mcp-servers': [_server(name) for name in names]}


def _user_servers(profile_dir: Path) -> dict[str, Any]:
    content: dict[str, Any] = json.loads((profile_dir / '.claude.json').read_text(encoding='utf-8'))
    servers: dict[str, Any] = content.get('mcpServers', {})
    return servers


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The working directory of the runs, outside every real configuration, with the CLI kept offline."""
    project = tmp_path / 'project'
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv('DISABLE_AUTOUPDATER', '1')
    monkeypatch.setenv('CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', '1')
    return project


def test_real_binary_available_when_required() -> None:
    """CI must fail loudly when the binary is missing, never skip silently."""
    if _REQUIRE_REAL_BINARY:
        assert _CLAUDE_CMD is not None, 'CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1 but no claude binary was found'


@pytest.mark.usefixtures('project_dir')
def test_a_dropped_server_is_removed_and_an_edited_one_stays(
    e2e_isolated_home: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert _CLAUDE_CMD is not None
    profile_dir = e2e_isolated_home['claude_dir'] / PROFILE
    configs = tmp_path / 'configs'
    configs.mkdir()
    cfg = write_config(configs, 'mcp.yaml', _config(['lefty', 'edited', 'keeper']))

    assert run_main([str(cfg), *SKIP, '--yes'], real_mcp=True, claude_path=_CLAUDE_CMD) == 0

    servers = _user_servers(profile_dir)
    assert sorted(servers) == ['edited', 'keeper', 'lefty'], servers
    manifest = read_manifest(profile_dir)
    assert not validate_manifest(profile_dir / 'manifest.json', _config(['lefty', 'edited', 'keeper']))
    recorded = {record['name']: record['sha256'] for record in manifest['mcp_servers']}
    assert recorded == {name: {'user': setup_environment.leftover_digest(servers[name])} for name in servers}, (
        'each entry the CLI stored is recorded by the digest of what it holds'
    )

    write_config(configs, 'mcp.yaml', _config(['keeper']))
    edited = dict(servers['edited'], url='http://127.0.0.1:9/edited-by-hand')
    content = json.loads((profile_dir / '.claude.json').read_text(encoding='utf-8'))
    content['mcpServers']['edited'] = edited
    (profile_dir / '.claude.json').write_text(json.dumps(content, indent=2), encoding='utf-8')
    capsys.readouterr()

    assert run_main([str(cfg), *SKIP, '--yes'], real_mcp=True, claude_path=_CLAUDE_CMD) == 0

    rows = [row.strip() for row in leftover_rows(printed(capsys))]
    assert '[changed since written: left in place, no longer tracked] MCP server: edited (scope: user)' in rows, rows
    assert '[leftover] MCP server: lefty (scope: user)' in rows, rows
    assert sorted(_user_servers(profile_dir)) == ['edited', 'keeper', 'lefty'], 'nothing is removed without the flag'

    assert run_main([str(cfg), *SKIP, '--yes', '--remove-leftovers'], real_mcp=True, claude_path=_CLAUDE_CMD) == 0

    output = printed(capsys)
    assert '[remove] MCP server: lefty (scope: user)' in [row.strip() for row in leftover_rows(output)]
    assert 'Removed leftover MCP server: lefty (scope: user)' in output
    servers = _user_servers(profile_dir)
    assert sorted(servers) == ['edited', 'keeper'], servers
    assert servers['edited'] == edited, 'an entry edited by hand stays as the user left it'
    leftovers = read_manifest(profile_dir)['leftovers']
    assert leftovers['removed'] == ['MCP server: lefty (scope: user)']
    assert leftovers['items'] == []
