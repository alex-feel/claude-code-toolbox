"""E2E tests for what an isolated install writes to keep its sessions out of the base config home.

Claude Code reads the home folder's ``.claude`` -- the base profile -- as the
project ``.claude`` of a session started in the home folder and as ancestor
project memory of every session started below it. An isolated install
therefore puts the base profile's memory files into ``claudeMdExcludes`` of
its ``config.json`` (unioned with the exclusions the configuration declares,
without the rules when the profile's ``rules/`` is a link to the base rules,
and on Windows under the home's 8.3 short spelling as well when Windows gives
one that differs), names the injected value with the ``[auto]`` marker before
consent, and writes launchers that limit a session started in the home folder
to the profile's own settings sources. A base install writes none of this.

Every test runs main() against YAML files on disk in an isolated home; only
network access, the Claude Code binary, MCP registration, OS-level variables
and the Windows PATH registry are replaced. The expected patterns come from
``base_home_support``, which asks the Windows API for the short spelling
itself, so they share no code with the toolbox.
"""

from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from scripts.setup_environment import CLAUDE_MD_EXCLUDES_KEY
from tests.e2e.base_home_support import base_exclusions
from tests.e2e.base_home_support import short_spelling
from tests.e2e.profile_support import home_state
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config
from tests.e2e.validators import validate_launcher_limits_home_folder_settings

SKIP = ['--skip-install', '--no-admin']
AUTO_LINE = f'[auto] user-settings.{CLAUDE_MD_EXCLUDES_KEY}: '


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the resources they install beside them."""
    directory = tmp_path / 'configs'
    for relative, content in (
        ('rules/rule.md', '# rule\n'),
        ('prompts/prompt.md', '# prompt\n'),
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _team(user_settings: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """A configuration with a rule, so a profile holds a rules/ entry to link."""
    config: dict[str, Any] = {'name': 'Team', 'rules': ['rules/rule.md'], 'user-settings': {'theme': 'dark'}}
    if user_settings is not None:
        config['user-settings'] = user_settings
    config.update(extra)
    return config


def _patterns(home: Path, *, with_rules: bool = True) -> list[str]:
    """The exclusions an isolated profile of ``home`` carries: the long spelling's, then on Windows the short spelling's."""
    return base_exclusions(home, with_rules=with_rules)


def _config_json(profile_dir: Path) -> dict[str, Any]:
    content: dict[str, Any] = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
    return content


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    return (captured.out + captured.err).replace('\r\n', '\n')


def _auto_line_patterns(output: str) -> list[str]:
    """The patterns the summary's ``[auto] user-settings.claudeMdExcludes`` line names, in order."""
    for line in output.splitlines():
        if AUTO_LINE in line:
            return re.sub(r'\x1b\[[0-9;]*m', '', line.split(AUTO_LINE, 1)[1]).split(', ')
    return []


