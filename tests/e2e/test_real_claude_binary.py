"""E2E tests exercising the real Claude CLI for MCP configuration.

These tests run `claude mcp` config commands (which require no
authentication) against a fully isolated CLAUDE_CONFIG_DIR, verifying the
contracts the idempotent MCP configuration depends on:

- serialization parity: _build_expected_mcp_entry() predicts exactly what
  `claude mcp add` writes per scope and transport, so a binary-version drift
  in the stored shape fails here instead of silently disabling the skip;
- idempotency: a rerun with an unchanged config performs no remove/add
  cycle, preserving per-project disabled-server state and the mcpOAuth
  credential entry keyed by name plus a hash of the server's
  type/url/headers (`claude mcp remove` deletes that entry for http/sse
  servers, which is what de-authenticated unchanged servers before);
- reconfiguration: a changed config still lands on disk, and a stale
  same-name entry at another scope is cleaned up.

Skipped when the binary is absent; CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1
(set in CI) turns absence into a failure instead of a silent skip.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_CLAUDE_CMD = setup_environment.find_command('claude')

pytestmark = [
    pytest.mark.real_binary,
    pytest.mark.skipif(
        _CLAUDE_CMD is None and not _REQUIRE_REAL_BINARY,
        reason='claude binary not available',
    ),
]


def _derive_mcp_oauth_key(name: str, entry: dict[str, Any]) -> str:
    """Derive the mcpOAuth credential key the Claude CLI uses for a server.

    The CLI keys stored MCP OAuth tokens as
    ``<name>|sha256(JSON.stringify({type, url, headers}))[:16]``, so an
    unchanged type/url/headers triple keeps the key stable across runs.

    Args:
        name: MCP server name.
        entry: The stored mcpServers entry.

    Returns:
        The credential key.
    """
    payload = {
        'type': entry.get('type'),
        'url': entry.get('url'),
        'headers': entry.get('headers') or {},
    }
    serialized = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
    digest = hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]
    return f'{name}|{digest}'


@pytest.fixture
def isolated_claude_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    """Provide an isolated CLAUDE_CONFIG_DIR and working directory.

    Every claude invocation in these tests targets config_dir (via the
    CLAUDE_CONFIG_DIR environment variable and the artifact_base_dir
    parameter) and runs from project_dir, so the real user configuration is
    never touched.

    Returns:
        Mapping with the isolated config_dir and project_dir paths.
    """
    config_dir = tmp_path / 'claude-config'
    project_dir = tmp_path / 'project'
    config_dir.mkdir()
    project_dir.mkdir()
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(config_dir))
    monkeypatch.setenv('DISABLE_AUTOUPDATER', '1')
    monkeypatch.setenv('CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', '1')
    monkeypatch.chdir(project_dir)
    return {'config_dir': config_dir, 'project_dir': project_dir}


def _read_global_config(config_dir: Path) -> dict[str, Any]:
    config_file = config_dir / '.claude.json'
    if not config_file.is_file():
        return {}
    return json.loads(config_file.read_text(encoding='utf-8'))


def _configure(servers: list[dict[str, Any]], config_dir: Path) -> dict[str, int]:
    """Run configure_all_mcp_servers() against the isolated config dir."""
    _, _, stats = setup_environment.configure_all_mcp_servers(
        servers,
        profile_mcp_config_path=None,
        artifact_base_dir=config_dir,
    )
    return stats


def test_real_binary_available_when_required() -> None:
    """CI must fail loudly when the binary is missing, never skip silently."""
    if _REQUIRE_REAL_BINARY:
        assert _CLAUDE_CMD is not None, (
            'CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1 but no claude binary was found'
        )


def test_stdio_add_matches_expected_entry(isolated_claude_env: dict[str, Path]) -> None:
    """The stored stdio entry equals the comparator's predicted entry."""
    server = {
        'name': 'e2e-stdio',
        'scope': 'user',
        'command': 'my-fake-server --port 1234',
        'env': ['FOO=bar', 'BAZ=${QUX}'],
    }
    _configure([server], isolated_claude_env['config_dir'])

    stored = _read_global_config(isolated_claude_env['config_dir'])['mcpServers']['e2e-stdio']
    expected = setup_environment._build_expected_mcp_entry(server)
    assert expected is not None
    assert setup_environment._mcp_entries_equal(stored, expected), (
        f'stored={stored!r} expected={expected!r}'
    )
    # The real CLI persisted the declared env verbatim, with the ${QUX}
    # placeholder stored unexpanded for Claude Code to expand at session start
    assert stored['env'] == {'FOO': 'bar', 'BAZ': '${QUX}'}


def test_http_add_matches_expected_entry(isolated_claude_env: dict[str, Path]) -> None:
    """The stored http entry (with header) equals the predicted entry."""
    server = {
        'name': 'e2e-http',
        'scope': 'user',
        'transport': 'http',
        'url': 'https://example.invalid/mcp',
        'header': 'Authorization: Bearer ${TOK}',
    }
    _configure([server], isolated_claude_env['config_dir'])

    stored = _read_global_config(isolated_claude_env['config_dir'])['mcpServers']['e2e-http']
    expected = setup_environment._build_expected_mcp_entry(server)
    assert expected is not None
    assert setup_environment._mcp_entries_equal(stored, expected), (
        f'stored={stored!r} expected={expected!r}'
    )


