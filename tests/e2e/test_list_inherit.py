"""E2E tests for list-based inherit (composition chains).

Tests verify that configuration inheritance with a list of sources composes
configs sequentially: first entry is the base, each subsequent entry overrides
the previous, and the leaf's own keys are the final override. Leaf merge-keys
applies only to the final merge step.
"""

from pathlib import Path
from typing import Any

import yaml

from scripts import setup_environment


def _fixtures_dir() -> Path:
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


class TestListInheritBasicComposition:
    """Test basic list inherit composition with real fixture files."""

    def test_model_inherited_from_base(self):
        """Model comes from base (not overridden by middle or leaf)."""
        leaf_path = _fixtures_dir() / 'list_inherit_leaf.yaml'
        config = _load_yaml(leaf_path)
        resolved, _ = _resolve(config, str(leaf_path))
        assert resolved['model'] == 'sonnet'

    def test_agents_replaced_by_middle(self):
        """Agents from middle replace base agents (inter-entry replace)."""
        leaf_path = _fixtures_dir() / 'list_inherit_leaf.yaml'
        config = _load_yaml(leaf_path)
        resolved, _ = _resolve(config, str(leaf_path))
        assert resolved['agents'] == ['agents/middle-agent.md']

    def test_env_variables_replaced_by_leaf(self):
        """Leaf env-variables replaces accumulated (no merge-keys)."""
        leaf_path = _fixtures_dir() / 'list_inherit_leaf.yaml'
        config = _load_yaml(leaf_path)
        resolved, _ = _resolve(config, str(leaf_path))
        env = resolved['env-variables']
        # Leaf's env-variables replaces the accumulated base+middle entirely
        assert env == {'LEAF_VAR': 'from-leaf'}
        assert 'BASE_VAR' not in env
        assert 'MIDDLE_VAR' not in env

    def test_name_from_leaf(self):
        """Name comes from leaf (final override)."""
        leaf_path = _fixtures_dir() / 'list_inherit_leaf.yaml'
        config = _load_yaml(leaf_path)
        resolved, _ = _resolve(config, str(leaf_path))
        assert resolved['name'] == 'List Inherit Leaf'

    def test_meta_keys_stripped(self):
        """inherit and merge-keys are stripped from resolved config."""
        leaf_path = _fixtures_dir() / 'list_inherit_leaf.yaml'
        config = _load_yaml(leaf_path)
        resolved, _ = _resolve(config, str(leaf_path))
        assert 'inherit' not in resolved
        assert 'merge-keys' not in resolved

    def test_chain_length(self):
        """Inheritance chain contains both base and middle entries."""
        leaf_path = _fixtures_dir() / 'list_inherit_leaf.yaml'
        config = _load_yaml(leaf_path)
        _, chain = _resolve(config, str(leaf_path))
        assert len(chain) == 2


class TestListInheritWithLeafMergeKeys:
    """Test list inherit with leaf-level merge-keys."""

    def test_agents_merged_across_chain(self):
        """Agents are MERGED (not replaced) because leaf declares merge-keys."""
        leaf_path = _fixtures_dir() / 'list_inherit_with_merge.yaml'
        config = _load_yaml(leaf_path)
        resolved, _ = _resolve(config, str(leaf_path))
        agents = resolved['agents']
        # Between base and middle: REPLACE (inter-entry, no merge-keys)
        # So accumulated agents = ['agents/middle-agent.md']
        # Final merge with leaf: MERGE (leaf has merge-keys: [agents])
        assert 'agents/middle-agent.md' in agents
        assert 'agents/leaf-agent.md' in agents
        # Base agent was replaced by middle (not merged)
        assert 'agents/base-agent.md' not in agents

    def test_env_variables_merged(self):
        """Env-variables are MERGED because leaf declares merge-keys."""
        leaf_path = _fixtures_dir() / 'list_inherit_with_merge.yaml'
        config = _load_yaml(leaf_path)
        resolved, _ = _resolve(config, str(leaf_path))
        env = resolved['env-variables']
        # Accumulated from base+middle (replace): BASE_VAR=overridden, MIDDLE_VAR=from-middle
        # Leaf merges: LEAF_VAR=from-leaf added
        assert env['BASE_VAR'] == 'overridden-by-middle'
        assert env['MIDDLE_VAR'] == 'from-middle'
        assert env['LEAF_VAR'] == 'from-leaf'


class TestListInheritChainDisplay:
    """Test that inheritance chain entries are present for display in summary."""

    def test_chain_entries_have_names(self):
        """Chain entries carry the config name for display."""
        leaf_path = _fixtures_dir() / 'list_inherit_leaf.yaml'
        config = _load_yaml(leaf_path)
        _, chain = _resolve(config, str(leaf_path))
        names = [entry.name for entry in chain]
        assert 'List Inherit Base' in names
        assert 'List Inherit Middle' in names