@pytest.mark.usefixtures('e2e_isolated_home')
class TestIsolatedConfigJsonExcludesTheBaseConfigHome:
    """config.json of an isolated profile excludes the base profile's CLAUDE.md, CLAUDE.local.md and rules."""

    def test_install_writes_the_exclusions_and_marks_them_auto(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'team.yaml', _team())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'work-1']) == 0

        settings = _config_json(home / '.claude' / 'work-1')
        assert settings[CLAUDE_MD_EXCLUDES_KEY] == _patterns(home)
        assert settings['theme'] == 'dark'
        assert AUTO_LINE + ', '.join(_patterns(home)) in _output(capsys)

    def test_declared_exclusions_stay_first_and_the_auto_line_names_only_the_added_ones(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        declared = ['**/node_modules/**', _patterns(home)[0]]
        cfg = write_config(configs, 'team.yaml', _team({CLAUDE_MD_EXCLUDES_KEY: declared}))

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'work-1']) == 0

        assert _config_json(home / '.claude' / 'work-1')[CLAUDE_MD_EXCLUDES_KEY] == [*declared, *_patterns(home)[1:]]
        assert AUTO_LINE + ', '.join(_patterns(home)[1:]) in _output(capsys)

    def test_declared_non_list_is_replaced_with_a_warning(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'team.yaml', _team({CLAUDE_MD_EXCLUDES_KEY: '**/node_modules/**'}))

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'work-1']) == 0

        assert _config_json(home / '.claude' / 'work-1')[CLAUDE_MD_EXCLUDES_KEY] == _patterns(home)
        output = _output(capsys)
        assert f"user-settings.{CLAUDE_MD_EXCLUDES_KEY} is '**/node_modules/**', not a list of patterns" in output
        assert AUTO_LINE in output

    def test_dry_run_shows_the_auto_line_and_writes_nothing(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'team.yaml', _team())
        before = home_state(home)

        assert run_main([str(cfg), *SKIP, '--dry-run', '--command-names', 'work-1']) == 0

        assert AUTO_LINE + ', '.join(_patterns(home)) in _output(capsys)
        assert home_state(home) == before

    def test_profile_rerun_keeps_the_exclusions(self, e2e_isolated_home: dict[str, Path], configs: Path) -> None:
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'team.yaml', _team())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'work-1']) == 0

        assert run_main(['--profile', 'work-1', *SKIP, '--yes']) == 0

        assert _config_json(home / '.claude' / 'work-1')[CLAUDE_MD_EXCLUDES_KEY] == _patterns(home)

    def test_relocated_profile_excludes_the_base_config_home_and_never_itself(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """A profile moved by user-settings.env CLAUDE_CONFIG_DIR still excludes ~/.claude, never its own files."""
        home = e2e_isolated_home['home']
        profile_dir = home.parent / 'elsewhere' / 'work-1'
        cfg = write_config(configs, 'team.yaml', _team({'env': {'CLAUDE_CONFIG_DIR': profile_dir.as_posix()}}))

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'work-1']) == 0

        patterns = _config_json(profile_dir)[CLAUDE_MD_EXCLUDES_KEY]
        assert patterns == _patterns(home)
        assert not any(profile_dir.as_posix() in pattern for pattern in patterns)

    def test_rules_linked_from_the_base_keep_the_base_rules(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile whose rules/ links to ~/.claude/rules excludes the memory files only: the rules are its own."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'team.yaml', _team())
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'work-2', '--link-dirs', 'rules', '--link-from', 'base',
        ]) == 0

        assert _config_json(home / '.claude' / 'work-2')[CLAUDE_MD_EXCLUDES_KEY] == _patterns(home, with_rules=False)
        assert AUTO_LINE + ', '.join(_patterns(home, with_rules=False)) in _output(capsys)

    def test_rules_linked_from_another_profile_still_exclude_the_base_rules(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'team.yaml', _team())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'team-2', '--link-dirs', 'rules', '--link-from', 'team-1',
        ]) == 0

        assert _config_json(home / '.claude' / 'team-2')[CLAUDE_MD_EXCLUDES_KEY] == _patterns(home)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestShortHomeSpellingExclusions:
    """On Windows config.json also excludes the base memory under the home's 8.3 short spelling.

    Windows spells a home whose account name is longer than eight characters
    short in %TEMP% and %TMP% (``C:\\Users\\CHRIST~1\\...``), and Claude Code
    builds the ancestor paths it matches the exclusions against from such a
    working directory as spelled; the isolated home of these tests lies below
    pytest's temporary directory, whose components are longer than eight
    characters, so Windows gives it a differing short spelling.
    """

    @pytest.mark.skipif(sys.platform != 'win32', reason='8.3 short names are a Windows path form')
    def test_install_writes_the_short_spelling_s_patterns_after_the_long_ones(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        short = short_spelling(home)
        if short is None:
            pytest.skip('the volume creates no 8.3 names for the isolated home')
        cfg = write_config(configs, 'team.yaml', _team())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'work-1']) == 0

        patterns = _config_json(home / '.claude' / 'work-1')[CLAUDE_MD_EXCLUDES_KEY]
        assert patterns == _patterns(home)
        assert len(patterns) == 6
        short_base = (short / '.claude').as_posix()
        assert fnmatch.fnmatchcase(f'{short_base}/CLAUDE.md', patterns[3]), patterns[3]
        assert fnmatch.fnmatchcase(f'{short_base}/CLAUDE.md'.lower(), patterns[3]), patterns[3]
        assert fnmatch.fnmatchcase(f'{short_base}/CLAUDE.local.md', patterns[4]), patterns[4]
        assert fnmatch.fnmatchcase(f'{short_base}/rules/team/style.md', patterns[5]), patterns[5]
        assert not fnmatch.fnmatchcase(f'{short_base}/work-1/CLAUDE.md', patterns[3]), patterns[3]
        assert not fnmatch.fnmatchcase(f'{short_base}/work-1/rules/own.md', patterns[5]), patterns[5]
        assert _auto_line_patterns(_output(capsys)) == patterns

    @pytest.mark.skipif(sys.platform != 'win32', reason='8.3 short names are a Windows path form')
    @pytest.mark.parametrize('windows_gives', ['the long spelling', 'nothing'])
    def test_a_home_without_a_differing_short_spelling_gets_the_long_patterns_only(
        self,
        e2e_isolated_home: dict[str, Path],
        configs: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        windows_gives: str,
    ) -> None:
        """A volume without 8.3 names gives the long spelling back and a failed call gives nothing; neither adds patterns."""
        home = e2e_isolated_home['home']
        short = (lambda path: path) if windows_gives == 'the long spelling' else (lambda _path: None)
        monkeypatch.setattr(setup_environment, '_windows_short_path', short)
        cfg = write_config(configs, 'team.yaml', _team())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'work-1']) == 0

        patterns = _config_json(home / '.claude' / 'work-1')[CLAUDE_MD_EXCLUDES_KEY]
        assert patterns == _patterns(home)[:3]
        assert len(patterns) == 3
        assert _auto_line_patterns(_output(capsys)) == patterns

    @pytest.mark.skipif(sys.platform == 'win32', reason='the other platforms give a home no second spelling')
    def test_other_platforms_write_the_long_spelling_s_patterns_only(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'team.yaml', _team())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'work-1']) == 0

        patterns = _config_json(home / '.claude' / 'work-1')[CLAUDE_MD_EXCLUDES_KEY]
        assert patterns == _patterns(home)
        assert len(patterns) == 3
        assert _auto_line_patterns(_output(capsys)) == patterns


