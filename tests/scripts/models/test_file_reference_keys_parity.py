"""Parity test: FILE_REFERENCE_KEYS must match keys processed by _resolve_config_file_paths().

Ensures the registry constant stays synchronized with the actual resolution logic.
If this test fails, a file-reference key was added to or removed from
_resolve_config_file_paths() without updating FILE_REFERENCE_KEYS (or vice versa).

Fix: Update BOTH FILE_REFERENCE_KEYS and _resolve_config_file_paths() simultaneously.
"""

from __future__ import annotations

from scripts.setup_environment import FILE_REFERENCE_KEYS
from scripts.setup_environment import _resolve_config_file_paths


def _get_keys_resolved_by_function() -> frozenset[str]:
    """Determine which file-reference keys _resolve_config_file_paths actually resolves.

    Feeds a config with sentinel values for all possible file-reference keys
    and checks which ones are transformed by the function.

    Returns:
        frozenset of dot-path key identifiers that the function resolves.
    """
    sentinel_value = 'sentinel-relative-path.txt'
    url_source = 'https://raw.githubusercontent.com/test/repo/main/config.yaml'

    # Config with all possible file-reference key types populated
    config: dict = {
        'agents': [sentinel_value],
        'slash-commands': [sentinel_value],
        'rules': [sentinel_value],
        'hooks': {'files': [sentinel_value], 'events': []},
        'files-to-download': [{'source': sentinel_value, 'destination': '/tmp/test'}],
        'skills': [{'base': sentinel_value, 'files': ['SKILL.md']}],
        'command-defaults': {'system-prompt': sentinel_value, 'mode': 'replace'},
        'status-line': {'file': sentinel_value, 'config': sentinel_value, 'interval': 10},
    }

    result = _resolve_config_file_paths(config, url_source)

    resolved_keys: set[str] = set()

    # Check simple list keys
    for key in ('agents', 'slash-commands', 'rules'):
        if result.get(key) and result[key] != config[key]:
            resolved_keys.add(key)

    # Check hooks.files
    if (
        result.get('hooks', {}).get('files')
        and result['hooks']['files'] != config['hooks']['files']
    ):
        resolved_keys.add('hooks.files')

    # Check files-to-download
    ftd_result = result.get('files-to-download', [])
    ftd_original = config['files-to-download']
    if ftd_result and ftd_result[0].get('source') != ftd_original[0].get('source'):
        resolved_keys.add('files-to-download')

    # Check skills
    skills_result = result.get('skills', [])
    skills_original = config['skills']
    if skills_result and skills_result[0].get('base') != skills_original[0].get('base'):
        resolved_keys.add('skills')

    # Check command-defaults.system-prompt
    cd_result = result.get('command-defaults', {})
    cd_original = config['command-defaults']
    if cd_result.get('system-prompt') != cd_original.get('system-prompt'):
        resolved_keys.add('command-defaults.system-prompt')

    # Check status-line.file
    sl_result = result.get('status-line', {})
    sl_original = config['status-line']
    if sl_result.get('file') != sl_original.get('file'):
        resolved_keys.add('status-line.file')

    # Check status-line.config
    if sl_result.get('config') != sl_original.get('config'):
        resolved_keys.add('status-line.config')

    return frozenset(resolved_keys)


def test_file_reference_keys_match_resolve_function() -> None:
    """FILE_REFERENCE_KEYS must match keys resolved by _resolve_config_file_paths."""
    resolved_keys = _get_keys_resolved_by_function()
    assert resolved_keys == FILE_REFERENCE_KEYS, (
        f'FILE_REFERENCE_KEYS and _resolve_config_file_paths are out of sync.\n'
        f'In FILE_REFERENCE_KEYS only: {sorted(FILE_REFERENCE_KEYS - resolved_keys)}\n'
        f'Resolved by function only: {sorted(resolved_keys - FILE_REFERENCE_KEYS)}'
    )


def test_file_reference_keys_is_subset_of_known_keys() -> None:
    """All top-level keys in FILE_REFERENCE_KEYS must appear in KNOWN_CONFIG_KEYS.

    Dot-path keys (e.g., 'hooks.files') are checked by their top-level prefix.
    """
    from scripts.setup_environment import KNOWN_CONFIG_KEYS

    for key in FILE_REFERENCE_KEYS:
        top_level = key.split('.')[0]
        assert top_level in KNOWN_CONFIG_KEYS, (
            f'FILE_REFERENCE_KEYS contains "{key}" whose top-level key "{top_level}" '
            f'is not in KNOWN_CONFIG_KEYS.'
        )
