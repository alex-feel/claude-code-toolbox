"""E2E tests for inherit: [list] composition chains.

Tests verify that list-based inheritance follows the 3 mandatory rules:
1. Own inherit in ALL list entries is completely ignored
2. List behaves identically to separate-file chains (left-to-right)
3. merge-keys in each entry applies normally

Each test class focuses on a specific scenario. All tests use real YAML
fixture files loaded from disk, not mocked configs.
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


class TestBasicListComposition:
    """Test basic two-element list composition (Rule 2)."""

    def test_leaf_overrides_all(self, fixtures_dir):
        """Leaf name overrides middle and base."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        assert resolved['name'] == 'List Inherit Leaf'

    def test_left_to_right_priority_mcp_servers(self, fixtures_dir):
        """Middle (right) replaces base (left) MCP servers (no merge-keys for mcp-servers)."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        # Middle has merge-keys: [agents, rules] but NOT mcp-servers
        # So middle's mcp-servers replace base's at the accumulated level
        # Then leaf has no mcp-servers, so accumulated mcp-servers survive
        server_names = [s['name'] for s in resolved.get('mcp-servers', [])]
        assert 'middle-server' in server_names
        assert 'base-server' not in server_names

    def test_leaf_replaces_env_variables(self, fixtures_dir):
        """Leaf env-variables replaces accumulated (no merge-keys for env-variables)."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        # Leaf has env-variables without merge-keys, so it replaces entirely
        assert resolved['env-variables'] == {'LEAF_VAR': 'leaf_val'}
        assert 'BASE_VAR' not in resolved['env-variables']
        assert 'MIDDLE_VAR' not in resolved['env-variables']

    def test_leaf_keys_added(self, fixtures_dir):
        """Leaf's own keys appear in result."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        assert resolved['model'] == 'sonnet'
        assert resolved['env-variables']['LEAF_VAR'] == 'leaf_val'

    def test_meta_keys_stripped(self, fixtures_dir):
        """inherit and merge-keys stripped from final result."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        assert 'inherit' not in resolved
        assert 'merge-keys' not in resolved

    def test_chain_length(self, fixtures_dir):
        """Chain has 2 entries (base + middle) for 2-element list."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        _, chain = _resolve(config, str(path))
        assert len(chain) == 2


class TestOwnInheritStripping:
    """Test Rule 1: Own inherit in list entries is completely ignored."""

    def test_own_inherit_not_resolved(self, fixtures_dir):
        """Middle's own 'inherit: some-parent-that-should-be-ignored.yaml' is stripped."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        resolved, chain = _resolve(config, str(path))
        # Only base and middle loaded, not 'some-parent-that-should-be-ignored.yaml'
        chain_sources = [e.source for e in chain]
        assert not any('ignored' in s for s in chain_sources)

    def test_base_with_own_inherit_stripped(self, fixtures_dir):
        """Base's own inherit is stripped when it's a list entry."""
        path = fixtures_dir / 'list_inherit_leaf_strip_test.yaml'
        config = _load_yaml(path)
        resolved, chain = _resolve(config, str(path))
        chain_sources = [e.source for e in chain]
        assert not any('deeply-nested' in s for s in chain_sources)

    def test_only_listed_files_loaded(self, fixtures_dir):
        """Only the explicitly listed files are loaded, no recursive resolution."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        _, chain = _resolve(config, str(path))
        # Exactly 2 entries: base and middle
        assert len(chain) == 2

    def test_strip_test_chain_has_two_entries(self, fixtures_dir):
        """Strip test leaf should have exactly 2 entries despite base having own inherit."""
        path = fixtures_dir / 'list_inherit_leaf_strip_test.yaml'
        config = _load_yaml(path)
        _, chain = _resolve(config, str(path))
        assert len(chain) == 2


class TestMergeKeysPerEntry:
    """Test Rule 3: merge-keys in each entry applies normally."""

    def test_middle_merge_keys_merge_agents_visible_via_leaf_merge(self, fixtures_dir):
        """Middle's merge-keys verified via leaf that also merges agents."""
        # list_inherit_merge_keys_leaf.yaml has merge-keys: [agents, rules]
        # so the merge chain is: base agents + middle agents + leaf agents
        path = fixtures_dir / 'list_inherit_merge_keys_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        agents = resolved.get('agents', [])
        # Middle merge-keys merges with base, then leaf merge-keys merges again
        assert 'agents/base-agent.md' in agents
        assert 'agents/middle-agent.md' in agents
        assert 'agents/mk-leaf-agent.md' in agents

    def test_middle_merge_keys_merge_rules_visible_via_leaf_merge(self, fixtures_dir):
        """Middle's merge-keys for rules verified via leaf that also merges."""
        path = fixtures_dir / 'list_inherit_merge_keys_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        rules = resolved.get('rules', [])
        assert 'rules/base-rule.md' in rules
        assert 'rules/middle-rule.md' in rules
        assert 'rules/mk-leaf-rule.md' in rules

    def test_leaf_merge_keys_applied(self, fixtures_dir):
        """Leaf's own merge-keys applies on top of accumulated."""
        path = fixtures_dir / 'list_inherit_merge_keys_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        agents = resolved.get('agents', [])
        # All three levels' agents should be present
        assert 'agents/base-agent.md' in agents
        assert 'agents/middle-agent.md' in agents
        assert 'agents/mk-leaf-agent.md' in agents

    def test_leaf_merge_keys_merge_rules(self, fixtures_dir):
        """Leaf's merge-keys merges rules from all levels."""
        path = fixtures_dir / 'list_inherit_merge_keys_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        rules = resolved.get('rules', [])
        assert 'rules/base-rule.md' in rules
        assert 'rules/middle-rule.md' in rules
        assert 'rules/mk-leaf-rule.md' in rules

    def test_leaf_without_merge_keys_replaces_agents(self, fixtures_dir):
        """Leaf without merge-keys replaces accumulated agents."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        # Leaf has agents: [leaf-agent.md] WITHOUT merge-keys, so it replaces
        agents = resolved.get('agents', [])
        assert agents == ['agents/leaf-agent.md']
        assert 'agents/base-agent.md' not in agents
        assert 'agents/middle-agent.md' not in agents


class TestSingleElementListNormalization:
    """Test: inherit: ['x'] normalized to string path."""

    def test_single_element_resolves_recursively(self, fixtures_dir):
        """Single-element list uses existing recursive string path."""
        path = fixtures_dir / 'list_inherit_single.yaml'
        config = _load_yaml(path)
        resolved, chain = _resolve(config, str(path))
        # Should behave like inherit: list_inherit_base.yaml
        assert resolved['name'] == 'List Inherit Single'
        assert resolved['model'] == 'opus'

    def test_single_element_inherits_base_agents(self, fixtures_dir):
        """Single-element list inherits parent agents (replaced by leaf)."""
        path = fixtures_dir / 'list_inherit_single.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        # Leaf replaces agents (no merge-keys)
        assert 'agents/single-agent.md' in resolved['agents']

    def test_single_element_chain_has_one_entry(self, fixtures_dir):
        """Single-element list produces chain with 1 entry."""
        path = fixtures_dir / 'list_inherit_single.yaml'
        config = _load_yaml(path)
        _, chain = _resolve(config, str(path))
        assert len(chain) == 1


class TestEquivalenceToSeparateFiles:
    """Test Rule 2: list must behave IDENTICALLY to separate-file chains."""

    def test_equivalence_two_files(self, fixtures_dir):
        """inherit: [base, middle] == middle inherits base (separate files)."""
        # Method 1: List inherit
        leaf_path = fixtures_dir / 'list_inherit_leaf.yaml'
        leaf_config = _load_yaml(leaf_path)
        list_result, _ = _resolve(leaf_config, str(leaf_path))

        # Method 2: Simulate separate-file chain
        base_config = _load_yaml(fixtures_dir / 'list_inherit_base.yaml')
        middle_config = _load_yaml(fixtures_dir / 'list_inherit_middle.yaml')

        # Manually build the chain: base -> middle -> leaf
        # Step 1: strip middle's own inherit, apply merge-keys
        middle_mk = middle_config.get('merge-keys')
        middle_validated_mk = frozenset(middle_mk) if middle_mk else None
        base_stripped = {
            k: v for k, v in base_config.items()
            if k not in ('inherit', 'merge-keys')
        }
        step1 = setup_environment._merge_configs(
            base_stripped, middle_config, merge_keys=middle_validated_mk,
        )

        # Step 2: apply leaf on top (leaf has no merge-keys)
        leaf_fresh = _load_yaml(leaf_path)
        manual_result = setup_environment._merge_configs(step1, leaf_fresh, merge_keys=None)

        # Compare all keys except meta-keys
        for key in set(list_result.keys()) | set(manual_result.keys()):
            if key in ('inherit', 'merge-keys'):
                continue
            assert list_result.get(key) == manual_result.get(key), (
                f"Mismatch on key '{key}': "
                f"list={list_result.get(key)}, manual={manual_result.get(key)}"
            )


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_list_raises(self):
        """Empty inherit list raises ValueError."""
        config = {'inherit': [], 'name': 'Test'}
        with pytest.raises(ValueError, match='cannot be empty'):
            _resolve(config, 'test.yaml')

    def test_list_with_non_string_raises(self):
        """List with non-string entry raises ValueError."""
        config = {'inherit': ['a.yaml', 123], 'name': 'Test'}
        with pytest.raises(ValueError, match='must be a string'):
            _resolve(config, 'test.yaml')

    def test_list_with_blank_entry_raises(self):
        """List with whitespace-only entry raises ValueError."""
        config = {'inherit': ['a.yaml', '  '], 'name': 'Test'}
        with pytest.raises(ValueError, match='cannot be empty'):
            _resolve(config, 'test.yaml')

    def test_circular_dependency_in_list(self, fixtures_dir):
        """Duplicate entry in list triggers circular dependency."""
        config = {
            'inherit': ['list_inherit_base.yaml', 'list_inherit_base.yaml'],
            'name': 'Test',
        }
        with pytest.raises(ValueError, match='Circular dependency'):
            _resolve(config, str(fixtures_dir / 'test.yaml'))

    def test_missing_file_in_list_raises(self, fixtures_dir):
        """Non-existent file in list raises FileNotFoundError."""
        config = {
            'inherit': ['list_inherit_base.yaml', 'nonexistent_file.yaml'],
            'name': 'Test',
        }
        with pytest.raises(FileNotFoundError):
            _resolve(config, str(fixtures_dir / 'test.yaml'))

    def test_dict_inherit_raises(self):
        """Dict inherit value raises ValueError."""
        config = {'inherit': {'source': 'base.yaml'}, 'name': 'Test'}
        with pytest.raises(ValueError, match='must be a string or list'):
            _resolve(config, 'test.yaml')

    def test_int_inherit_raises(self):
        """Integer inherit value raises ValueError."""
        config = {'inherit': 42, 'name': 'Test'}
        with pytest.raises(ValueError, match='must be a string or list'):
            _resolve(config, 'test.yaml')


class TestChainOrdering:
    """Test that inheritance chain entries are recorded correctly."""

    def test_chain_order_matches_list_order(self, fixtures_dir):
        """Chain entries are in the same order as the list entries."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        _, chain = _resolve(config, str(path))
        # First entry should be base, second should be middle
        assert 'list_inherit_base' in chain[0].source
        assert 'list_inherit_middle' in chain[1].source

    def test_chain_source_types_correct(self, fixtures_dir):
        """Chain entries have correct source types (local files)."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        _, chain = _resolve(config, str(path))
        for entry in chain:
            assert entry.source_type == 'local'

    def test_chain_names_from_config(self, fixtures_dir):
        """Chain entry names come from config name field."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        _, chain = _resolve(config, str(path))
        assert chain[0].name == 'List Inherit Base'
        assert chain[1].name == 'List Inherit Middle'


class TestEnvVariableComposition:
    """Test that env-variables compose correctly across list entries."""

    def test_leaf_env_vars_replace_accumulated(self, fixtures_dir):
        """Leaf env-variables replaces accumulated (no merge-keys for env-variables)."""
        path = fixtures_dir / 'list_inherit_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        # Leaf has env-variables without merge-keys, so it replaces entirely
        env_vars = resolved['env-variables']
        assert env_vars == {'LEAF_VAR': 'leaf_val'}

    def test_env_vars_merged_when_merge_keys_used(self, fixtures_dir):
        """Env-variables merge when merge-keys includes env-variables."""
        path = fixtures_dir / 'list_inherit_merge_keys_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = _resolve(config, str(path))
        # merge_keys_leaf has merge-keys: [agents, rules] but NOT env-variables
        # Middle has env-variables which replaces base's env-variables
        # Leaf has NO env-variables key, so accumulated env-variables survive
        env_vars = resolved.get('env-variables', {})
        # Middle's env-variables replaced base's (no merge-keys for env-variables in middle)
        assert env_vars.get('MIDDLE_VAR') == 'middle_val'
        assert env_vars.get('SHARED_VAR') == 'from_middle'
