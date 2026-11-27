"""A Windows user environment kept in a JSON file, standing in for HKCU\\Environment in E2E tests.

Step 7 of a base run sets the profile's OS environment variables in the
Windows user environment (setx and reg delete), and a re-run reads them back
to find the leftovers of earlier runs. On Windows the E2E conftest installs
this fake as the setup's writer (set_os_env_variable_windows), its reader
(_read_user_environment_value) and a no-op WM_SETTINGCHANGE broadcast, so no
E2E test reads or changes the machine's own user environment; the file it
keeps is named in ENVIRONMENT_VARIABLE, so every child run started by the
test (tests/e2e/fixtures/setup_child.py) reads and writes the same one.
Variable names are compared without regard to letter case, as Windows
compares them.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

ENVIRONMENT_VARIABLE = 'CCT_E2E_FAKE_USER_ENVIRONMENT'


class FakeUserEnvironment:
    """The user environment of one test, in a JSON file of variable names and values.

    Attributes:
        path: The JSON file.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def values(self) -> dict[str, str]:
        """Return every variable the user environment holds."""
        if not self.path.is_file():
            return {}
        content: dict[str, str] = json.loads(self.path.read_text(encoding='utf-8'))
        return content

    def read(self, name: str) -> str | None:
        """Read a variable the way _read_user_environment_value() does: its value, or None when absent."""
        return next((value for key, value in self.values().items() if key.casefold() == name.casefold()), None)

    def write(self, name: str, value: str | None) -> bool:
        """Set or delete a variable the way set_os_env_variable_windows() does, and report success."""
        values = {key: stored for key, stored in self.values().items() if key.casefold() != name.casefold()}
        if value is not None:
            values[name] = value
        self.path.write_text(json.dumps(values, indent=2, sort_keys=True), encoding='utf-8')
        return True


def replacements(fake: FakeUserEnvironment) -> dict[str, Callable[..., Any]]:
    """Name the setup module functions the fake replaces, with what replaces each."""
    def _no_broadcast(*_args: object, **_kwargs: object) -> None:
        return None

    return {
        'set_os_env_variable_windows': fake.write,
        '_read_user_environment_value': fake.read,
        '_broadcast_wm_settingchange': _no_broadcast,
    }


def is_installed(module: ModuleType) -> bool:
    """Report whether a setup module writes through a FakeUserEnvironment."""
    return isinstance(getattr(module.set_os_env_variable_windows, '__self__', None), FakeUserEnvironment)
