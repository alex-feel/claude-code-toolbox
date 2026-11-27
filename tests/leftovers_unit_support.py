"""Shared helpers of the leftovers unit tests: files with their digests, settings files that wire a hook, live readers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts import setup_environment
from scripts.setup_environment import InstalledProfile
from scripts.setup_environment import LeftoverEntry
from scripts.setup_environment import LeftoverItem
from scripts.setup_environment import LiveLeftoverState


def sha(content: bytes) -> str:
    """The sha256 of the bytes, as the manifest records a file."""
    return hashlib.sha256(content).hexdigest()


def write(path: Path, content: bytes) -> str:
    """Write a file, its directories included, and return its digest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return sha(content)


def write_json(path: Path, data: object) -> None:
    """Write a JSON file, its directories included."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def hooks_settings(event: str, hook: dict[str, object]) -> dict[str, object]:
    """A settings file holding one matcher group with one hook under the event."""
    return {'hooks': {event: [{'matcher': '*', 'hooks': [hook]}]}}


def wiring(profile_dir: Path, name: str, event: str = 'Stop') -> dict[str, object]:
    """A settings file whose one hook runs hooks/NAME of the profile through uv, as the setup spells it."""
    return hooks_settings(event, {'type': 'command', 'command': f'uv run "{(profile_dir / "hooks" / name).as_posix()}"'})


def helper_entry(path: str, digest: str) -> LeftoverEntry:
    """A removable leftover installed as a hooks.helpers module."""
    return LeftoverEntry(LeftoverItem('file', path, digest, hook_helper=True), 'removable', '')


def live_state(
    profile_dir: Path,
    *,
    holders: dict[str, list[str]] | None = None,
    linked: frozenset[str] = frozenset(),
    settings_files: tuple[Path, ...] = (),
    dependents: tuple[InstalledProfile, ...] = (),
) -> LiveLeftoverState:
    """A live state over the real file system and real settings files, with links and holders given.

    Returns:
        The readers; the tests put the profile at <home>/.claude/p, so the
        home the wiring check expands is two levels above it.
    """
    def _references(relative: str, view: Mapping[Path, dict[str, Any]]) -> str | None:
        return setup_environment._hook_file_references(
            relative, profile_dir=profile_dir, home_dir=profile_dir.parents[1], settings_files=settings_files,
            dependents=dependents, view=view,
        )

    def _wired(installed: Iterable[str], view: Mapping[Path, dict[str, Any]]) -> str | None:
        return setup_environment._first_wired_hook_file(
            installed, profile_dir=profile_dir, home_dir=profile_dir.parents[1],
            settings_files=settings_files, dependents=dependents, view=view,
        )

    return LiveLeftoverState(
        file_digest=setup_environment._live_file_digest,
        under_link=lambda relative: relative.split('/')[0] in linked,
        destination_holders=lambda dest: (holders or {}).get(dest, []),
        hook_references=_references,
        hook_files_wired=_wired,
    )
