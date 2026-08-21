"""Parity test: HOOK_EVENT_NAMES must match across both modules.

setup_environment.py and scripts/models/environment_config.py each define the
set of hook event names Claude Code recognizes. The standalone script policy
forbids a cross-import, so the two definitions are deliberate duplicates. This
test enforces strict equality between them.

If this test fails, the event-name set was changed in one module but not the
other. Fix: update BOTH modules so the constants match exactly.
"""

from __future__ import annotations

from scripts.models import environment_config as model_mod
from scripts.setup_environment import HOOK_EVENT_NAMES as SETUP_HOOK_EVENT_NAMES


def test_hook_event_names_parity() -> None:
    """HOOK_EVENT_NAMES is identical in both modules."""
    assert SETUP_HOOK_EVENT_NAMES == model_mod.HOOK_EVENT_NAMES


def test_hook_event_names_is_frozenset() -> None:
    """Both definitions are frozensets (immutable, hashable membership sets)."""
    assert isinstance(SETUP_HOOK_EVENT_NAMES, frozenset)
    assert isinstance(model_mod.HOOK_EVENT_NAMES, frozenset)
