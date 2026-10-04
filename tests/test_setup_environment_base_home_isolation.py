"""Unit tests for keeping an isolated profile's sessions out of the base config home.

Claude Code reads the home folder's ``.claude`` -- the base profile -- as the
project ``.claude`` of a session started in the home folder and as ancestor
project memory of every session started below it. An isolated profile closes
both channels: its config.json excludes the base profile's memory files from
loading, and its launch.sh limits a session started in the home folder to the
profile's own settings sources.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import CLAUDE_MD_EXCLUDES_KEY
from scripts.setup_environment import HOME_FOLDER_SETTINGS_GUARD
from scripts.setup_environment import apply_base_config_home_exclusions
from scripts.setup_environment import base_config_home_exclusions
from scripts.setup_environment import create_launcher_script
from tests.e2e.shells import find_bash

LAUNCHER_VARIANTS = [
    pytest.param(None, 'replace', id='no-prompt'),
    pytest.param('probe-prompt.md', 'replace', id='prompt-replace'),
    pytest.param('probe-prompt.md', 'append', id='prompt-append'),
]
SOURCES_FLAGS = '"${SOURCES[@]}"'


def _patterns(home: Path) -> list[str]:
    """The three patterns an isolated profile excludes for the base config home below ``home``."""
    base = (home / '.claude').as_posix()
    return [f'{base}/CLAUDE.md', f'{base}/CLAUDE.local.md', f'{base}/rules/**']


class TestBaseConfigHomeExclusions:
    """base_config_home_exclusions() names the base profile's memory files in forward-slash form."""

    def test_names_the_memory_files_and_the_rules_of_the_base_profile(self, tmp_path: Path) -> None:
        """CLAUDE.md, CLAUDE.local.md and every rule of ~/.claude are excluded, spelled with forward slashes."""
        patterns = base_config_home_exclusions(tmp_path, links_rules_from_base=False)

        assert patterns == _patterns(tmp_path)
        assert all('\\' not in pattern for pattern in patterns)

    def test_rules_linked_from_the_base_are_the_profile_s_own(self, tmp_path: Path) -> None:
        """A profile whose rules/ links to ~/.claude/rules keeps those rules: only the memory files are excluded."""
        patterns = base_config_home_exclusions(tmp_path, links_rules_from_base=True)

        assert patterns == _patterns(tmp_path)[:2]

    def test_patterns_keep_the_home_as_spelled(self, tmp_path: Path) -> None:
        """The home directory is spelled as given, so it matches the path Claude Code builds from the same home."""
        home = tmp_path / 'Mixed Case Home'

        patterns = base_config_home_exclusions(home, links_rules_from_base=False)

        assert patterns[0] == f'{home.as_posix()}/.claude/CLAUDE.md'


