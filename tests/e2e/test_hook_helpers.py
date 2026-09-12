"""E2E tests for hooks.helpers, the shared modules hook scripts import.

Helpers download into the same directory as the hook scripts in BOTH routing
modes -- ``~/.claude/{cmd}/hooks/`` when ``command-names`` creates an isolated
profile and ``~/.claude/hooks/`` when it does not -- so a hook script reaches
its helper as a sibling import whichever directory it was installed into.
They are never registered as a command, so no helper name reaches the
generated hooks JSON or the status line.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.setup_environment import _build_hooks_json
from scripts.setup_environment import _hook_file_basename
from scripts.setup_environment import create_profile_config
from scripts.setup_environment import download_hook_files
from tests.e2e.validators import validate_hook_helpers_absent_from_json
from tests.e2e.validators import validate_hook_helpers_installed

HELPER_SOURCE = 'hooks/e2e_hook_helper.py'
HELPER_BASENAME = 'e2e_hook_helper.py'


@pytest.fixture
def golden_config_no_command_names() -> dict[str, Any]:
    """Load the no-command-names golden configuration."""
    path = Path(__file__).parent / 'golden_config_no_command_names.yaml'
    with path.open(encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestGoldenConfigsDeclareHelpers:
    """Both golden configs exercise the helpers key."""

    def test_isolated_golden_declares_helper(self, golden_config: dict[str, Any]) -> None:
        """The command-names golden config declares the helper module."""
        assert golden_config['hooks']['helpers'] == [HELPER_SOURCE]

    def test_base_golden_declares_helper(
        self, golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """The no-command-names golden config declares the helper module."""
        assert golden_config_no_command_names['hooks']['helpers'] == [HELPER_SOURCE]

    def test_helper_is_not_referenced_by_any_event(
        self, golden_config: dict[str, Any],
    ) -> None:
        """No event or status-line entry names the helper."""
        hooks = golden_config['hooks']
        referenced = {str(event.get('command', '')) for event in hooks['events']}
        referenced |= {str(event.get('config', '')) for event in hooks['events']}
        referenced.add(str(golden_config['status-line']['file']))
        assert HELPER_BASENAME not in referenced


class TestHelperDownloadDestination:
    """Helpers install beside the hook scripts in both routing modes."""

    def test_isolated_mode_installs_helper_in_profile_hooks_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
        mock_repo_path: Path,
    ) -> None:
        """With command-names, the helper lands in ~/.claude/{cmd}/hooks/."""
        claude_dir = e2e_isolated_home['claude_dir']
        cmd = golden_config['command-names'][0]
        hooks_dir = claude_dir / cmd / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        assert download_hook_files(
            golden_config['hooks'],
            claude_dir,
            str(mock_repo_path / 'config.yaml'),
            hooks_base_dir=hooks_dir,
        )

        errors = validate_hook_helpers_installed(hooks_dir, golden_config)
        assert not errors, '\n'.join(errors)
        # The helper does NOT land in the base hooks directory, which is
        # exactly why a literal files-to-download dest cannot serve it
        assert not (claude_dir / 'hooks' / HELPER_BASENAME).exists()

    def test_base_mode_installs_helper_in_base_hooks_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config_no_command_names: dict[str, Any],
        mock_repo_path: Path,
    ) -> None:
        """Without command-names, the helper lands in ~/.claude/hooks/."""
        claude_dir = e2e_isolated_home['claude_dir']

        assert download_hook_files(
            golden_config_no_command_names['hooks'],
            claude_dir,
            str(mock_repo_path / 'config.yaml'),
        )

        errors = validate_hook_helpers_installed(
            claude_dir / 'hooks', golden_config_no_command_names,
        )
        assert not errors, '\n'.join(errors)


class TestHelperAbsentFromGeneratedJson:
    """A helper name never reaches the generated hooks JSON or statusLine."""

    def test_helper_not_in_hooks_json(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """_build_hooks_json emits no command naming the helper."""
        hooks_dir = e2e_isolated_home['claude_dir'] / 'hooks'
        hooks_json = _build_hooks_json(golden_config['hooks'], hooks_dir)
        errors = validate_hook_helpers_absent_from_json(hooks_json, None, golden_config)
        assert not errors, '\n'.join(errors)

    def test_helper_not_in_profile_config_json(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """The isolated config.json carries no helper reference."""
        claude_dir = e2e_isolated_home['claude_dir']
        cmd = golden_config['command-names'][0]
        artifact_base_dir = claude_dir / cmd
        hooks_dir = artifact_base_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        assert create_profile_config(
            {
                'hooks': golden_config['hooks'],
                'statusLine': golden_config['status-line'],
            },
            artifact_base_dir,
            hooks_base_dir=hooks_dir,
        )

        data = json.loads((artifact_base_dir / 'config.json').read_text(encoding='utf-8'))
        errors = validate_hook_helpers_absent_from_json(
            data.get('hooks', {}), data.get('statusLine'), golden_config,
        )
        assert not errors, '\n'.join(errors)


class TestHelperImportFromInstalledHook:
    """The installed hook script imports its helper from its own directory."""

    def test_hook_imports_helper_in_isolated_hooks_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
        mock_repo_path: Path,
        tmp_path: Path,
    ) -> None:
        """Running the installed hook resolves the sibling helper import.

        The script is executed from an unrelated working directory with the
        exact command string the toolbox generates, so the import can only
        resolve through the hook's own directory -- which is what a literal
        ~/.claude/hooks/ download destination fails to provide for an
        isolated profile.
        """
        claude_dir = e2e_isolated_home['claude_dir']
        cmd = golden_config['command-names'][0]
        hooks_dir = claude_dir / cmd / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        assert download_hook_files(
            golden_config['hooks'],
            claude_dir,
            str(mock_repo_path / 'config.yaml'),
            hooks_base_dir=hooks_dir,
        )

        hook_script = hooks_dir / 'e2e_test_hook.py'
        config_arg = hooks_dir / _hook_file_basename('configs/e2e-hook-config.yaml')
        elsewhere = tmp_path / 'elsewhere'
        elsewhere.mkdir()

        completed = subprocess.run(  # noqa: S603
            [sys.executable, str(hook_script), str(config_arg)],
            input='{}',
            capture_output=True,
            text=True,
            cwd=str(elsewhere),
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        assert payload['helper'] == 'e2e-hook-helper-loaded'
        assert payload['config_loaded'] is True
