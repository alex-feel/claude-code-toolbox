"""Parity tests: hooks-files consistency verdicts must match across both scripts.

validate_hooks_files_consistency() in setup_environment.py is the runtime twin
of the Pydantic model validator of the same name in environment_config.py (the
standalone script policy prevents a cross-import, so the two implementations
are deliberate duplicates). These tests run a shared corpus of configuration
shapes through both sides and enforce identical accept/reject verdicts, plus
strict parity of the basename derivation both sides rely on.

The corpus covers only shapes both sides can evaluate: the model rejects
structural violations (non-string entries, unknown hook types) at the typing
layer before the consistency validator runs, so those shapes are exercised
runtime-only in tests/test_hooks_consistency_validation.py.

The one deliberate asymmetry is inherit: the model SKIPS the consistency
checks for inherit-declaring configs (cross-references are decidable only on
the resolved composition), while the runtime twin runs on the RESOLVED
configuration and enforces them there.

If a verdict test fails, the matching semantics were changed in one module but
not the other. Fix: update BOTH modules so the verdicts match exactly.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from scripts.models.environment_config import EnvironmentConfig
from scripts.models.environment_config import _extract_basename
from scripts.setup_environment import _hook_file_basename
from scripts.setup_environment import validate_hooks_files_consistency

# Shared corpus: (label, config-without-name, expected-valid)
CONSISTENCY_CORPUS: list[tuple[str, dict[str, Any], bool]] = [
    (
        'consistent-command-and-config',
        {
            'hooks': {
                'files': ['hooks/a.py', 'configs/a_cfg.yaml'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'matcher': 'Edit',
                        'type': 'command',
                        'command': 'a.py',
                        'config': 'a_cfg.yaml',
                    },
                ],
            },
        },
        True,
    ),
    (
        'consistent-url-files',
        {
            'hooks': {
                'files': [
                    'https://example.com/hooks/a.py?ref=main',
                    'https://example.com/configs/a_cfg.yaml',
                ],
                'events': [
                    {'event': 'PostToolUse', 'command': 'a.py', 'config': 'a_cfg.yaml'},
                ],
            },
        },
        True,
    ),
    (
        'consistent-status-line-only',
        {
            'hooks': {
                'files': ['hooks/sl.py', 'configs/sl_cfg.yaml'],
                'events': [],
            },
            'status-line': {'file': 'sl.py', 'config': 'sl_cfg.yaml'},
        },
        True,
    ),
    (
        'consistent-windows-path-files',
        {
            'hooks': {
                'files': ['C:\\Users\\user\\hooks\\a.py'],
                'events': [{'event': 'PostToolUse', 'command': 'a.py'}],
            },
        },
        True,
    ),
    (
        'consistent-config-query-parameters',
        {
            'hooks': {
                'files': ['hooks/a.py', 'configs/c.yaml'],
                'events': [
                    {'event': 'PostToolUse', 'command': 'a.py', 'config': 'c.yaml?ref=main'},
                ],
            },
        },
        True,
    ),
    (
        'consistent-prompt-only-empty-files',
        {
            'hooks': {
                'files': [],
                'events': [
                    {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'prompt', 'prompt': 'check'},
                ],
            },
        },
        True,
    ),
    (
        'consistent-http-and-agent-excluded',
        {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [
                    {'event': 'PostToolUse', 'command': 'a.py'},
                    {'event': 'PostToolUse', 'matcher': 'Write', 'type': 'http', 'url': 'http://localhost:1/h'},
                    {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'agent', 'prompt': 'verify'},
                ],
            },
        },
        True,
    ),
    ('no-hooks-at-all', {}, True),
    ('null-hooks', {'hooks': None}, True),
    (
        'missing-command-reference',
        {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [{'event': 'PostToolUse', 'command': 'missing.py'}],
            },
        },
        False,
    ),
    (
        'missing-config-reference',
        {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [
                    {'event': 'PostToolUse', 'command': 'a.py', 'config': 'missing.yaml'},
                ],
            },
        },
        False,
    ),
    (
        'unused-file',
        {
            'hooks': {
                'files': ['hooks/a.py', 'hooks/unused.py'],
                'events': [{'event': 'PostToolUse', 'command': 'a.py'}],
            },
        },
        False,
    ),
    (
        'status-line-path-form-file',
        {
            'hooks': {
                'files': ['hooks/sl.py'],
                'events': [],
            },
            'status-line': {'file': 'hooks/sl.py'},
        },
        False,
    ),
    (
        'status-line-missing-config',
        {
            'hooks': {
                'files': ['hooks/sl.py'],
                'events': [],
            },
            'status-line': {'file': 'sl.py', 'config': 'missing.yaml'},
        },
        False,
    ),
    (
        'status-line-without-hooks',
        {'status-line': {'file': 'sl.py'}},
        False,
    ),
]


def _model_accepts(config: dict[str, Any]) -> bool:
    """Return whether the Pydantic model validates the config."""
    try:
        EnvironmentConfig.model_validate({'name': 'hooks-parity-probe', **config})
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize(
    ('label', 'config', 'expected_valid'),
    CONSISTENCY_CORPUS,
    ids=[label for label, _, _ in CONSISTENCY_CORPUS],
)
def test_consistency_verdict_parity(
    label: str,
    config: dict[str, Any],
    expected_valid: bool,
) -> None:
    """Model and runtime twin agree on every corpus shape."""
    del label
    model_valid = _model_accepts(config)
    runtime_errors = validate_hooks_files_consistency(config)
    runtime_valid = not runtime_errors
    assert model_valid == expected_valid, (
        f'Model verdict {model_valid} != expected {expected_valid}'
    )
    assert runtime_valid == expected_valid, (
        f'Runtime verdict {runtime_valid} != expected {expected_valid}: {runtime_errors}'
    )


@pytest.mark.parametrize(
    'path_or_url',
    [
        'script.py',
        'hooks/script.py',
        '/home/user/script.py',
        'C:\\Users\\user\\script.py',
        'https://example.com/path/to/script.py',
        'https://example.com/path/to/script.py?ref=main',
        'https://gitlab.com/api/v4/projects/1/repository/files/sub%2Fscript.py/raw',
        '',
    ],
)
def test_basename_derivation_parity(path_or_url: str) -> None:
    """The runtime basename helper mirrors the model's exactly."""
    assert _hook_file_basename(path_or_url) == _extract_basename(path_or_url)


def test_inherit_asymmetry_model_skips_runtime_enforces() -> None:
    """The model skips inherit-declaring configs; the runtime twin enforces.

    A leaf whose event references a file only a parent contributes is valid
    for the model (undecidable standalone) and stays enforceable at runtime
    because the twin sees the resolved composition, where the reference
    either resolves or fails.
    """
    leaf = {
        'inherit': 'parent.yaml',
        'hooks': {
            'files': [],
            'events': [{'event': 'PostToolUse', 'command': 'parent_contributed.py'}],
        },
    }
    # Model accepts: the consistency validator is skipped under inherit
    EnvironmentConfig.model_validate({'name': 'hooks-parity-probe', **leaf})
    # The runtime twin, running on what would be a resolved config with the
    # same content, reports the dangling reference
    resolved_without_parent = {key: value for key, value in leaf.items() if key != 'inherit'}
    errors = validate_hooks_files_consistency(resolved_without_parent)
    assert any('parent_contributed.py' in e for e in errors)