def test_rerun_skips_and_preserves_state(isolated_claude_env: dict[str, Path]) -> None:
    """An unchanged rerun touches neither credentials nor per-project state."""
    config_dir = isolated_claude_env['config_dir']
    servers: list[dict[str, Any]] = [
        {
            'name': 'e2e-http',
            'scope': 'user',
            'transport': 'http',
            'url': 'https://example.invalid/mcp',
        },
        {'name': 'e2e-stdio', 'scope': 'user', 'command': 'my-fake-server --flag'},
    ]
    first_stats = _configure(servers, config_dir)
    assert first_stats['unchanged_count'] == 0

    # Seed the states the remove/add cycle used to destroy: an OAuth
    # credential under the real derived key, and a per-project disabled list
    config = _read_global_config(config_dir)
    oauth_key = _derive_mcp_oauth_key('e2e-http', config['mcpServers']['e2e-http'])
    credentials = {
        'mcpOAuth': {
            oauth_key: {'serverName': 'e2e-http', 'accessToken': 'fake', 'expiresAt': 9999999999999},
        },
    }
    credentials_file = config_dir / '.credentials.json'
    credentials_file.write_text(json.dumps(credentials), encoding='utf-8')

    config['projects'] = {
        'C:/fake/other-project': {
            'mcpServers': {},
            'disabledMcpServers': ['e2e-http', 'e2e-stdio'],
            'disabledMcpjsonServers': [],
            'enabledMcpjsonServers': [],
            'mcpContextUris': [],
        },
    }
    config_file = config_dir / '.claude.json'
    config_file.write_text(json.dumps(config), encoding='utf-8')
    snapshot = config_file.read_bytes()

    second_stats = _configure(servers, config_dir)

    assert second_stats['unchanged_count'] == 2
    assert config_file.read_bytes() == snapshot, (
        'an unchanged rerun must not rewrite .claude.json at all'
    )
    surviving = json.loads(credentials_file.read_text(encoding='utf-8'))
    assert oauth_key in surviving['mcpOAuth'], (
        'the OAuth credential entry must survive an unchanged rerun'
    )


def test_changed_config_reconfigures(isolated_claude_env: dict[str, Path]) -> None:
    """A changed URL lands on disk; the old-config credential entry is cleared."""
    config_dir = isolated_claude_env['config_dir']
    original = {
        'name': 'e2e-http',
        'scope': 'user',
        'transport': 'http',
        'url': 'https://old.invalid/mcp',
    }
    _configure([original], config_dir)

    config = _read_global_config(config_dir)
    old_key = _derive_mcp_oauth_key('e2e-http', config['mcpServers']['e2e-http'])
    credentials_file = config_dir / '.credentials.json'
    credentials_file.write_text(json.dumps({
        'mcpOAuth': {
            old_key: {'serverName': 'e2e-http', 'accessToken': 'fake', 'expiresAt': 9999999999999},
        },
    }), encoding='utf-8')

    changed = dict(original, url='https://new.invalid/mcp')
    stats = _configure([changed], config_dir)

    assert stats['unchanged_count'] == 0
    stored = _read_global_config(config_dir)['mcpServers']['e2e-http']
    assert stored['url'] == 'https://new.invalid/mcp'
    # The CLI clears the old config's credential entry during removal; the
    # new config derives a different key anyway, so the old token could
    # never authenticate the new configuration. On macOS the CLI keeps MCP
    # OAuth credentials in the Keychain and may delete a plaintext
    # .credentials.json it encounters, so a missing file also proves the
    # old entry is gone
    surviving = json.loads(credentials_file.read_text(encoding='utf-8')) if credentials_file.is_file() else {}
    assert old_key not in surviving.get('mcpOAuth', {})


def test_stale_other_scope_entry_removed(isolated_claude_env: dict[str, Path]) -> None:
    """A same-name local-scope leftover is removed while the matching user entry stays."""
    config_dir = isolated_claude_env['config_dir']
    project_dir = isolated_claude_env['project_dir']
    server = {'name': 'e2e-stdio', 'scope': 'user', 'command': 'my-fake-server --flag'}
    _configure([server], config_dir)

    # Plant a stale local-scope entry through the real CLI, exactly as a
    # prior differently-scoped configuration would have left it
    assert _CLAUDE_CMD is not None
    result = subprocess.run(
        [str(_CLAUDE_CMD), 'mcp', 'add', '--scope', 'local', 'e2e-stdio', '--', 'other-cmd'],
        capture_output=True, text=True, cwd=project_dir,
        env={**os.environ, 'CLAUDE_CONFIG_DIR': str(config_dir)},
        check=False,
    )
    assert result.returncode == 0, result.stderr

    stats = _configure([server], config_dir)

    assert stats['unchanged_count'] == 1
    config = _read_global_config(config_dir)
    assert 'e2e-stdio' in config['mcpServers'], 'the matching user-scope entry must stay'
    projects = config.get('projects', {})
    for project_entry in projects.values():
        assert 'e2e-stdio' not in (project_entry.get('mcpServers') or {}), (
            'the stale local-scope entry must be removed'
        )


def test_project_scope_parity_and_skip(isolated_claude_env: dict[str, Path]) -> None:
    """Project-scope entries reach .mcp.json, match the prediction, and skip on rerun."""
    config_dir = isolated_claude_env['config_dir']
    project_dir = isolated_claude_env['project_dir']
    server = {
        'name': 'e2e-project',
        'scope': 'project',
        'command': 'my-fake-server --project',
    }
    first_stats = _configure([server], config_dir)
    assert first_stats['unchanged_count'] == 0

    mcp_json = project_dir / '.mcp.json'
    stored = json.loads(mcp_json.read_text(encoding='utf-8'))['mcpServers']['e2e-project']
    expected = setup_environment._build_expected_mcp_entry(server)
    assert expected is not None
    assert setup_environment._mcp_entries_equal(stored, expected), (
        f'stored={stored!r} expected={expected!r}'
    )

    snapshot = mcp_json.read_bytes()
    second_stats = _configure([server], config_dir)
    assert second_stats['unchanged_count'] == 1
    assert mcp_json.read_bytes() == snapshot
