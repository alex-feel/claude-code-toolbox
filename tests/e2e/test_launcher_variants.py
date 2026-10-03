"""E2E tests for the content and runtime output of every launcher variant.

These tests verify that each generated launcher variant starts Claude Code
directly, and that an update-available.json left in the profile directory
changes neither setup nor what the freshly generated launcher prints.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from unittest.mock import patch

if TYPE_CHECKING:
    from unittest.mock import MagicMock

import pytest

from scripts import setup_environment
from scripts.setup_environment import create_launcher_script
from tests.conftest import empty_mcp_stats
from tests.e2e.test_launcher_scripts import _find_bash
from tests.e2e.validators import UPDATE_CHECK_FRAGMENTS
from tests.e2e.validators import validate_launcher_has_no_update_check
from tests.e2e.validators import validate_launcher_script
from tests.e2e.validators import validate_manifest

# Launcher variants create_launcher_script() generates: no system prompt, and
# a system prompt in each mode.
LAUNCHER_VARIANTS = [
    pytest.param(None, 'replace', id='no-prompt'),
    pytest.param('probe-prompt.md', 'replace', id='prompt-replace'),
    pytest.param('probe-prompt.md', 'append', id='prompt-append'),
]


class TestLauncherVariantsStartClaudeDirectly:
    """Every generated launcher variant starts Claude Code with no update check.

    platform.system() is the only platform detection create_launcher_script()
    uses, so mocking it generates the Windows and the Unix file sets on every
    CI runner.
    """

    @pytest.mark.parametrize(
        ('system', 'expected_files'),
        [
            pytest.param('Windows', {'start.ps1', 'start.cmd', 'launch.sh'}, id='windows'),
            pytest.param('Linux', {'launch.sh'}, id='linux'),
            pytest.param('Darwin', {'launch.sh'}, id='macos'),
        ],
    )
    @pytest.mark.parametrize(('system_prompt_file', 'mode'), LAUNCHER_VARIANTS)
    def test_generated_launchers_carry_no_update_check(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        expected_files: set[str],
        system_prompt_file: str | None,
        mode: str,
    ) -> None:
        """No generated launcher file references an update marker or prints a notice."""
        cmd = 'variant-probe'
        profile_dir = e2e_isolated_home['claude_dir'] / cmd
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)

        result = create_launcher_script(
            config_base_dir=profile_dir,
            command_name=cmd,
            system_prompt_file=system_prompt_file,
            mode=mode,
            has_profile_mcp_servers=False,
        )
        assert result is not None

        generated = {path.name: path for path in profile_dir.iterdir() if path.is_file()}
        assert set(generated) == expected_files
        errors = [
            error
            for path in generated.values()
            for error in validate_launcher_has_no_update_check(path)
        ]
        assert not errors, '\n'.join(errors)


def _write_stub_claude(stub_dir: Path, args_file: Path) -> None:
    """Write a stub claude that reports a version and records its arguments."""
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / 'claude'
    stub.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "--version" ]; then echo "2.1.0 (Claude Code)"; exit 0; fi\n'
        'printf \'%s\\n\' "$@" > "' + args_file.as_posix() + '"\n',
        encoding='utf-8',
        newline='\n',
    )
    stub.chmod(0o755)


class TestLeftoverUpdateMarker:
    """A leftover update-available.json does not change the profile launcher.

    The file is left in the profile directory before setup runs; setup leaves
    it in place, and the freshly generated launcher starts Claude Code without
    printing any notice.
    """

    @pytest.mark.parametrize(
        ('command_defaults', 'prompt_name'),
        [
            pytest.param({}, None, id='no-prompt'),
            pytest.param(
                {'system-prompt': 'prompts/marker-probe.md', 'mode': 'replace'},
                'marker-probe.md',
                id='prompt-replace',
            ),
            pytest.param(
                {'system-prompt': 'prompts/marker-probe.md', 'mode': 'append'},
                'marker-probe.md',
                id='prompt-append',
            ),
        ],
    )
    @patch('scripts.setup_environment.load_config_from_source')
    @patch('scripts.setup_environment.validate_all_config_files')
    @patch('scripts.setup_environment.install_claude', return_value=True)
    @patch('scripts.setup_environment.install_dependencies', return_value=[])
    @patch('scripts.setup_environment.process_resources')
    @patch('scripts.setup_environment.process_skills')
    @patch('scripts.setup_environment.configure_all_mcp_servers')
    @patch('scripts.setup_environment.set_all_os_env_variables', return_value=True)
    @patch('scripts.setup_environment.generate_env_loader_files', return_value={})
    @patch('scripts.setup_environment.handle_resource')
    @patch('scripts.setup_environment.is_admin', return_value=True)
    def test_fresh_launcher_ignores_leftover_marker(
        self,
        mock_is_admin: MagicMock,
        mock_handle_resource: MagicMock,
        mock_env_loader: MagicMock,
        mock_os_env: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        command_defaults: dict[str, str],
        prompt_name: str | None,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Setup and the launcher it writes print no update notice."""
        del mock_is_admin, mock_env_loader, mock_os_env, mock_skills
        del mock_resources, mock_deps, mock_install
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        local_bin = e2e_isolated_home['local_bin']
        cmd = 'marker-probe'
        profile_dir = claude_dir / cmd
        profile_dir.mkdir(parents=True)

        marker_path = profile_dir / 'update-available.json'
        marker_content = json.dumps({
            'installed_version': '1.0.0',
            'available_version': '1.1.0',
            'checked_at': '2026-01-01T00:00:00+00:00',
            'config_source_url': 'https://example.com/marker-probe.yaml',
        })
        marker_path.write_text(marker_content, encoding='utf-8')

        def write_prompt(_source: str, destination: Path, *_args: object, **_kwargs: object) -> bool:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text('Probe system prompt.\n', encoding='utf-8')
            return True

        mock_handle_resource.side_effect = write_prompt
        config: dict[str, Any] = {
            'name': 'Marker Probe',
            'version': '1.0.0',
            'command-names': [cmd],
            'command-defaults': command_defaults,
            'user-settings': {'theme': 'dark'},
        }
        mock_load.return_value = (config, 'marker-probe.yaml')
        mock_validate.return_value = (True, [])
        mock_mcp.return_value = (True, [], empty_mcp_stats())
        find_other_command = setup_environment.find_command

        def find_command(name: str) -> str | None:
            return '/usr/bin/claude' if name == 'claude' else find_other_command(name)

        with patch('sys.argv', ['setup_environment.py', 'marker-probe', '--yes', '--skip-install']), \
             patch.object(setup_environment, 'find_command', side_effect=find_command), \
             patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        setup_output = capsys.readouterr()
        for fragment in ('update marker', *UPDATE_CHECK_FRAGMENTS):
            assert fragment not in setup_output.out + setup_output.err

        assert marker_path.read_text(encoding='utf-8') == marker_content, (
            'setup must leave a file it does not own in place'
        )
        if prompt_name is not None:
            assert (profile_dir / 'prompts' / prompt_name).exists()

        errors = validate_manifest(profile_dir / 'manifest.json', config)
        launcher_files = [
            profile_dir / name
            for name in ('launch.sh', 'start.ps1', 'start.cmd')
            if (profile_dir / name).exists()
        ]
        wrappers = sorted(local_bin.glob(f'{cmd}*'))
        assert wrappers, 'setup must register the global command'
        for path in launcher_files + wrappers:
            errors.extend(validate_launcher_script(path, cmd))
        assert not errors, '\n'.join(errors)

        bash = _find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        stub_dir = home / 'stub-bin'
        args_file = stub_dir / 'invoked.txt'
        _write_stub_claude(stub_dir, args_file)
        env = dict(os.environ)
        env['HOME'] = str(home)
        env['PATH'] = f'{stub_dir}{os.pathsep}' + env.get('PATH', '')

        completed = subprocess.run(
            [bash, str(profile_dir / 'launch.sh'), '--probe-arg'],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env=env,
        )
        assert completed.returncode == 0, (
            f'launch.sh failed:\nstdout: {completed.stdout}\nstderr: {completed.stderr}'
        )
        launcher_output = completed.stdout + completed.stderr
        for fragment in UPDATE_CHECK_FRAGMENTS:
            assert fragment not in launcher_output, (
                f'launcher printed {fragment!r}:\n{launcher_output}'
            )
        assert args_file.exists(), 'stub claude was never invoked'
        invoked_args = args_file.read_text(encoding='utf-8').splitlines()
        assert '--probe-arg' in invoked_args
        assert '--settings' in invoked_args
