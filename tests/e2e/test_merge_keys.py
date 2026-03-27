"""E2E tests for the merge-keys selective merge feature.

Tests verify that configuration inheritance with merge-keys correctly merges
specified keys using type-aware strategies while replacing non-listed keys.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import setup_environment


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to E2E fixtures directory."""
    return Path(__file__).parent / 'fixtures'


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its content."""
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _resolve(
    config: dict[str, Any],
    source: str,
) -> tuple[dict[str, Any], list[setup_environment.InheritanceChainEntry]]:
    """Resolve config inheritance from a source path."""
    return setup_environment.resolve_config_inheritance(config, source)


class TestTwoLevelMerge:
    """Test two-level parent-child inheritance with merge-keys."""

    def test_agents_merged(self, fixtures_dir):
        """Agents from parent and child are concatenated with dedup."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        assert 'agents/parent-agent.md' in resolved['agents']
        assert 'agents/child-agent.md' in resolved['agents']

    def test_rules_merged(self, fixtures_dir):
        """Rules from parent and child are concatenated."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        assert 'rules/parent-rule.md' in resolved['rules']
        assert 'rules/child-rule.md' in resolved['rules']

    def test_mcp_servers_in_position_replacement(self, fixtures_dir):
        """MCP server with same name replaced in-position; new server appended."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        servers = resolved['mcp-servers']
        # parent-server replaced in-position (was at index 0)
        assert servers[0]['name'] == 'parent-server'
        assert servers[0]['url'] == 'http://localhost:3000/child-override'
        assert servers[0]['scope'] == 'project'
        # child-server appended
        assert servers[1]['name'] == 'child-server'

    def test_dependencies_per_platform_merge(self, fixtures_dir):
        """Dependencies merged per-platform with dedup."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        deps = resolved['dependencies']
        assert 'echo parent-common' in deps['common']
        assert 'echo child-common' in deps['common']
        assert 'echo parent-linux' in deps['linux']
        assert 'echo child-windows' in deps['windows']

    def test_hooks_files_dedup_events_concat(self, fixtures_dir):
        """Hooks files deduplicated, events concatenated."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        hooks = resolved['hooks']
        assert 'hooks/parent-hook.py' in hooks['files']
        assert 'hooks/child-hook.py' in hooks['files']
        assert len(hooks['events']) == 2

    def test_global_config_deep_merge(self, fixtures_dir):
        """Global-config deep merged: child overrides shared key, parent-only preserved."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        gc = resolved['global-config']
        assert gc['parentKey'] == 'parentValue'
        assert gc['childKey'] == 'childValue'
        assert gc['sharedKey'] == 'fromChild'

    def test_user_settings_deep_merge_with_permission_union(self, fixtures_dir):
        """User-settings deep merged with permission array union."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        us = resolved['user-settings']
        assert us['language'] == 'english'
        assert us['theme'] == 'dark'
        perms = us['permissions']['allow']
        assert 'Read' in perms
        assert 'Write' in perms

    def test_env_variables_shallow_merge_null_delete(self, fixtures_dir):
        """Env-variables shallow merged, null deletes parent key."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        env = resolved['env-variables']
        assert env['PARENT_VAR'] == 'parent_val'
        assert env['CHILD_VAR'] == 'child_val'
        assert 'SHARED_VAR' not in env

    def test_os_env_variables_shallow_merge(self, fixtures_dir):
        """Os-env-variables shallow merged."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        os_env = resolved['os-env-variables']
        assert os_env['PARENT_OS'] == 'parent_os_val'
        assert os_env['CHILD_OS'] == 'child_os_val'

    def test_skills_merged_by_name(self, fixtures_dir):
        """Skills merged by name identity."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        skill_names = [s['name'] for s in resolved['skills']]
        assert 'parent-skill' in skill_names
        assert 'child-skill' in skill_names

    def test_files_to_download_merged_by_dest(self, fixtures_dir):
        """Files-to-download merged by dest identity."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        files = resolved['files-to-download']
        dest_map = {f['dest']: f['source'] for f in files}
        # parent-file.txt overridden by child (same dest)
        assert dest_map['~/.claude/parent-file.txt'] == 'configs/override-parent.txt'
        # child-file.txt added
        assert '~/.claude/child-file.txt' in dest_map

    def test_name_replaced_not_merged(self, fixtures_dir):
        """Name is not in merge-keys, so child replaces parent."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        assert resolved['name'] == 'Merge Child'

    def test_meta_keys_stripped(self, fixtures_dir):
        """inherit and merge-keys are not present in resolved config."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))
        assert 'inherit' not in resolved
        assert 'merge-keys' not in resolved


