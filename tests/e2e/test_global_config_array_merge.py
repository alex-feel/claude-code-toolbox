"""E2E tests for how global-config arrays merge at each layer.

Two layers touch a global-config array on its way into a .claude.json:

- The inherit layer composes the YAML chain. With global-config listed in
  merge-keys, objects merge member by member while a child array replaces
  the parent's at every depth; without merge-keys the child's section
  replaces the parent's whole.
- The Step 15 writer merges the resolved section into the one
  .claude.json the run owns (~/.claude.json for a base run, the
  profile's own file for an isolated run) and unions every array at
  every depth with the array that file already holds (existing elements
  first, duplicates dropped), because Claude Code keeps arrays of its own
  there. A YAML array therefore only adds elements; a YAML null deletes
  the whole key. An isolated run never writes the base file.

The inherit layer composes user-settings differently: its
permissions.allow/deny/ask arrays are unioned and every other array is
replaced by the child's. On disk the two modes differ as well: a base run
unions user-settings arrays with ~/.claude/settings.json the same way the
global-config writer does, while an isolated run rebuilds the profile's
config.json from the resolved configuration on every run, so the arrays
there are exactly the resolved ones.

Every test runs main() against YAML files on disk, so loading, inheritance
resolution, validation and the writers run for real; only the steps that
never touch these files (Claude Code installation, dependencies,
downloads, MCP registration, OS environment writes, launcher and command
registration) are stubbed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

from scripts import setup_environment
from tests.conftest import empty_mcp_stats
from tests.e2e.validators import validate_json_arrays

PROFILE_NAME = 'e2e-arrays'


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    """Write a configuration dict as a YAML file and return its path."""
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
    return path


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Seed a JSON file the way Claude Code leaves it before setup runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""
    data: dict[str, Any] = json.loads(path.read_text(encoding='utf-8'))
    return data


def _run_setup(config_path: Path) -> None:
    """Run main() for one YAML file on disk with the unrelated steps stubbed."""
    profile_dir = config_path.parent / 'unused-launcher'
    passthrough_find = setup_environment.find_command

    def find_with_claude(cmd: str) -> str | None:
        return '/usr/bin/claude' if cmd == 'claude' else passthrough_find(cmd)

    with (
        patch('scripts.setup_environment.find_command', side_effect=find_with_claude),
        patch('scripts.setup_environment.install_claude', return_value=True),
        patch('scripts.setup_environment.install_dependencies', return_value=[]),
        patch('scripts.setup_environment.process_resources', return_value=True),
        patch('scripts.setup_environment.process_skills', return_value=True),
        patch('scripts.setup_environment.configure_all_mcp_servers',
              return_value=(True, [], empty_mcp_stats())),
        patch('scripts.setup_environment.set_all_os_env_variables', return_value=True),
        patch('scripts.setup_environment.create_launcher_script',
              return_value=(profile_dir / 'launch.sh', profile_dir / 'launch.sh')),
        patch('scripts.setup_environment.register_global_command', return_value=True),
        patch('scripts.setup_environment.is_admin', return_value=True),
        patch('sys.argv', ['setup_environment.py', str(config_path), '--yes', '--skip-install']),
    ):
        setup_environment.main()


class TestWriterUnionsArraysWithClaudeJson:
    """Step 15 unions a YAML global-config array with the array on disk."""

    def test_base_run_appends_yaml_elements_after_existing_ones(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Existing elements stay first, new ones follow, duplicates collapse, siblings survive."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        _write_json(claude_json, {
            'enabledMcpjsonServers': ['cli-server'],
            'customApiKeyResponses': {
                'approved': ['cli-key'],
                'rejected': ['cli-rejected-key'],
            },
        })
        config_path = _write_yaml(tmp_path / 'arrays.yaml', {
            'name': 'Global Config Arrays',
            'global-config': {
                'enabledMcpjsonServers': ['yaml-server', 'cli-server'],
                'customApiKeyResponses': {'approved': ['cli-key', 'yaml-key']},
            },
        })

        _run_setup(config_path)

        errors = validate_json_arrays(claude_json, {
            ('enabledMcpjsonServers',): ['cli-server', 'yaml-server'],
            ('customApiKeyResponses', 'approved'): ['cli-key', 'yaml-key'],
            ('customApiKeyResponses', 'rejected'): ['cli-rejected-key'],
        })
        assert not errors, '\n'.join(errors)

    def test_base_run_never_removes_elements_the_yaml_omits(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """A shorter YAML array leaves the elements already in the file in place."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        _write_json(claude_json, {'enabledMcpjsonServers': ['first', 'second', 'third']})
        config_path = _write_yaml(tmp_path / 'shorter.yaml', {
            'name': 'Shorter Array',
            'global-config': {'enabledMcpjsonServers': ['second']},
        })

        _run_setup(config_path)

        errors = validate_json_arrays(claude_json, {
            ('enabledMcpjsonServers',): ['first', 'second', 'third'],
        })
        assert not errors, '\n'.join(errors)

    def test_base_run_null_deletes_the_whole_array(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """A YAML null removes the array key while the rest of the file stays."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        _write_json(claude_json, {
            'enabledMcpjsonServers': ['first', 'second'],
            'editorMode': 'vim',
        })
        config_path = _write_yaml(tmp_path / 'delete.yaml', {
            'name': 'Delete Array',
            'global-config': {'enabledMcpjsonServers': None},
        })

        _run_setup(config_path)

        errors = validate_json_arrays(claude_json, {('enabledMcpjsonServers',): None})
        assert not errors, '\n'.join(errors)
        assert _read_json(claude_json)['editorMode'] == 'vim'

    def test_isolated_run_merges_the_profile_claude_json_and_leaves_the_base_untouched(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """The profile file is unioned with its own arrays; the base file keeps exactly its content.

        The base file and the profile file start with different arrays. After
        the run the profile file holds its own elements first and the YAML
        elements after them, while the base file is byte-for-byte unchanged:
        one merge into the profile's own file, no write to the base.
        """
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        base_claude_json = home / '.claude.json'
        profile_claude_json = claude_dir / PROFILE_NAME / '.claude.json'
        _write_json(base_claude_json, {'enabledMcpjsonServers': ['base-cli-server']})
        base_bytes = base_claude_json.read_bytes()
        _write_json(profile_claude_json, {
            'customApiKeyResponses': {'approved': ['profile-cli-key']},
        })
        config_path = _write_yaml(tmp_path / 'isolated.yaml', {
            'name': 'Isolated Arrays',
            'command-names': [PROFILE_NAME],
            'global-config': {
                'enabledMcpjsonServers': ['yaml-server'],
                'customApiKeyResponses': {'approved': ['yaml-key', 'profile-cli-key']},
            },
        })

        _run_setup(config_path)

        assert base_claude_json.read_bytes() == base_bytes, 'An isolated run must not write the base ~/.claude.json'
        errors = validate_json_arrays(profile_claude_json, {
            ('enabledMcpjsonServers',): ['yaml-server'],
            ('customApiKeyResponses', 'approved'): ['profile-cli-key', 'yaml-key'],
        })
        assert not errors, '\n'.join(errors)


class TestInheritLayerReplacesArrays:
    """Under inherit, a child's global-config array replaces the parent's."""

    @staticmethod
    def _write_parent(directory: Path) -> None:
        _write_yaml(directory / 'parent.yaml', {
            'name': 'Parent',
            'global-config': {
                'enabledMcpjsonServers': ['parent-server'],
                'customApiKeyResponses': {'approved': ['parent-key']},
                'parentOnly': True,
            },
        })

    def test_merge_keys_child_array_replaces_parent_array_at_every_depth(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Objects merge, but each child array arrives without the parent's elements."""
        home = e2e_isolated_home['home']
        self._write_parent(tmp_path)
        child_path = _write_yaml(tmp_path / 'child.yaml', {
            'name': 'Child',
            'inherit': 'parent.yaml',
            'merge-keys': ['global-config'],
            'global-config': {
                'enabledMcpjsonServers': ['child-server'],
                'customApiKeyResponses': {'approved': ['child-key']},
            },
        })

        _run_setup(child_path)

        claude_json = home / '.claude.json'
        errors = validate_json_arrays(claude_json, {
            ('enabledMcpjsonServers',): ['child-server'],
            ('customApiKeyResponses', 'approved'): ['child-key'],
        })
        assert not errors, '\n'.join(errors)
        assert _read_json(claude_json)['parentOnly'] is True, \
            'merge-keys must keep the parent members the child does not declare'

    def test_without_merge_keys_child_section_replaces_parent_section(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Without merge-keys nothing of the parent's global-config reaches the file."""
        home = e2e_isolated_home['home']
        self._write_parent(tmp_path)
        child_path = _write_yaml(tmp_path / 'child.yaml', {
            'name': 'Child',
            'inherit': 'parent.yaml',
            'global-config': {'enabledMcpjsonServers': ['child-server']},
        })

        _run_setup(child_path)

        claude_json = home / '.claude.json'
        errors = validate_json_arrays(claude_json, {
            ('enabledMcpjsonServers',): ['child-server'],
            ('customApiKeyResponses',): None,
            ('parentOnly',): None,
        })
        assert not errors, '\n'.join(errors)

    def test_resolved_child_array_is_then_unioned_with_the_file(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Both layers in one run: the parent element is gone, the file's element stays."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        _write_json(claude_json, {'enabledMcpjsonServers': ['cli-server']})
        self._write_parent(tmp_path)
        child_path = _write_yaml(tmp_path / 'child.yaml', {
            'name': 'Child',
            'inherit': 'parent.yaml',
            'merge-keys': ['global-config'],
            'global-config': {'enabledMcpjsonServers': ['child-server']},
        })

        _run_setup(child_path)

        errors = validate_json_arrays(claude_json, {
            ('enabledMcpjsonServers',): ['cli-server', 'child-server'],
        })
        assert not errors, '\n'.join(errors)

    def test_user_settings_inherit_unions_permissions_and_replaces_other_arrays(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """The user-settings counterpart keeps both permission lists and only the child's other arrays."""
        claude_dir = e2e_isolated_home['claude_dir']
        _write_yaml(tmp_path / 'parent.yaml', {
            'name': 'Parent',
            'user-settings': {
                'permissions': {
                    'allow': ['Read'],
                    'additionalDirectories': ['/parent-dir'],
                },
                'companyAnnouncements': ['parent announcement'],
            },
        })
        child_path = _write_yaml(tmp_path / 'child.yaml', {
            'name': 'Child',
            'inherit': 'parent.yaml',
            'merge-keys': ['user-settings'],
            'user-settings': {
                'permissions': {
                    'allow': ['Write'],
                    'additionalDirectories': ['/child-dir'],
                },
                'companyAnnouncements': ['child announcement'],
            },
        })

        _run_setup(child_path)

        errors = validate_json_arrays(claude_dir / 'settings.json', {
            ('permissions', 'allow'): ['Read', 'Write'],
            ('permissions', 'additionalDirectories'): ['/child-dir'],
            ('companyAnnouncements',): ['child announcement'],
        })
        assert not errors, '\n'.join(errors)


class TestIsolatedConfigJsonHoldsResolvedArrays:
    """An isolated run rebuilds config.json, so its user-settings arrays are the resolved ones."""

    def test_rebuild_drops_stale_arrays_and_follows_a_shorter_yaml_list(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Arrays already in config.json never survive a run; a re-run with a shorter list shrinks it."""
        profile_dir = e2e_isolated_home['claude_dir'] / PROFILE_NAME
        config_json = profile_dir / 'config.json'
        _write_json(config_json, {
            'permissions': {'allow': ['Stale']},
            'companyAnnouncements': ['stale announcement'],
        })
        config_path = tmp_path / 'isolated-settings.yaml'

        def write_config(allow: list[str]) -> None:
            _write_yaml(config_path, {
                'name': 'Isolated Settings Arrays',
                'command-names': [PROFILE_NAME],
                'user-settings': {'permissions': {'allow': allow}},
            })

        write_config(['Read', 'Write'])
        _run_setup(config_path)

        errors = validate_json_arrays(config_json, {
            ('permissions', 'allow'): ['Read', 'Write'],
            ('companyAnnouncements',): None,
        })
        assert not errors, 'first run:\n' + '\n'.join(errors)

        write_config(['Read'])
        _run_setup(config_path)

        errors = validate_json_arrays(config_json, {
            ('permissions', 'allow'): ['Read'],
        })
        assert not errors, 're-run:\n' + '\n'.join(errors)
        assert not (profile_dir / 'settings.json').exists(), \
            'an isolated run must not write user-settings to the profile settings.json'
