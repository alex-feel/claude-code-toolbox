"""Tests for Step 19, which builds the uv environment of every PEP 723 hook a run wires.

The toolbox writes every Python command hook and status line as ``uv run
--no-project --python 3.12 "<hooks dir>/<file>"``; for a file with PEP 723
metadata uv builds a persistent environment on that command's first launch.
The step runs ``uv sync --script`` on the same path string after the hooks
and the profile's settings files are in place, in the environment a session
hands its hooks, so the first launch installs nothing.

tests/conftest.py replaces prepare_hook_environments for every unit test,
because the real step runs the machine's uv; these tests call the
implementation captured at import time and replace the sync runner.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts import setup_environment
from scripts.setup_environment import HOOK_LAUNCHER_PYTHON_VERSION
from scripts.setup_environment import HookEnvironmentResult
from scripts.setup_environment import _build_file_command
from scripts.setup_environment import _build_file_exec_command
from scripts.setup_environment import declares_pep723_script
from scripts.setup_environment import hook_environment_candidate_names
from scripts.setup_environment import hook_environment_sync_command
from scripts.setup_environment import hook_environment_sync_command_text
from scripts.setup_environment import hook_sync_environment
from scripts.setup_environment import wired_hook_file_names

prepare_hook_environments = setup_environment.prepare_hook_environments

PEP723_BLOCK = '# /// script\n# dependencies = ["packaging"]\n# ///\nimport packaging\n'


def _hook_config(**overrides: Any) -> dict[str, Any]:
    """Build a resolved configuration wiring a Python hook, a JavaScript hook and a status line."""
    config: dict[str, Any] = {
        'hooks': {
            'files': ['hooks/lint.py', 'configs/lint.yaml', 'hooks/notify.js', 'hooks/status.py', 'configs/status.yaml'],
            'helpers': ['hooks/shared.py'],
            'events': [
                {'event': 'PostToolUse', 'type': 'command', 'command': 'lint.py', 'config': 'lint.yaml'},
                {'event': 'PostToolUse', 'type': 'command', 'command': 'notify.js'},
                {'event': 'PreToolUse', 'type': 'prompt', 'prompt': 'Check it'},
            ],
        },
        'status-line': {'file': 'status.py', 'config': 'status.yaml'},
    }
    config.update(overrides)
    return config


class _Runner:
    """Stand in for _run_hook_environment_sync() and record every call."""

    def __init__(self, returncode: int = 0, stderr: str = '', failing: frozenset[str] = frozenset()) -> None:
        self.calls: list[tuple[list[str], Path, dict[str, str]]] = []
        self.returncode = returncode
        self.stderr = stderr
        self.failing = failing

    def __call__(self, command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(command), cwd, dict(env)))
        failed = self.returncode != 0 or any(name in command[3] for name in self.failing)
        return subprocess.CompletedProcess(command, 2 if failed else 0, '', self.stderr if failed else '')


class TestDeclaresPep723Script:
    """The opening tag of a script block decides whether uv builds an environment."""

    def test_block_present(self, tmp_path: Path) -> None:
        path = tmp_path / 'hook.py'
        path.write_text(PEP723_BLOCK, encoding='utf-8')
        assert declares_pep723_script(path) is True

    def test_block_absent(self, tmp_path: Path) -> None:
        path = tmp_path / 'hook.py'
        path.write_text('#!/usr/bin/env python3\nprint("plain")\n', encoding='utf-8')
        assert declares_pep723_script(path) is False

    def test_pyproject_block_is_not_a_script_block(self, tmp_path: Path) -> None:
        path = tmp_path / 'hook.py'
        path.write_text('# /// pyproject\n# [tool.x]\n# ///\n', encoding='utf-8')
        assert declares_pep723_script(path) is False

    def test_opening_tag_without_closing_tag_counts(self, tmp_path: Path) -> None:
        """uv run and uv sync both refuse such a file, so the sync must run and report it."""
        path = tmp_path / 'hook.py'
        path.write_text('# /// script\n# dependencies = []\nprint(1)\n', encoding='utf-8')
        assert declares_pep723_script(path) is True

    def test_tag_with_trailing_text_is_not_the_tag(self, tmp_path: Path) -> None:
        path = tmp_path / 'hook.py'
        path.write_text('# /// script extra\n# ///\n', encoding='utf-8')
        assert declares_pep723_script(path) is False

    def test_crlf_line_endings(self, tmp_path: Path) -> None:
        path = tmp_path / 'hook.py'
        path.write_bytes(b'# /// script\r\n# dependencies = []\r\n# ///\r\n')
        assert declares_pep723_script(path) is True

    def test_tag_below_the_shebang_and_docstring(self, tmp_path: Path) -> None:
        path = tmp_path / 'hook.py'
        path.write_text('#!/usr/bin/env python3\n"""Doc."""\n\n' + PEP723_BLOCK, encoding='utf-8')
        assert declares_pep723_script(path) is True

    def test_unreadable_file_warns_and_is_false(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = tmp_path / 'hook.py'
        path.write_bytes(b'\xff\xfe# /// script\n')
        assert declares_pep723_script(path) is False
        assert 'Cannot read' in capsys.readouterr().out

    def test_missing_file_warns_and_is_false(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert declares_pep723_script(tmp_path / 'absent.py') is False
        assert 'Cannot read' in capsys.readouterr().out


class TestHookEnvironmentCandidateNames:
    """Only the files the written commands launch through uv are candidates."""

    def test_python_command_hooks_and_status_line_file(self) -> None:
        assert hook_environment_candidate_names(_hook_config()) == ['lint.py', 'status.py']

    def test_config_files_are_arguments_not_launched(self) -> None:
        """A Python config file is passed as an argument and never launched."""
        config = _hook_config()
        config['hooks']['files'] = ['hooks/lint.py', 'configs/settings.py', 'hooks/status.py']
        config['hooks']['events'] = [
            {'event': 'PostToolUse', 'type': 'command', 'command': 'lint.py', 'config': 'settings.py'},
        ]
        config['status-line'] = {'file': 'status.py', 'config': 'settings.py'}
        assert hook_environment_candidate_names(config) == ['lint.py', 'status.py']

    def test_unlisted_command_is_left_out(self) -> None:
        config = _hook_config()
        config['hooks']['events'].append({'event': 'Stop', 'type': 'command', 'command': 'elsewhere.py'})
        assert hook_environment_candidate_names(config) == ['lint.py', 'status.py']

    def test_each_file_once(self) -> None:
        config = _hook_config()
        config['hooks']['events'].append({'event': 'Stop', 'type': 'command', 'command': 'lint.py'})
        assert hook_environment_candidate_names(config) == ['lint.py', 'status.py']

    def test_pyw_and_query_parameters(self) -> None:
        config = _hook_config()
        config['hooks']['files'] = ['hooks/win.pyw?ref=main']
        config['hooks']['events'] = [{'event': 'Stop', 'type': 'command', 'command': 'win.pyw?ref=main'}]
        del config['status-line']
        assert hook_environment_candidate_names(config) == ['win.pyw']

    def test_no_hooks(self) -> None:
        assert hook_environment_candidate_names({}) == []
        assert hook_environment_candidate_names({'hooks': None, 'status-line': None}) == []

    def test_wired_names_keep_configs_unless_launched_only(self) -> None:
        config = _hook_config()
        assert wired_hook_file_names(config) == ['lint.py', 'lint.yaml', 'notify.js', 'status.py', 'status.yaml']
        assert wired_hook_file_names(config, launched_only=True) == ['lint.py', 'notify.js', 'status.py']


class TestHookEnvironmentSyncCommand:
    """The sync names the environment the written command names."""

    def test_sync_path_equals_the_written_command_path(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / 'profile' / 'hooks'
        hook_path = (hooks_dir / 'lint.py').as_posix()
        assert _build_file_command('hooks/lint.py?ref=x', None, hooks_dir) == (
            f'uv run --no-project --python {HOOK_LAUNCHER_PYTHON_VERSION} "{hook_path}"'
        )
        executable, exec_args = _build_file_exec_command('lint.py', None, hooks_dir)
        assert (executable, exec_args) == ('uv', ['run', '--no-project', '--python', HOOK_LAUNCHER_PYTHON_VERSION, hook_path])
        assert hook_environment_sync_command(hook_path) == [
            'uv', 'sync', '--script', hook_path, '--python', HOOK_LAUNCHER_PYTHON_VERSION,
        ]
        assert hook_environment_sync_command(hook_path, 'C:/tools/uv.exe')[0] == 'C:/tools/uv.exe'

    def test_text_form_quotes_the_path_only(self) -> None:
        assert hook_environment_sync_command_text('C:/Users/Jo Doe/.claude/hooks/a.py') == (
            f'uv sync --script "C:/Users/Jo Doe/.claude/hooks/a.py" --python {HOOK_LAUNCHER_PYTHON_VERSION}'
        )

    def test_built_command_pattern_follows_the_launcher_version(self, tmp_path: Path) -> None:
        """The pattern that recognizes written commands names the same version as the launcher."""
        command = _build_file_command('lint.py', 'lint.yaml', tmp_path / 'hooks')
        assert setup_environment._BUILT_FILE_COMMAND_PATTERN.fullmatch(command)


class TestHookSyncEnvironment:
    """The sync runs in the environment a session hands its hooks."""

    def test_os_variables_apply_over_the_base_and_nulls_remove(self) -> None:
        env = hook_sync_environment(
            {'UV_CACHE_DIR': '/cache', 'GONE': None}, [], lockfile_present=True, base={'GONE': 'x', 'KEEP': 'y'},
        )
        assert env == {'UV_CACHE_DIR': '/cache', 'KEEP': 'y'}

    def test_settings_files_apply_in_order_over_os_variables(self, tmp_path: Path) -> None:
        settings = tmp_path / 'settings.json'
        settings.write_text(
            json.dumps({'env': {'UV_INDEX_URL': 'https://a', 'UV_CACHE_DIR': '/from-settings'}}), encoding='utf-8',
        )
        config = tmp_path / 'config.json'
        config.write_text(json.dumps({'env': {'UV_INDEX_URL': 'https://b', 'NUMBER': 1, 'NULL': None}}), encoding='utf-8')
        env = hook_sync_environment(
            {'UV_CACHE_DIR': '/from-os'}, [settings, config], lockfile_present=True, base={},
        )
        assert env == {'UV_CACHE_DIR': '/from-settings', 'UV_INDEX_URL': 'https://b'}

    def test_missing_invalid_and_envless_settings_files_add_nothing(self, tmp_path: Path) -> None:
        invalid = tmp_path / 'invalid.json'
        invalid.write_text('{not json', encoding='utf-8')
        no_env = tmp_path / 'no-env.json'
        no_env.write_text(json.dumps({'model': 'opus', 'env': 'not an object'}), encoding='utf-8')
        env = hook_sync_environment({}, [tmp_path / 'absent.json', invalid, no_env], lockfile_present=True, base={'A': '1'})
        assert env == {'A': '1'}

    def test_lock_settings_dropped_without_a_lockfile(self) -> None:
        base = {'UV_LOCKED': '1', 'UV_FROZEN': '1', 'UV_CACHE_DIR': '/c'}
        assert hook_sync_environment({}, [], lockfile_present=False, base=base) == {'UV_CACHE_DIR': '/c'}
        assert hook_sync_environment({}, [], lockfile_present=True, base=base) == base

    def test_lock_settings_from_the_settings_env_are_dropped_too(self, tmp_path: Path) -> None:
        config = tmp_path / 'config.json'
        config.write_text(json.dumps({'env': {'UV_LOCKED': '1'}}), encoding='utf-8')
        assert hook_sync_environment({}, [config], lockfile_present=False, base={}) == {}
        assert hook_sync_environment({}, [config], lockfile_present=True, base={}) == {'UV_LOCKED': '1'}

    def test_process_environment_is_the_default_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('CCT_HOOK_ENV_PROBE', 'present')
        env = hook_sync_environment({}, [], lockfile_present=True)
        assert env['CCT_HOOK_ENV_PROBE'] == 'present'


class TestRunHookEnvironmentSync:
    """The runner hands uv the hooks directory and the composed environment."""

    def test_runs_through_run_command_in_the_hooks_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        recorded: dict[str, Any] = {}

        def fake_run_command(cmd: list[str], capture_output: bool = True, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded.update(cmd=cmd, capture_output=capture_output, **kwargs)
            return subprocess.CompletedProcess(cmd, 0, '', '')

        monkeypatch.setattr(setup_environment, 'run_command', fake_run_command)
        command = hook_environment_sync_command('/h/a.py')
        setup_environment._run_hook_environment_sync(command, cwd=tmp_path, env={'X': '1'})
        assert recorded == {'cmd': command, 'capture_output': False, 'cwd': str(tmp_path), 'env': {'X': '1'}}


class TestPrepareHookEnvironments:
    """The step syncs every PEP 723 candidate and reports the rest."""

    @pytest.fixture
    def hooks_dir(self, tmp_path: Path) -> Path:
        directory = tmp_path / 'profile' / 'hooks'
        directory.mkdir(parents=True)
        (directory / 'lint.py').write_text(PEP723_BLOCK, encoding='utf-8')
        (directory / 'status.py').write_text('print("plain")\n', encoding='utf-8')
        (directory / 'notify.js').write_text('console.log(1)\n', encoding='utf-8')
        return directory

    def test_syncs_pep723_files_and_skips_plain_ones(
        self, hooks_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        runner = _Runner()
        monkeypatch.setattr(setup_environment, '_run_hook_environment_sync', runner)
        monkeypatch.setenv('UV_LOCKED', '1')
        config_json = tmp_path / 'profile' / 'config.json'
        config_json.write_text(json.dumps({'env': {'UV_CACHE_DIR': '/profile-cache'}}), encoding='utf-8')

        result = prepare_hook_environments(
            _hook_config(), hooks_dir, os_env_variables={'HTTPS_PROXY': 'http://proxy:3128'}, settings_files=[config_json],
            uv_executable='uv',
        )

        assert result == HookEnvironmentResult(['lint.py'], ['status.py'], [])
        hook_path = (hooks_dir / 'lint.py').as_posix()
        assert [call[0] for call in runner.calls] == [hook_environment_sync_command(hook_path, 'uv')]
        command, cwd, env = runner.calls[0]
        assert cwd == hooks_dir
        assert env['UV_CACHE_DIR'] == '/profile-cache'
        assert env['HTTPS_PROXY'] == 'http://proxy:3128'
        assert 'UV_LOCKED' not in env, 'no lockfile beside lint.py, so uv run would ignore the setting'
        out = capsys.readouterr().out
        assert 'Preparing the environment of lint.py' in out
        assert 'status.py: no PEP 723 metadata' in out

    def test_lockfile_keeps_the_lock_settings(self, hooks_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        runner = _Runner()
        monkeypatch.setattr(setup_environment, '_run_hook_environment_sync', runner)
        monkeypatch.setenv('UV_LOCKED', '1')
        (hooks_dir / 'lint.py.lock').write_text('version = 1\n', encoding='utf-8')
        prepare_hook_environments(_hook_config(), hooks_dir, os_env_variables={}, settings_files=[], uv_executable='uv')
        assert runner.calls[0][2]['UV_LOCKED'] == '1'

    def test_failure_is_recorded_and_the_other_files_still_run(
        self, hooks_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        (hooks_dir / 'status.py').write_text(PEP723_BLOCK, encoding='utf-8')
        runner = _Runner(stderr='error: No solution found', failing=frozenset({'lint.py'}))
        monkeypatch.setattr(setup_environment, '_run_hook_environment_sync', runner)

        result = prepare_hook_environments(
            _hook_config(), hooks_dir, os_env_variables={}, settings_files=[], uv_executable='uv',
        )

        assert result.failed == [(hooks_dir / 'lint.py').as_posix()]
        assert result.prepared == ['status.py']
        assert len(runner.calls) == 2
        captured = capsys.readouterr()
        assert 'No solution found' in captured.err
        assert 'Failed to prepare the environment of lint.py (exit code 2)' in captured.err

    def test_missing_wired_file_is_a_failure(
        self, hooks_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        runner = _Runner()
        monkeypatch.setattr(setup_environment, '_run_hook_environment_sync', runner)
        (hooks_dir / 'lint.py').unlink()
        result = prepare_hook_environments(
            _hook_config(), hooks_dir, os_env_variables={}, settings_files=[], uv_executable='uv',
        )
        assert result.failed == [(hooks_dir / 'lint.py').as_posix()]
        assert result.skipped == ['status.py']
        assert runner.calls == []
        assert 'Hook file not found' in capsys.readouterr().err

    def test_uv_missing_fails_every_candidate_without_running(
        self, hooks_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        runner = _Runner()
        monkeypatch.setattr(setup_environment, '_run_hook_environment_sync', runner)
        result = prepare_hook_environments(
            _hook_config(), hooks_dir, os_env_variables={}, settings_files=[], uv_executable=None,
        )
        assert result.failed == [(hooks_dir / 'lint.py').as_posix(), (hooks_dir / 'status.py').as_posix()]
        assert runner.calls == []
        assert 'uv is not on PATH' in capsys.readouterr().err

    def test_no_candidates(self, hooks_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        runner = _Runner()
        monkeypatch.setattr(setup_environment, '_run_hook_environment_sync', runner)
        result = prepare_hook_environments({'hooks': {'files': ['hooks/notify.js'], 'events': [
            {'event': 'Stop', 'type': 'command', 'command': 'notify.js'},
        ]}}, hooks_dir, os_env_variables={}, settings_files=[], uv_executable='uv')
        assert result == HookEnvironmentResult([], [], [])
        assert result.ran is False
        assert runner.calls == []
        assert 'No Python hooks to prepare environments for' in capsys.readouterr().out

    def test_completion_line_counts(self) -> None:
        """The closing summary counts what was prepared and skipped; a failure ends the run in the error block."""
        assert HookEnvironmentResult(['a.py'], ['b.py'], []).completion_line() == '1 prepared, 1 without PEP 723 metadata'
        assert HookEnvironmentResult(['a.py', 'b.py'], [], []).completion_line() == '2 prepared'
        assert HookEnvironmentResult([], [], ['/h/c.py']).ran is False


class TestRunHookEnvironmentStep:
    """Step 19 prints its line and skips when the hooks never landed."""

    def test_runs_the_step(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr(setup_environment, 'prepare_hook_environments', prepare_hook_environments)
        runner = _Runner()
        monkeypatch.setattr(setup_environment, '_run_hook_environment_sync', runner)
        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()
        (hooks_dir / 'lint.py').write_text(PEP723_BLOCK, encoding='utf-8')
        (hooks_dir / 'status.py').write_text(PEP723_BLOCK, encoding='utf-8')

        result = setup_environment.run_hook_environment_step(
            _hook_config(), hooks_dir, os_env_variables={}, settings_files=[], uv_executable='uv', download_failed=False,
        )

        assert result.prepared == ['lint.py', 'status.py']
        assert 'Step 19: Preparing hook environments...' in capsys.readouterr().out

    def test_skips_when_the_download_failed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(setup_environment, 'prepare_hook_environments', prepare_hook_environments)
        runner = _Runner()
        monkeypatch.setattr(setup_environment, '_run_hook_environment_sync', runner)
        result = setup_environment.run_hook_environment_step(
            _hook_config(), tmp_path, os_env_variables={}, settings_files=[], uv_executable='uv', download_failed=True,
        )
        assert result == HookEnvironmentResult([], [], [])
        assert runner.calls == []
        out = capsys.readouterr().out
        assert 'Step 19: Preparing hook environments...' in out
        assert 'Skipped: the hook files failed to download' in out


def _plan_from(config: dict[str, Any]) -> setup_environment.InstallationPlan:
    args = MagicMock()
    args.skip_install = True
    return setup_environment.collect_installation_plan(
        config=config,
        config_source='probe.yaml',
        config_name='probe',
        config_version=None,
        inheritance_chain=[setup_environment.InheritanceChainEntry('probe.yaml', 'local', 'probe')],
        args=args,
    )


class TestInstallationSummary:
    """The summary names the candidates before consent; the step decides per file after download."""

    def test_plan_lists_the_uv_launched_files(self) -> None:
        plan = _plan_from({'name': 'probe', **_hook_config()})
        assert plan.hook_environments == ['lint.py', 'status.py']

    def test_summary_row(self) -> None:
        plan = _plan_from({'name': 'probe', **_hook_config()})
        output = io.StringIO()
        setup_environment.display_installation_summary(plan, output=output)
        assert (
            '* Hook environments: lint.py, status.py '
            '(uv builds an environment after download for each file with PEP 723 metadata)'
        ) in output.getvalue()

    def test_no_row_without_uv_launched_files(self) -> None:
        plan = _plan_from({'name': 'probe', 'hooks': {'files': ['hooks/notify.js'], 'events': [
            {'event': 'Stop', 'type': 'command', 'command': 'notify.js'},
        ]}})
        assert plan.hook_environments == []
        output = io.StringIO()
        setup_environment.display_installation_summary(plan, output=output)
        assert 'Hook environments' not in output.getvalue()
