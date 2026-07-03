"""E2E tests for settings routing in non-command-names (non-isolated) mode.

When ``command-names`` is absent, the toolbox writes to the shared
``~/.claude/settings.json`` in two passes:

- Step 14 (``write_user_settings``) deep-merges the raw ``user-settings``
  section (model, permissions, env, and every other settings.json key) into
  ``~/.claude/settings.json`` with universal array union and RFC 7396
  null-as-delete.
- Step 18 (``write_profile_settings_to_settings``) applies the profile-owned
  delta -- only ``statusLine`` and ``hooks`` -- into the same file via the
  same deep-merge helper.

Both passes preserve every key outside their own delta, so the two
contributions coexist in one file. The profile-owned key set is exactly
``{'statusLine', 'hooks'}`` because those two keys require dedicated write
logic (path resolution and per-event processing) and are rejected inside
``user-settings``; every other settings.json key is expressed directly in
``user-settings``.

Test coverage:
- ``_build_profile_settings`` statusLine/hooks behavior, including explicit
  nulls and the empty/absent cases.
- Step 18 writes ONLY the statusLine/hooks delta and preserves unrelated
  on-disk keys; top-level null deletes statusLine/hooks.
- Step 14 user-settings deep-merge: array union, RFC 7396 null-as-delete,
  and env sub-dict merge.
- ``golden_config_no_command_names.yaml`` end-to-end: user-settings content
  plus statusLine and hooks all land in ``~/.claude/settings.json``.
- Auto-update Target ``user-settings.env`` survival across the Step 14 then
  Step 18 ordering.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.setup_environment import PROFILE_OWNED_KEYS
from scripts.setup_environment import _build_profile_settings
from scripts.setup_environment import write_profile_settings_to_settings
from scripts.setup_environment import write_user_settings

# ---------------------------------------------------------------------------
# Test Class 1: _build_profile_settings statusLine/hooks Behavior
# ---------------------------------------------------------------------------


class TestBuildProfileSettings:
    """Verify the pure builder emits only the two profile-owned keys.

    ``_build_profile_settings`` is I/O-free. It maps a per-key
    ``profile_config`` dict (camelCase names) to a settings delta, handling
    exactly ``statusLine`` and ``hooks``. Dict membership encodes the YAML
    declaration state: absent keys are omitted, keys present with ``None``
    propagate as ``None`` for downstream null-as-delete.
    """

    def test_profile_owned_keys_is_status_line_and_hooks(self) -> None:
        """PROFILE_OWNED_KEYS is exactly {statusLine, hooks}."""
        assert frozenset({'statusLine', 'hooks'}) == PROFILE_OWNED_KEYS

    def test_empty_profile_config_yields_empty_delta(self, tmp_path: Path) -> None:
        """No profile-owned keys declared -> empty delta."""
        assert _build_profile_settings({}, tmp_path / 'hooks') == {}

    def test_non_profile_keys_are_ignored(self, tmp_path: Path) -> None:
        """Keys other than statusLine/hooks are not emitted by the builder."""
        delta = _build_profile_settings(
            {'model': 'sonnet', 'permissions': {'allow': ['Read']}, 'env': {'A': 'b'}},
            tmp_path / 'hooks',
        )
        assert delta == {}

    def test_status_line_built_into_command(self, tmp_path: Path) -> None:
        """A statusLine file reference becomes a command-string entry."""
        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()
        delta = _build_profile_settings(
            {'statusLine': {'file': 'status.py', 'padding': 0}},
            hooks_dir,
        )
        assert set(delta.keys()) == {'statusLine'}
        assert delta['statusLine']['type'] == 'command'
        assert 'uv run' in delta['statusLine']['command']
        assert (hooks_dir / 'status.py').as_posix() in delta['statusLine']['command']
        assert delta['statusLine']['padding'] == 0

    def test_hooks_built_into_event_structure(self, tmp_path: Path) -> None:
        """A hooks config with events becomes an event-keyed structure."""
        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()
        delta = _build_profile_settings(
            {
                'hooks': {
                    'events': [
                        {
                            'event': 'PreToolUse', 'matcher': 'Bash',
                            'type': 'command', 'command': 'a.sh',
                        },
                    ],
                },
            },
            hooks_dir,
        )
        assert set(delta.keys()) == {'hooks'}
        assert 'PreToolUse' in delta['hooks']

    def test_explicit_null_status_line_propagates(self, tmp_path: Path) -> None:
        """statusLine present with None propagates as None for null-as-delete."""
        delta = _build_profile_settings({'statusLine': None}, tmp_path / 'hooks')
        assert delta == {'statusLine': None}

    def test_explicit_null_hooks_propagates(self, tmp_path: Path) -> None:
        """hooks present with None propagates as None for null-as-delete."""
        delta = _build_profile_settings({'hooks': None}, tmp_path / 'hooks')
        assert delta == {'hooks': None}

    def test_empty_hooks_dict_omitted(self, tmp_path: Path) -> None:
        """An empty hooks dict (no events) is omitted from the delta."""
        delta = _build_profile_settings({'hooks': {}}, tmp_path / 'hooks')
        assert delta == {}

    def test_both_keys_together(self, tmp_path: Path) -> None:
        """statusLine and hooks together yield both entries."""
        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()
        delta = _build_profile_settings(
            {
                'statusLine': {'file': 'status.py'},
                'hooks': {
                    'events': [
                        {
                            'event': 'PreToolUse', 'matcher': 'Bash',
                            'type': 'command', 'command': 'a.sh',
                        },
                    ],
                },
            },
            hooks_dir,
        )
        assert set(delta.keys()) == {'statusLine', 'hooks'}


# ---------------------------------------------------------------------------
# Test Class 2: Step 18 Writes ONLY the statusLine/hooks Delta
# ---------------------------------------------------------------------------


class TestProfileDeltaWriter:
    """Filesystem tests of write_profile_settings_to_settings().

    Step 18 deep-merges the statusLine/hooks delta into
    ~/.claude/settings.json via the shared _write_merged_json() helper:
    unrelated keys are preserved, nested dicts merge, every array unions,
    and RFC 7396 null deletes keys.
    """

    def test_empty_delta_does_not_create_file(self, tmp_path: Path) -> None:
        """Empty delta -> no file created."""
        write_profile_settings_to_settings({}, tmp_path)
        assert not (tmp_path / 'settings.json').exists()

    def test_empty_delta_does_not_modify_existing(self, tmp_path: Path) -> None:
        """Empty delta -> existing settings.json unchanged."""
        settings_file = tmp_path / 'settings.json'
        original = {'language': 'english', 'model': 'sonnet'}
        settings_file.write_text(json.dumps(original), encoding='utf-8')

        write_profile_settings_to_settings({}, tmp_path)

        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert content == original

    def test_only_status_line_and_hooks_written(self, tmp_path: Path) -> None:
        """The written keys are exactly the profile-owned delta keys."""
        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()
        delta = _build_profile_settings(
            {
                'statusLine': {'file': 'status.py'},
                'hooks': {
                    'events': [
                        {
                            'event': 'PreToolUse', 'matcher': 'Bash',
                            'type': 'command', 'command': 'a.sh',
                        },
                    ],
                },
            },
            hooks_dir,
        )
        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        assert set(content.keys()) == {'statusLine', 'hooks'}

    def test_unrelated_keys_preserved(self, tmp_path: Path) -> None:
        """User-settings keys written by Step 14 survive the Step 18 delta write.

        Step 14 leaves model/permissions/env/language in settings.json. The
        Step 18 profile delta only carries statusLine, so every user-settings
        key must remain intact.
        """
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'model': 'sonnet',
            'permissions': {'allow': ['Read'], 'deny': ['Bash(rm -rf)']},
            'env': {'FOO': 'bar'},
            'language': 'english',
        }), encoding='utf-8')

        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()
        delta = _build_profile_settings({'statusLine': {'file': 'status.py'}}, hooks_dir)
        write_profile_settings_to_settings(delta, tmp_path)

        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert content['model'] == 'sonnet'
        assert content['permissions'] == {'allow': ['Read'], 'deny': ['Bash(rm -rf)']}
        assert content['env'] == {'FOO': 'bar'}
        assert content['language'] == 'english'
        assert content['statusLine']['type'] == 'command'

    def test_top_level_null_status_line_deletes_key(self, tmp_path: Path) -> None:
        """Top-level None for statusLine deletes only that key."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'statusLine': {'type': 'command', 'command': 'x'},
            'model': 'sonnet',
        }), encoding='utf-8')

        write_profile_settings_to_settings({'statusLine': None}, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert 'statusLine' not in content
        assert content['model'] == 'sonnet'

    def test_top_level_null_hooks_deletes_key(self, tmp_path: Path) -> None:
        """Top-level None for hooks deletes only that key."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'hooks': {'PreToolUse': [{'matcher': '', 'hooks': []}]},
            'model': 'sonnet',
        }), encoding='utf-8')

        write_profile_settings_to_settings({'hooks': None}, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert 'hooks' not in content
        assert content['model'] == 'sonnet'

    def test_explicit_null_hooks_removes_stale_block(self, tmp_path: Path) -> None:
        """A YAML root null removes a hooks block written by an earlier run."""
        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()
        delta_a = _build_profile_settings(
            {
                'hooks': {
                    'events': [
                        {
                            'event': 'PreToolUse', 'matcher': 'Bash',
                            'type': 'command', 'command': 'a.sh',
                        },
                    ],
                },
            },
            hooks_dir,
        )
        write_profile_settings_to_settings(delta_a, tmp_path)
        # A later YAML with hooks: null -> delta {'hooks': None}
        write_profile_settings_to_settings({'hooks': None}, tmp_path)
        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        assert 'hooks' not in content

    def test_hooks_event_lists_union_across_runs(self, tmp_path: Path) -> None:
        """Two Step 18 writes with different hook events both survive on disk."""
        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()
        delta_a = _build_profile_settings(
            {
                'hooks': {
                    'events': [
                        {
                            'event': 'PreToolUse', 'matcher': 'Bash',
                            'type': 'command', 'command': 'a.sh',
                        },
                    ],
                },
            },
            hooks_dir,
        )
        write_profile_settings_to_settings(delta_a, tmp_path)
        delta_b = _build_profile_settings(
            {
                'hooks': {
                    'events': [
                        {
                            'event': 'PostToolUse', 'matcher': 'Write',
                            'type': 'command', 'command': 'b.sh',
                        },
                    ],
                },
            },
            hooks_dir,
        )
        write_profile_settings_to_settings(delta_b, tmp_path)
        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        assert 'PreToolUse' in content['hooks']
        assert 'PostToolUse' in content['hooks']


# ---------------------------------------------------------------------------
# Test Class 3: Step 14 user-settings Deep-Merge Into Shared settings.json
# ---------------------------------------------------------------------------


class TestUserSettingsDeepMerge:
    """Verify write_user_settings() deep-merge semantics on ~/.claude/settings.json.

    Step 14 deep-merges the raw user-settings section into the shared file:
    every array unions with structural dedupe, nested dicts merge, RFC 7396
    null deletes keys, and the env sub-dict merges key-by-key.
    """

    def test_initial_write_creates_file(self, tmp_path: Path) -> None:
        """First write against an empty directory creates settings.json."""
        write_user_settings({'model': 'sonnet', 'theme': 'dark'}, tmp_path)
        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        assert content == {'model': 'sonnet', 'theme': 'dark'}

    def test_unrelated_keys_preserved(self, tmp_path: Path) -> None:
        """Keys already on disk and outside the delta are preserved."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({'cleanupPeriodDays': 30}), encoding='utf-8')
        write_user_settings({'model': 'sonnet'}, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert content['cleanupPeriodDays'] == 30
        assert content['model'] == 'sonnet'

    def test_permissions_allow_unions_across_runs(self, tmp_path: Path) -> None:
        """permissions.allow accumulates across successive user-settings writes."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'permissions': {'allow': ['Read'], 'deny': ['Bash(sudo *)']},
        }), encoding='utf-8')

        write_user_settings(
            {'permissions': {'allow': ['Write', 'Edit']}}, tmp_path,
        )
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        # allow unioned, deny preserved intact
        assert set(content['permissions']['allow']) == {'Read', 'Write', 'Edit'}
        assert content['permissions']['deny'] == ['Bash(sudo *)']

    def test_permissions_deny_preserved_when_only_allow_declared(self, tmp_path: Path) -> None:
        """A narrower permissions dict must not destroy existing deny rules."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'permissions': {
                'allow': ['Read'],
                'deny': ['Bash(rm -rf *)', 'Bash(curl *)'],
                'ask': ['Edit'],
            },
        }), encoding='utf-8')

        write_user_settings({'permissions': {'allow': ['Grep']}}, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert set(content['permissions']['allow']) == {'Read', 'Grep'}
        assert content['permissions']['deny'] == ['Bash(rm -rf *)', 'Bash(curl *)']
        assert content['permissions']['ask'] == ['Edit']

    def test_env_sub_dict_merges_key_by_key(self, tmp_path: Path) -> None:
        """The env sub-dict merges: existing keys survive, new keys are added."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'env': {'DISABLE_AUTOUPDATER': '1', 'KEEP_ME': 'preserved'},
        }), encoding='utf-8')

        write_user_settings({'env': {'FOO': 'bar'}}, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert content['env']['DISABLE_AUTOUPDATER'] == '1'
        assert content['env']['KEEP_ME'] == 'preserved'
        assert content['env']['FOO'] == 'bar'

    def test_top_level_null_deletes_key(self, tmp_path: Path) -> None:
        """RFC 7396: a top-level null deletes the on-disk key."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'model': 'sonnet', 'theme': 'dark',
        }), encoding='utf-8')

        write_user_settings({'model': None}, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert 'model' not in content
        assert content['theme'] == 'dark'

    def test_nested_null_deletes_env_sub_key(self, tmp_path: Path) -> None:
        """RFC 7396: a nested null deletes just that env sub-key."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'env': {'STALE_VAR': 'x', 'KEEP_ME': 'y'},
        }), encoding='utf-8')

        write_user_settings({'env': {'STALE_VAR': None}}, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert 'STALE_VAR' not in content['env']
        assert content['env']['KEEP_ME'] == 'y'


# ---------------------------------------------------------------------------
# Test Class 4: golden_config_no_command_names End-to-End
# ---------------------------------------------------------------------------


@pytest.fixture
def golden_config_no_command_names() -> dict[str, Any]:
    """Load the no-command-names variant of golden_config.yaml."""
    config_path = Path(__file__).parent / 'golden_config_no_command_names.yaml'
    with config_path.open('r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    result: dict[str, Any] = config
    return result


class TestGoldenConfigNoCommandNames:
    """End-to-end integration test using golden_config_no_command_names.yaml.

    Reproduces the Step 14 then Step 18 ordering that main() applies in
    non-isolated mode and asserts that both the user-settings content and the
    profile-owned statusLine/hooks entries coexist in ~/.claude/settings.json,
    with no config.json written anywhere.
    """

    def test_no_command_names_declared(
        self,
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """The fixture intentionally omits command-names (non-isolated mode)."""
        assert 'command-names' not in golden_config_no_command_names

    def test_settings_json_content_key_lives_in_user_settings(
        self,
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """settings.json content keys are declared inside user-settings, not at root."""
        cfg = golden_config_no_command_names
        user_settings = cfg['user-settings']
        assert user_settings.get('model') == 'sonnet'
        assert 'permissions' in user_settings
        assert 'env' in user_settings
        assert user_settings.get('alwaysThinkingEnabled') is True
        assert user_settings.get('effortLevel') == 'low'
        # The two profile-owned keys remain at the YAML root (dedicated write logic)
        assert 'status-line' in cfg
        assert 'hooks' in cfg
        # Removed root keys must not resurface at the YAML root
        for stale_root_key in (
            'model', 'permissions', 'env-variables', 'attribution',
            'always-thinking-enabled', 'effort-level', 'company-announcements',
        ):
            assert stale_root_key not in cfg

    def test_no_profile_scoped_mcp(
        self,
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """No mcp-server uses scope 'profile' (which requires command-names)."""
        for server in golden_config_no_command_names.get('mcp-servers', []):
            scope = server.get('scope')
            if isinstance(scope, str):
                assert scope != 'profile'
            elif isinstance(scope, list):
                assert 'profile' not in scope

    def test_user_settings_and_profile_keys_coexist_in_settings_json(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """Step 14 then Step 18 leave both contributions in settings.json.

        The user-settings content (model, permissions, env, ...) is written by
        write_user_settings, then the statusLine/hooks delta is written by
        write_profile_settings_to_settings. Both survive in the same file, and
        no config.json is created in non-isolated mode.
        """
        claude_dir = e2e_isolated_home['claude_dir']
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        cfg = golden_config_no_command_names

        # Step 14: write user-settings section
        write_user_settings(cfg['user-settings'], claude_dir)

        # Step 18: build and write the profile-owned delta (statusLine + hooks)
        profile_config = {
            camel_key: cfg[yaml_key]
            for yaml_key, camel_key in {
                'status-line': 'statusLine',
                'hooks': 'hooks',
            }.items()
            if yaml_key in cfg
        }
        delta = _build_profile_settings(profile_config, hooks_dir)
        write_profile_settings_to_settings(delta, claude_dir)

        settings_path = claude_dir / 'settings.json'
        assert settings_path.exists()
        content = json.loads(settings_path.read_text(encoding='utf-8'))

        # user-settings content present
        assert content['model'] == 'sonnet'
        assert content['permissions']['defaultMode'] == 'default'
        assert content['alwaysThinkingEnabled'] is True
        assert content['effortLevel'] == 'low'
        assert content['companyAnnouncements'] == [
            'Welcome to E2E Testing Environment',
            'This is a test announcement for validation',
        ]
        assert content['attribution'] == {
            'commit': 'E2E Test Attribution for Commits',
            'pr': 'E2E Test Attribution for Pull Requests',
        }
        # profile-owned keys present
        assert content['statusLine']['type'] == 'command'
        assert 'PostToolUse' in content['hooks']

        # Non-isolated mode: NO config.json anywhere
        assert not (claude_dir / 'config.json').exists()

    def test_env_null_entry_deletes_stale_value(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """The golden config's null env entry deletes the stale settings.json value.

        Base-mode null-as-delete: a per-key env null in user-settings flows
        through the deep-merge writer and removes the key, while active values
        are set as strings and the literal string 'None' never appears.
        """
        claude_dir = e2e_isolated_home['claude_dir']

        cfg = golden_config_no_command_names
        env_section = cfg['user-settings']['env']
        assert env_section.get('E2E_DELETE_VAR', '') is None, (
            'Golden no-command-names config must declare user-settings.env.E2E_DELETE_VAR: null'
        )

        # Pre-seed a stale value as if a prior run had set the variable
        settings_path = claude_dir / 'settings.json'
        settings_path.write_text(
            json.dumps({'env': {'E2E_DELETE_VAR': 'stale_value'}}),
            encoding='utf-8',
        )

        write_user_settings(cfg['user-settings'], claude_dir)

        content = json.loads(settings_path.read_text(encoding='utf-8'))
        env_block = content['env']
        assert 'E2E_DELETE_VAR' not in env_block
        assert env_block.get('E2E_TEST_VAR') == 'test_value'
        assert env_block.get('E2E_INT_VAR') == '42'
        assert 'None' not in env_block.values()

    def test_status_line_absolute_path_in_settings(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """statusLine.command has an absolute POSIX path under ~/.claude/hooks/."""
        claude_dir = e2e_isolated_home['claude_dir']
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        cfg = golden_config_no_command_names

        delta = _build_profile_settings(
            {'statusLine': cfg.get('status-line')},
            hooks_dir,
        )
        write_profile_settings_to_settings(delta, claude_dir)

        settings_path = claude_dir / 'settings.json'
        content = json.loads(settings_path.read_text(encoding='utf-8'))
        sl = content['statusLine']
        assert sl['type'] == 'command'
        expected_path = (hooks_dir / 'e2e_statusline.py').as_posix()
        assert expected_path in sl['command']
        # Python script -> uv run prefix
        assert 'uv run' in sl['command']
        # Config file embedded in the command string
        expected_cfg = (hooks_dir / 'e2e-statusline-config.yaml').as_posix()
        assert expected_cfg in sl['command']


# ---------------------------------------------------------------------------
# Test Class 5: Auto-Update Target user-settings.env Survival
# ---------------------------------------------------------------------------


class TestAutoUpdateEnvSurvival:
    """Verify the auto-update user-settings.env injection survives Step 14 then Step 18.

    When version pinning is active, apply_auto_update_settings() injects
    DISABLE_AUTOUPDATER into user_settings.env (one of its three targets).
    Step 14 (write_user_settings) writes that entry to settings.json.env.
    The subsequent Step 18 profile-settings write carries only statusLine and
    hooks, so it must not touch the env block that Step 14 wrote.
    """

    def test_disable_autoupdater_survives_step14_then_step18(self, tmp_path: Path) -> None:
        """DISABLE_AUTOUPDATER written by Step 14 survives the Step 18 delta write."""
        claude_dir = tmp_path
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir()

        # Step 14: user-settings carrying the injected env target
        write_user_settings(
            {'model': 'sonnet', 'env': {'DISABLE_AUTOUPDATER': '1'}},
            claude_dir,
        )

        # Step 18: profile delta has statusLine only (no env)
        delta = _build_profile_settings({'statusLine': {'file': 'status.py'}}, hooks_dir)
        assert 'env' not in delta
        write_profile_settings_to_settings(delta, claude_dir)

        content = json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))
        assert content['env']['DISABLE_AUTOUPDATER'] == '1'
        assert content['model'] == 'sonnet'
        assert content['statusLine']['type'] == 'command'

    def test_ide_and_auto_update_env_targets_both_survive(self, tmp_path: Path) -> None:
        """Both env auto-control targets written by Step 14 survive Step 18."""
        claude_dir = tmp_path
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir()

        write_user_settings(
            {
                'env': {
                    'DISABLE_AUTOUPDATER': '1',
                    'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL': 'true',
                },
            },
            claude_dir,
        )

        delta = _build_profile_settings(
            {
                'hooks': {
                    'events': [
                        {
                            'event': 'PreToolUse', 'matcher': 'Bash',
                            'type': 'command', 'command': 'a.sh',
                        },
                    ],
                },
            },
            hooks_dir,
        )
        write_profile_settings_to_settings(delta, claude_dir)

        content = json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))
        assert content['env']['DISABLE_AUTOUPDATER'] == '1'
        assert content['env']['CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL'] == 'true'
        assert 'PreToolUse' in content['hooks']