class TestFourLevelChain:
    """Test 4-level inheritance chain with mixed merge/replace semantics."""

    def test_merge_replace_merge_pattern(self, fixtures_dir):
        """L1 source -> L2 merge -> L3 replace -> L4 merge = L3+L4 only."""
        l4_path = fixtures_dir / 'merge_chain_l4.yaml'
        config = _load_yaml(l4_path)
        resolved, chain = _resolve(config, str(l4_path))

        agents = resolved['agents']
        # L3 replaces everything from L1+L2 with ['agents/l3-agent.md']
        # L4 merges with L3, adding ['agents/l4-agent.md']
        assert 'agents/l3-agent.md' in agents
        assert 'agents/l4-agent.md' in agents
        # L1 and L2 agents should NOT be present (L3 replaced)
        assert 'agents/l1-agent.md' not in agents
        assert 'agents/l2-agent.md' not in agents

    def test_mcp_servers_chain(self, fixtures_dir):
        """MCP servers follow same merge-replace-merge pattern."""
        l4_path = fixtures_dir / 'merge_chain_l4.yaml'
        config = _load_yaml(l4_path)
        resolved, _ = _resolve(config, str(l4_path))

        server_names = [s['name'] for s in resolved['mcp-servers']]
        assert 'l3-server' in server_names
        assert 'l4-server' in server_names
        assert 'l1-server' not in server_names
        assert 'l2-server' not in server_names

    def test_rules_chain(self, fixtures_dir):
        """Rules follow same merge-replace-merge pattern."""
        l4_path = fixtures_dir / 'merge_chain_l4.yaml'
        config = _load_yaml(l4_path)
        resolved, _ = _resolve(config, str(l4_path))

        rules = resolved['rules']
        assert 'rules/l3-rule.md' in rules
        assert 'rules/l4-rule.md' in rules
        assert 'rules/l1-rule.md' not in rules
        assert 'rules/l2-rule.md' not in rules

    def test_chain_length(self, fixtures_dir):
        """Inheritance chain has 3 entries (L1, L2, L3 as ancestors of L4)."""
        l4_path = fixtures_dir / 'merge_chain_l4.yaml'
        config = _load_yaml(l4_path)
        _, chain = _resolve(config, str(l4_path))
        assert len(chain) == 3

    def test_name_from_last_child(self, fixtures_dir):
        """Name comes from L4 (last child replaces)."""
        l4_path = fixtures_dir / 'merge_chain_l4.yaml'
        config = _load_yaml(l4_path)
        resolved, _ = _resolve(config, str(l4_path))
        assert resolved['name'] == 'Chain Level 4'


class TestTwoLevelReplace:
    """Test two-level inheritance WITHOUT merge-keys (plain replace)."""

    def test_no_merge_keys_replaces_completely(self, fixtures_dir):
        """Without merge-keys, child completely replaces parent agents."""
        l3_path = fixtures_dir / 'merge_chain_l3.yaml'
        config = _load_yaml(l3_path)
        resolved, _ = _resolve(config, str(l3_path))

        # L3 has no merge-keys, so it replaces L2's (merged) agents
        agents = resolved['agents']
        assert agents == ['agents/l3-agent.md']


class TestMergeKeysWithoutInherit:
    """Test merge-keys behavior when inherit is absent."""

    def test_warning_emitted(self, capsys):
        """Warning about merge-keys without inherit is emitted."""
        config = {'name': 'test', 'merge-keys': ['agents']}
        setup_environment.resolve_config_inheritance(config, 'test.yaml')
        captured = capsys.readouterr()
        assert 'has no effect without' in captured.out

    def test_merge_keys_stripped_from_result(self):
        """merge-keys is stripped from result when no inherit."""
        config = {'name': 'test', 'merge-keys': ['agents'], 'agents': ['a.md']}
        resolved, _ = setup_environment.resolve_config_inheritance(config, 'test.yaml')
        assert 'merge-keys' not in resolved
        assert resolved['agents'] == ['a.md']

    def test_golden_config_has_merge_keys(self, golden_config):
        """Golden config includes merge-keys for testing."""
        assert 'merge-keys' in golden_config


class TestMixedMergeAndReplace:
    """Test that some keys merge while others replace in the same child."""

    def test_mixed_within_single_child(self, fixtures_dir):
        """In merge_child.yaml, agents merges but name replaces."""
        child_path = fixtures_dir / 'merge_child.yaml'
        config = _load_yaml(child_path)
        resolved, _ = _resolve(config, str(child_path))

        # Merged key
        assert len(resolved['agents']) == 2
        # Replaced key (name is not in merge-keys)
        assert resolved['name'] == 'Merge Child'