@pytest.mark.usefixtures('e2e_isolated_home')
class TestBaseInstallIsUnchanged:
    """A base install excludes nothing: ~/.claude is its own config home."""

    def test_base_settings_carry_no_exclusions_and_no_auto_line(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'team.yaml', _team())

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        settings = json.loads((e2e_isolated_home['claude_dir'] / 'settings.json').read_text(encoding='utf-8'))
        assert CLAUDE_MD_EXCLUDES_KEY not in settings
        assert AUTO_LINE not in _output(capsys)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestLaunchersWrittenByMainLimitHomeFolderSettings:
    """Every launcher main() writes passes the home-folder settings guard check, in every prompt variant."""

    @pytest.mark.parametrize(
        'command_defaults',
        [None, {'system-prompt': 'prompts/prompt.md'}, {'system-prompt': 'prompts/prompt.md', 'mode': 'append'}],
        ids=['no-prompt', 'prompt-replace', 'prompt-append'],
    )
    def test_launch_sh_limits_settings_in_the_home_folder(
        self, e2e_isolated_home: dict[str, Path], configs: Path, command_defaults: dict[str, str] | None,
    ) -> None:
        extra = {'command-defaults': command_defaults} if command_defaults else {}
        cfg = write_config(configs, 'team.yaml', _team(**extra))

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'work-1']) == 0

        launch_sh = e2e_isolated_home['claude_dir'] / 'work-1' / 'launch.sh'
        errors = validate_launcher_limits_home_folder_settings(launch_sh)
        assert not errors, '\n'.join(errors)
