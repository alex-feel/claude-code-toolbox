"""The ``claudeMdExcludes`` an isolated profile carries for the base config home, computed apart from the toolbox.

Claude Code matches ``claudeMdExcludes`` case-sensitively against paths it
builds from the working directory as spelled, so the toolbox spells every
ASCII letter of a pattern as a class matching either case and, on Windows,
adds the patterns of the home's 8.3 short spelling when Windows gives one
that differs from the long spelling beyond letter case (``%TEMP%`` spells a
home whose account name is longer than eight characters short). The helpers
here build the same patterns from the Windows API directly, so a test
compares what the toolbox wrote with an expectation that shares none of its
code.
"""

from __future__ import annotations

import ctypes
import re
import sys
from pathlib import Path

BASE_MEMORY_NAMES: tuple[str, ...] = ('CLAUDE.md', 'CLAUDE.local.md', 'rules/**')


def case_classes(text: str) -> str:
    """Spell every ASCII letter of ``text`` as a glob class matching either case."""
    return re.sub(r'[A-Za-z]', lambda match: f'[{match.group(0).lower()}{match.group(0).upper()}]', text)


def short_spelling(path: Path) -> Path | None:
    """Return the 8.3 short spelling Windows gives ``path`` when it differs from ``path`` beyond letter case.

    Args:
        path: An existing path.

    Returns:
        The short spelling, or None off Windows, when Windows gives none, or
        when the spelling it gives differs from ``path`` in letter case at
        most (a volume that creates no 8.3 names, or components of eight
        characters or fewer).
    """
    if sys.platform != 'win32':
        return None
    buffer = ctypes.create_unicode_buffer(32767)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer)):
        return None
    short = Path(buffer.value)
    if short.as_posix().casefold() == path.as_posix().casefold():
        return None
    return short


def home_spellings(home: Path) -> list[Path]:
    """Return ``home`` as given and, on Windows, its 8.3 short spelling when that differs."""
    short = short_spelling(home)
    return [home] if short is None else [home, short]


def base_exclusions(home: Path, *, with_rules: bool = True) -> list[str]:
    """Return the exclusions an isolated profile of ``home`` carries for the base config home.

    Args:
        home: The home directory the base profile lives in.
        with_rules: Whether the rules pattern is expected; a profile whose
            rules/ links from the base profile carries the memory files only.

    Returns:
        The long spelling's patterns, then the short spelling's when Windows
        gives one: CLAUDE.md, CLAUDE.local.md and, with rules, rules/** for
        each spelling, every ASCII letter a case class.
    """
    names = BASE_MEMORY_NAMES if with_rules else BASE_MEMORY_NAMES[:2]
    return [
        case_classes(f'{(spelling / ".claude").as_posix()}/{name}')
        for spelling in home_spellings(home)
        for name in names
    ]
