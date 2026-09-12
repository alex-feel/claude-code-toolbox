"""E2E tests for the ``env`` key of the shared ``~/.claude/settings.json``.

In non-isolated mode (no ``command-names``) the ``user-settings.env`` block
is deep-merged into the shared ``~/.claude/settings.json`` by
``write_user_settings`` (Step 14). Claude Code copies every member of that
block into the process environment at session start, and a JSON ``null``
there does not unset a variable: it arrives as the string ``'null'``, so a
leaked ``ANTHROPIC_AUTH_TOKEN: null`` sends the literal token ``null`` with
every request. A YAML ``null`` must therefore end as ABSENCE on disk,
whatever the file held before the run:

- no ``settings.json`` at all (first run on a machine)
- a ``settings.json`` without an ``env`` block
- an ``env`` block that is not an object
- an ``env`` block already holding the variable (stale value)
- an ``env`` block holding other variables (preserved)

The same guarantee is checked for ``write_global_config`` (which shares the
merge helper) and for the ``inherit`` composition layer, whose child
``null`` must reach the writer as a deletion even when the parent declared
a value for the same variable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.setup_environment import resolve_config_inheritance
from scripts.setup_environment import write_global_config
from scripts.setup_environment import write_user_settings
from tests.e2e.validators import validate_settings_json

GATEWAY_URL = 'https://gateway.example.test'

# The corporate gateway shape: a rotating apiKeyHelper value must not be
# shadowed by a static token, so the token is declared null.
GATEWAY_USER_SETTINGS: dict[str, Any] = {
    'apiKeyHelper': 'uv run --no-project --python 3.12 ~/.claude/scripts/username.py',
    'env': {
        'ANTHROPIC_AUTH_TOKEN': None,
        'ANTHROPIC_BASE_URL': GATEWAY_URL,
        'CLAUDE_CODE_API_KEY_HELPER_TTL_MS': '3600000',
    },
}


@pytest.fixture
def golden_config_no_command_names() -> dict[str, Any]:
    """Load the non-isolated golden config (declares user-settings.env.E2E_DELETE_VAR: null)."""
    config_path = Path(__file__).parent / 'golden_config_no_command_names.yaml'
    with config_path.open('r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    result: dict[str, Any] = config
    return result


def _read_settings(claude_dir: Path) -> tuple[dict[str, Any], str]:
    """Return the parsed settings.json and its raw text."""
    text = (claude_dir / 'settings.json').read_text(encoding='utf-8')
    data: dict[str, Any] = json.loads(text)
    return data, text


def _seed_settings(claude_dir: Path, content: dict[str, Any]) -> None:
    """Write a settings.json as if a prior run or the CLI had left it behind."""
    (claude_dir / 'settings.json').write_text(json.dumps(content), encoding='utf-8')


class TestEnvNullNeverWrittenToSettingsJson:
    """A null env member never reaches ~/.claude/settings.json as a JSON null."""

    def test_missing_settings_file(self, e2e_isolated_home: dict[str, Path]) -> None:
        """First run on a machine: the file is created without the null member."""
        claude_dir = e2e_isolated_home['claude_dir']
        assert not (claude_dir / 'settings.json').exists()

        assert write_user_settings(GATEWAY_USER_SETTINGS, claude_dir)

        data, text = _read_settings(claude_dir)
        assert 'ANTHROPIC_AUTH_TOKEN' not in data['env']
        assert data['env']['ANTHROPIC_BASE_URL'] == GATEWAY_URL
        assert data['env']['CLAUDE_CODE_API_KEY_HELPER_TTL_MS'] == '3600000'
        assert 'null' not in text

    def test_settings_file_without_env_block(self, e2e_isolated_home: dict[str, Path]) -> None:
        """An existing file with no env block gains one without the null member."""
        claude_dir = e2e_isolated_home['claude_dir']
        _seed_settings(claude_dir, {'model': 'sonnet'})

        assert write_user_settings(GATEWAY_USER_SETTINGS, claude_dir)

        data, text = _read_settings(claude_dir)
        assert data['model'] == 'sonnet'
        assert 'ANTHROPIC_AUTH_TOKEN' not in data['env']
        assert data['env']['ANTHROPIC_BASE_URL'] == GATEWAY_URL
        assert 'null' not in text

    def test_non_object_env_block_is_replaced(self, e2e_isolated_home: dict[str, Path]) -> None:
        """A corrupt non-object env block is replaced by a clean object (RFC 7396)."""
        claude_dir = e2e_isolated_home['claude_dir']
        _seed_settings(claude_dir, {'env': 'corrupt'})

        assert write_user_settings(GATEWAY_USER_SETTINGS, claude_dir)

        data, text = _read_settings(claude_dir)
        assert data['env'] == {
            'ANTHROPIC_BASE_URL': GATEWAY_URL,
            'CLAUDE_CODE_API_KEY_HELPER_TTL_MS': '3600000',
        }
        assert 'null' not in text

    def test_stale_value_deleted_and_siblings_preserved(self, e2e_isolated_home: dict[str, Path]) -> None:
        """A stale token from a prior run is deleted; unrelated members survive."""
        claude_dir = e2e_isolated_home['claude_dir']
        _seed_settings(claude_dir, {
            'env': {'ANTHROPIC_AUTH_TOKEN': 'stale-static-token', 'OTHER_VAR': 'keep'},
        })

        assert write_user_settings(GATEWAY_USER_SETTINGS, claude_dir)

        data, text = _read_settings(claude_dir)
        assert 'ANTHROPIC_AUTH_TOKEN' not in data['env']
        assert data['env']['OTHER_VAR'] == 'keep'
        assert data['env']['ANTHROPIC_BASE_URL'] == GATEWAY_URL
        assert 'null' not in text

    def test_rerun_is_idempotent(self, e2e_isolated_home: dict[str, Path]) -> None:
        """Running the same settings twice yields the same file, still without nulls."""
        claude_dir = e2e_isolated_home['claude_dir']

        assert write_user_settings(GATEWAY_USER_SETTINGS, claude_dir)
        first, _ = _read_settings(claude_dir)
        assert write_user_settings(GATEWAY_USER_SETTINGS, claude_dir)
        second, text = _read_settings(claude_dir)

        assert first == second
        assert 'ANTHROPIC_AUTH_TOKEN' not in second['env']
        assert 'null' not in text

    def test_env_declared_only_with_nulls_yields_empty_block(self, e2e_isolated_home: dict[str, Path]) -> None:
        """An env block made only of deletions lands as an empty object on a fresh file."""
        claude_dir = e2e_isolated_home['claude_dir']

        assert write_user_settings({'env': {'ANTHROPIC_AUTH_TOKEN': None}}, claude_dir)

        data, text = _read_settings(claude_dir)
        assert data['env'] == {}
        assert 'null' not in text

    def test_golden_config_env_on_fresh_home_passes_validator(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """The golden null entry is absent on a fresh home and the validator agrees."""
        claude_dir = e2e_isolated_home['claude_dir']
        cfg = golden_config_no_command_names
        assert cfg['user-settings']['env'].get('E2E_DELETE_VAR', '') is None

        assert write_user_settings(cfg['user-settings'], claude_dir)

        errors = validate_settings_json(claude_dir / 'settings.json', cfg)
        assert not errors, '\n'.join(errors)
        data, text = _read_settings(claude_dir)
        assert 'E2E_DELETE_VAR' not in data['env']
        assert data['env']['E2E_TEST_VAR'] == 'test_value'
        assert 'null' not in text


class TestGlobalConfigNestedNullNeverWritten:
    """The ~/.claude.json writer shares the merge helper and the same guarantee."""

    def test_nested_null_absent_from_fresh_claude_json(self, e2e_isolated_home: dict[str, Path]) -> None:
        """A nested null inside a new section is dropped, never written as JSON null."""
        home = e2e_isolated_home['home']

        assert write_global_config({'section': {'gone': None, 'kept': True}, 'top': None})

        text = (home / '.claude.json').read_text(encoding='utf-8')
        data = json.loads(text)
        assert data == {'section': {'kept': True}}
        assert 'null' not in text


class TestInheritedNullReachesSettingsJson:
    """A child config's null deletes a value the parent config wrote in an earlier run."""

    def test_child_null_deletes_value_parent_run_wrote(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Composition carries the child's deletion request to the writer.

        The parent declares a static token; the child, which inherits it,
        declares the token null. Applying the resolved child config must
        delete the token the parent's earlier run wrote, exactly as running
        the parent and then the child would.
        """
        claude_dir = e2e_isolated_home['claude_dir']
        parent_path = tmp_path / 'corp.yaml'
        child_path = tmp_path / 'team.yaml'
        parent_cfg: dict[str, Any] = {
            'name': 'corp',
            'user-settings': {'env': {'ANTHROPIC_AUTH_TOKEN': 'corp-token', 'CORP_VAR': '1'}},
        }
        child_cfg: dict[str, Any] = {
            'name': 'team',
            'inherit': str(parent_path),
            'merge-keys': ['user-settings'],
            'user-settings': {'env': {'ANTHROPIC_AUTH_TOKEN': None, 'TEAM_VAR': '2'}},
        }
        parent_path.write_text(yaml.safe_dump(parent_cfg), encoding='utf-8')
        child_path.write_text(yaml.safe_dump(child_cfg), encoding='utf-8')

        # Earlier run of the parent config wrote the static token.
        assert write_user_settings(parent_cfg['user-settings'], claude_dir)
        before, _ = _read_settings(claude_dir)
        assert before['env']['ANTHROPIC_AUTH_TOKEN'] == 'corp-token'

        # The team config run: resolve inheritance, then apply to disk.
        resolved, _ = resolve_config_inheritance(child_cfg, str(child_path))
        assert resolved['user-settings']['env']['ANTHROPIC_AUTH_TOKEN'] is None
        assert write_user_settings(resolved['user-settings'], claude_dir)

        data, text = _read_settings(claude_dir)
        assert 'ANTHROPIC_AUTH_TOKEN' not in data['env']
        assert data['env']['CORP_VAR'] == '1'
        assert data['env']['TEAM_VAR'] == '2'
        assert 'null' not in text