class TestApplyBaseConfigHomeExclusions:
    """apply_base_config_home_exclusions() unions the patterns into user-settings.claudeMdExcludes."""

    def test_absent_user_settings_become_the_exclusions_alone(self, tmp_path: Path) -> None:
        settings, warnings, auto = apply_base_config_home_exclusions(
            None, home_dir=tmp_path, links_rules_from_base=False,
        )

        assert settings == {CLAUDE_MD_EXCLUDES_KEY: _patterns(tmp_path)}
        assert warnings == []
        assert auto == [f'user-settings.{CLAUDE_MD_EXCLUDES_KEY}: ' + ', '.join(_patterns(tmp_path))]

    def test_other_settings_are_kept_beside_the_exclusions(self, tmp_path: Path) -> None:
        settings, warnings, auto = apply_base_config_home_exclusions(
            {'theme': 'dark'}, home_dir=tmp_path, links_rules_from_base=False,
        )

        assert settings == {'theme': 'dark', CLAUDE_MD_EXCLUDES_KEY: _patterns(tmp_path)}
        assert warnings == []
        assert len(auto) == 1

    def test_declared_patterns_come_first_and_survive(self, tmp_path: Path) -> None:
        """The configuration's own exclusions stay in place and in order; the base ones follow."""
        declared = ['**/node_modules/**', _patterns(tmp_path)[2]]

        settings, warnings, auto = apply_base_config_home_exclusions(
            {CLAUDE_MD_EXCLUDES_KEY: list(declared)}, home_dir=tmp_path, links_rules_from_base=False,
        )

        assert settings[CLAUDE_MD_EXCLUDES_KEY] == [*declared, *_patterns(tmp_path)[:2]]
        assert warnings == []
        assert auto == [f'user-settings.{CLAUDE_MD_EXCLUDES_KEY}: ' + ', '.join(_patterns(tmp_path)[:2])]

    def test_declared_complete_list_adds_nothing(self, tmp_path: Path) -> None:
        """A configuration that already excludes every base file is left as it is, with no [auto] line."""
        settings, warnings, auto = apply_base_config_home_exclusions(
            {CLAUDE_MD_EXCLUDES_KEY: _patterns(tmp_path)}, home_dir=tmp_path, links_rules_from_base=False,
        )

        assert settings == {CLAUDE_MD_EXCLUDES_KEY: _patterns(tmp_path)}
        assert warnings == []
        assert auto == []

    @pytest.mark.parametrize('declared', [None, '**/node_modules/**', {'a': 1}], ids=['null', 'string', 'object'])
    def test_declared_non_list_is_replaced_with_a_warning(self, tmp_path: Path, declared: object) -> None:
        """A value that is not a list cannot be unioned: the exclusions replace it and the run says so."""
        settings, warnings, auto = apply_base_config_home_exclusions(
            {CLAUDE_MD_EXCLUDES_KEY: declared}, home_dir=tmp_path, links_rules_from_base=False,
        )

        assert settings[CLAUDE_MD_EXCLUDES_KEY] == _patterns(tmp_path)
        assert warnings == [
            (
                f'user-settings.{CLAUDE_MD_EXCLUDES_KEY} is {declared!r}, not a list of patterns; the base profile '
                'exclusions of this isolated profile replace it.'
            ),
        ]
        assert len(auto) == 1

    def test_linked_rules_leave_the_rules_pattern_out(self, tmp_path: Path) -> None:
        settings, _warnings, auto = apply_base_config_home_exclusions(
            {}, home_dir=tmp_path, links_rules_from_base=True,
        )

        assert settings[CLAUDE_MD_EXCLUDES_KEY] == _patterns(tmp_path)[:2]
        assert auto == [f'user-settings.{CLAUDE_MD_EXCLUDES_KEY}: ' + ', '.join(_patterns(tmp_path)[:2])]

    def test_the_given_dict_is_updated_in_place(self, tmp_path: Path) -> None:
        """The caller's dict is the one returned, as with the other settings injectors."""
        user_settings: dict[str, object] = {'theme': 'dark'}

        settings, _warnings, _auto = apply_base_config_home_exclusions(
            user_settings, home_dir=tmp_path, links_rules_from_base=False,
        )

        assert settings is user_settings
        assert CLAUDE_MD_EXCLUDES_KEY in user_settings


def _launch_sh(profile_dir: Path, system: str, prompt: str | None, mode: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Render launch.sh for a platform and return its text."""
    monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)
    result = create_launcher_script(profile_dir, 'iso-cmd', prompt, mode, has_profile_mcp_servers=True)
    assert result is not None
    return result[1].read_text(encoding='utf-8')


def _claude_start_lines(content: str) -> list[str]:
    """Every line of a launch.sh that starts claude."""
    return [
        line.strip() for line in content.splitlines()
        if line.strip().startswith(('exec claude ', 'claude "'))
    ]


class TestLaunchShTemplate:
    """Every launch.sh runs the home-folder guard once and hands its flags to every claude start."""

    @pytest.mark.parametrize('system', ['Windows', 'Linux', 'Darwin'])
    @pytest.mark.parametrize(('prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_guard_runs_once_before_every_claude_start(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str, prompt: str | None, mode: str,
    ) -> None:
        content = _launch_sh(tmp_path / 'iso-cmd', system, prompt, mode, monkeypatch)

        assert content.count(HOME_FOLDER_SETTINGS_GUARD) == 1
        guard_end = content.index(HOME_FOLDER_SETTINGS_GUARD) + len(HOME_FOLDER_SETTINGS_GUARD)
        assert _claude_start_lines(content[:guard_end]) == []
        starts = _claude_start_lines(content[guard_end:])
        assert starts, content
        for line in starts:
            assert f'"${{MCP_FLAGS[@]}}" {SOURCES_FLAGS} ' in line, line
            assert line.index(SOURCES_FLAGS) < line.index('"$@"'), line

    @pytest.mark.parametrize('system', ['Windows', 'Linux', 'Darwin'])
    def test_guard_compares_the_working_directory_with_the_home_by_identity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str,
    ) -> None:
        """The test is -ef, so letter case, symlinks and short names never make a home folder look like another."""
        content = _launch_sh(tmp_path / 'iso-cmd', system, None, 'replace', monkeypatch)

        assert 'if [ "$PWD" -ef "$HOME" ]; then' in content
        assert 'SOURCES=(--setting-sources user)' in content


class TestGuardUnderBash:
    """The guard sets the flags exactly when the working directory is the home folder."""

    @staticmethod
    def _flags(home: Path, cwd: Path, *, home_value: str | None = None) -> str:
        """Run the guard under bash from ``cwd`` with ``home`` as HOME and return the flags it leaves.

        Args:
            home: The home directory the launcher sees.
            cwd: The working directory of the launch.
            home_value: HOME as the shell receives it; defaults to ``home``.

        Returns:
            The space-joined SOURCES, empty when the guard set none.
        """
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        assert bash is not None
        env = dict(os.environ)
        env['HOME'] = str(home) if home_value is None else home_value
        script = 'set -euo pipefail\n' + HOME_FOLDER_SETTINGS_GUARD + 'printf "%s" "${SOURCES[*]-}"\n'
        completed = subprocess.run(
            [bash, '-c', script, 'launch.sh'], capture_output=True, text=True, check=False, timeout=60, env=env,
            cwd=cwd,
        )
        assert completed.returncode == 0, completed.stderr
        return completed.stdout

    def test_home_folder_limits_settings_to_the_profile(self, tmp_path: Path) -> None:
        assert self._flags(tmp_path, tmp_path) == '--setting-sources user'

    def test_a_project_below_the_home_keeps_its_settings(self, tmp_path: Path) -> None:
        project = tmp_path / 'work' / 'project'
        project.mkdir(parents=True)

        assert self._flags(tmp_path, project) == ''

    def test_a_directory_outside_the_home_keeps_its_settings(self, tmp_path: Path) -> None:
        home = tmp_path / 'home'
        elsewhere = tmp_path / 'elsewhere'
        home.mkdir()
        elsewhere.mkdir()

        assert self._flags(home, elsewhere) == ''

    @pytest.mark.skipif(sys.platform != 'win32', reason='letter case and short names are Windows path forms')
    def test_home_folder_is_recognized_in_every_windows_spelling(self, tmp_path: Path) -> None:
        """The home spelled in another letter case, as a short name, or in POSIX form is still the home."""
        home = tmp_path / 'Mixed Case Home'
        home.mkdir()
        buffer = ctypes.create_unicode_buffer(260)
        assert ctypes.windll.kernel32.GetShortPathNameW(str(home), buffer, 260)
        short = Path(buffer.value)
        swapped = Path(str(home).swapcase())
        assert swapped.exists()

        assert self._flags(home, swapped) == '--setting-sources user'
        assert self._flags(home, short) == '--setting-sources user'
        assert self._flags(home, home, home_value=home.as_posix()) == '--setting-sources user'
        assert self._flags(home, home, home_value=str(short)) == '--setting-sources user'
