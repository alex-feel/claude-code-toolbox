"""Tests for re-rooting base config-home paths into an isolated profile.

An isolated run rewrites every files-to-download destination, dependency
command and TILDE_EXPANSION_KEYS settings value that names the base config
home (~/.claude in any spelling) or a ~/.claude.json sibling to the same
path inside its profile directory. ConfigHomeReroot is the one function
that does the rewriting; the installer, the manifest records, the
machine-wide summary rows, the linked-entry split of a dependent's run and
the deselection mirror all consume what it rewrote. A base run builds no
rerooter, so nothing changes there.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment
from setup_environment import ConfigHomeReroot
from setup_environment import RerootedPath

PROFILE = 'team-1'


def _reroot(home: Path, profile_dir: Path | None = None, *, others: tuple[str, ...] = ()) -> ConfigHomeReroot:
    """Build a rerooter for a profile below the given home (the default layout unless profile_dir is given)."""
    directory = profile_dir if profile_dir is not None else home / '.claude' / PROFILE
    return ConfigHomeReroot(directory, home, [PROFILE, *others])


class TestRewriteSpellings:
    """Every spelling of the base config home is rewritten; everything else stays."""

    @pytest.mark.parametrize(
        ('value', 'expected'),
        [
            ('~/.claude/CLAUDE.md', f'~/.claude/{PROFILE}/CLAUDE.md'),
            ('~/.claude/project-overrides/', f'~/.claude/{PROFILE}/project-overrides/'),
            ('~\\.claude\\scripts\\username.py', f'~\\.claude\\{PROFILE}\\scripts\\username.py'),
            ('$HOME/.claude/statsig', f'$HOME/.claude/{PROFILE}/statsig'),
            ('${HOME}/.claude/statsig', f'${{HOME}}/.claude/{PROFILE}/statsig'),
            ('"$HOME"/.claude/statsig', f'"$HOME"/.claude/{PROFILE}/statsig'),
            ('rm -rf "$HOME/.claude/statsig"', f'rm -rf "$HOME/.claude/{PROFILE}/statsig"'),
            ('$env:USERPROFILE\\.claude\\statsig', f'$env:USERPROFILE\\.claude\\{PROFILE}\\statsig'),
            (
                'Remove-Item "$env:USERPROFILE\\.claude\\statsig" -Recurse',
                f'Remove-Item "$env:USERPROFILE\\.claude\\{PROFILE}\\statsig" -Recurse',
            ),
            ('%USERPROFILE%\\.claude\\statsig', f'%USERPROFILE%\\.claude\\{PROFILE}\\statsig'),
            ('$env:USERPROFILE/.claude/statsig', f'$env:USERPROFILE/.claude/{PROFILE}/statsig'),
            ('%USERPROFILE%/.claude/statsig', f'%USERPROFILE%/.claude/{PROFILE}/statsig'),
        ],
    )
    def test_config_home_spellings_are_rewritten_into_the_profile(
        self, tmp_path: Path, value: str, expected: str,
    ) -> None:
        """Each spelling keeps its home token and separator; the profile path is inserted after .claude."""
        assert _reroot(tmp_path).rewrite(value) == expected

    @pytest.mark.parametrize(
        ('value', 'expected'),
        [
            ('~/.claude', f'~/.claude/{PROFILE}'),
            ('~/.claude/', f'~/.claude/{PROFILE}/'),
            ('ls ~/.claude; echo done', f'ls ~/.claude/{PROFILE}; echo done'),
            ('(cd "$HOME/.claude")', f'(cd "$HOME/.claude/{PROFILE}")'),
        ],
    )
    def test_the_config_home_itself_is_rewritten(self, tmp_path: Path, value: str, expected: str) -> None:
        """A path naming the config home directory itself becomes the profile directory."""
        assert _reroot(tmp_path).rewrite(value) == expected

    @pytest.mark.parametrize(
        ('value', 'expected'),
        [
            ('~/.claude.json', f'~/.claude/{PROFILE}/.claude.json'),
            ('~/.claude.json.backup', f'~/.claude/{PROFILE}/.claude.json.backup'),
            ('~/.claude.json.corrupted.1700000000', f'~/.claude/{PROFILE}/.claude.json.corrupted.1700000000'),
            ('rm -f "$HOME/.claude.json.backup"', f'rm -f "$HOME/.claude/{PROFILE}/.claude.json.backup"'),
            (
                'Remove-Item "$env:USERPROFILE\\.claude.json"',
                f'Remove-Item "$env:USERPROFILE\\.claude\\{PROFILE}\\.claude.json"',
            ),
        ],
    )
    def test_claude_json_siblings_are_rewritten(self, tmp_path: Path, value: str, expected: str) -> None:
        """~/.claude.json and its backup and corrupted siblings move into the profile directory."""
        assert _reroot(tmp_path).rewrite(value) == expected

    @pytest.mark.parametrize(
        ('home', 'sep'),
        [
            ('~', '/'),
            ('$HOME', '/'),
            ('${HOME}', '/'),
            ('"$HOME"', '/'),
            ('$env:USERPROFILE', '\\'),
            ('%USERPROFILE%', '\\'),
        ],
    )
    @pytest.mark.parametrize('suffix', ['.claude.json.corrupted.*', '.claude.json.backup.*'])
    def test_glob_siblings_are_rewritten_for_every_home_token(
        self, tmp_path: Path, home: str, sep: str, suffix: str,
    ) -> None:
        """A sibling spelled with a shell glob moves into the profile directory, glob and all."""
        assert _reroot(tmp_path).rewrite(f'{home}{sep}{suffix}') == f'{home}{sep}.claude{sep}{PROFILE}{sep}{suffix}'

    @pytest.mark.parametrize(
        ('value', 'expected'),
        [
            (
                'rm -f "$HOME"/.claude.json.corrupted.* 2>/dev/null || true',
                f'rm -f "$HOME"/.claude/{PROFILE}/.claude.json.corrupted.* 2>/dev/null || true',
            ),
            (
                'Remove-Item "$env:USERPROFILE\\.claude.json.corrupted.*" -Force -ErrorAction SilentlyContinue',
                (
                    f'Remove-Item "$env:USERPROFILE\\.claude\\{PROFILE}\\.claude.json.corrupted.*" -Force '
                    '-ErrorAction SilentlyContinue'
                ),
            ),
        ],
    )
    def test_corrupted_glob_cleanup_lines_are_rewritten(self, tmp_path: Path, value: str, expected: str) -> None:
        """The bash and PowerShell lines that sweep ~/.claude.json.corrupted.* run against the profile."""
        assert _reroot(tmp_path).rewrite(value) == expected

    @pytest.mark.parametrize(
        'value',
        [
            '~/.claude-backup/x',
            '~/.claudex/x',
            '~/.claude.jsonx',
            '~/.config/claude/x',
            '/opt/.claude/x',
            '~/.serena/x.yml',
            'uv tool install ruff',
            'https://example.com/~user/.claude/x',
            'foo~/.claude/x',
        ],
    )
    def test_paths_outside_the_config_home_stay_as_written(self, tmp_path: Path, value: str) -> None:
        """A path that does not name the base config home is returned unchanged."""
        assert _reroot(tmp_path).rewrite(value) == value

    def test_another_profile_directory_stays_as_written(self, tmp_path: Path) -> None:
        """A path naming an installed profile's directory is not hijacked into this profile."""
        reroot = _reroot(tmp_path, others=('other',))
        assert reroot.rewrite('~/.claude/other/shared.txt') == '~/.claude/other/shared.txt'
        assert reroot.rewrite('cp "$HOME/.claude/other/x" /tmp') == 'cp "$HOME/.claude/other/x" /tmp'
        assert reroot.rewrite('~/.claude/Other/shared.txt') == '~/.claude/Other/shared.txt'

    def test_a_directory_that_is_not_a_profile_is_rewritten(self, tmp_path: Path) -> None:
        """Only installed profiles and this run's own name are exempt; any other subdirectory moves."""
        reroot = _reroot(tmp_path, others=('other',))
        assert reroot.rewrite('~/.claude/hooks/x.py') == f'~/.claude/{PROFILE}/hooks/x.py'
        assert reroot.rewrite('~/.claude/another/x') == f'~/.claude/{PROFILE}/another/x'

    def test_own_profile_directory_stays_as_written(self, tmp_path: Path) -> None:
        """A path already inside this run's profile is unchanged, so rewriting is idempotent."""
        reroot = _reroot(tmp_path)
        own = f'~/.claude/{PROFILE}/CLAUDE.md'
        assert reroot.rewrite(own) == own
        assert reroot.rewrite(reroot.rewrite('~/.claude/CLAUDE.md')) == own
        assert reroot.rewrite(f'~/.claude/{PROFILE.upper()}/x') == f'~/.claude/{PROFILE.upper()}/x'

    def test_every_occurrence_in_a_command_is_rewritten(self, tmp_path: Path) -> None:
        """A command naming the config home twice has both occurrences rewritten."""
        reroot = _reroot(tmp_path)
        assert reroot.rewrite('cp ~/.claude/a "$HOME/.claude/b"') == (
            f'cp ~/.claude/{PROFILE}/a "$HOME/.claude/{PROFILE}/b"'
        )

    def test_profile_below_the_home_outside_claude_is_spelled_home_relative(self, tmp_path: Path) -> None:
        """A profile relocated below the home keeps the home token and the author's separator."""
        reroot = _reroot(tmp_path, tmp_path / 'profiles' / 'p1')
        assert reroot.rewrite('~/.claude/CLAUDE.md') == '~/profiles/p1/CLAUDE.md'
        assert reroot.rewrite('$env:USERPROFILE\\.claude\\x') == '$env:USERPROFILE\\profiles\\p1\\x'
        assert reroot.rewrite('~/.claude.json') == '~/profiles/p1/.claude.json'

    def test_profile_outside_the_home_is_spelled_absolute(self, tmp_path: Path) -> None:
        """A profile outside the home is spelled as its absolute path in the author's separator style."""
        home = tmp_path / 'home'
        outside = tmp_path / 'elsewhere' / 'p1'
        reroot = ConfigHomeReroot(outside, home, [PROFILE])
        assert reroot.rewrite('~/.claude/CLAUDE.md') == f'{outside.as_posix()}/CLAUDE.md'
        assert reroot.rewrite('$env:USERPROFILE\\.claude\\x') == f'{str(outside).replace("/", chr(92))}\\x'
        assert reroot.rewrite('$HOME/.claude.json') == f'{outside.as_posix()}/.claude.json'


class TestApply:
    """apply() rewrites the configuration sections in place and reports every rewritten item."""

    @staticmethod
    def _config() -> dict[str, Any]:
        return {
            'name': 'Reroot',
            'files-to-download': [
                {'source': 'files/claude.md', 'dest': '~/.claude/CLAUDE.md'},
                {'source': 'files/outside.txt', 'dest': '~/.serena/outside.txt'},
                {'source': 'files/no-dest.txt'},
            ],
            'dependencies': {
                'common': ['uv tool install ruff', 'uv run --script ~/.claude/skills/x/run.py'],
                'linux': ['rm -rf "$HOME/.claude/statsig"'],
                'windows': ['Remove-Item "$env:USERPROFILE\\.claude\\statsig"'],
            },
            'user-settings': {
                'theme': 'dark',
                'apiKeyHelper': 'uv run --no-project --python 3.12 ~/.claude/scripts/username.py',
                'awsCredentialExport': '~/.claude/scripts/aws.sh',
            },
        }

    def test_sections_are_rewritten_in_place_and_reported(self, tmp_path: Path) -> None:
        """Destinations, commands and settings values naming the config home move into the profile."""
        config = self._config()

        records = _reroot(tmp_path).apply(config)

        assert config['files-to-download'][0]['dest'] == f'~/.claude/{PROFILE}/CLAUDE.md'
        assert config['files-to-download'][1]['dest'] == '~/.serena/outside.txt'
        assert config['dependencies']['common'] == [
            'uv tool install ruff', f'uv run --script ~/.claude/{PROFILE}/skills/x/run.py',
        ]
        assert config['dependencies']['linux'] == [f'rm -rf "$HOME/.claude/{PROFILE}/statsig"']
        assert config['dependencies']['windows'] == [f'Remove-Item "$env:USERPROFILE\\.claude\\{PROFILE}\\statsig"']
        assert config['user-settings']['apiKeyHelper'] == (
            f'uv run --no-project --python 3.12 ~/.claude/{PROFILE}/scripts/username.py'
        )
        assert config['user-settings']['awsCredentialExport'] == f'~/.claude/{PROFILE}/scripts/aws.sh'
        assert config['user-settings']['theme'] == 'dark'
        assert records == [
            RerootedPath('files-to-download', '', '~/.claude/CLAUDE.md', f'~/.claude/{PROFILE}/CLAUDE.md'),
            RerootedPath(
                'dependencies', 'common',
                'uv run --script ~/.claude/skills/x/run.py',
                f'uv run --script ~/.claude/{PROFILE}/skills/x/run.py',
            ),
            RerootedPath(
                'dependencies', 'linux', 'rm -rf "$HOME/.claude/statsig"', f'rm -rf "$HOME/.claude/{PROFILE}/statsig"',
            ),
            RerootedPath(
                'dependencies', 'windows',
                'Remove-Item "$env:USERPROFILE\\.claude\\statsig"',
                f'Remove-Item "$env:USERPROFILE\\.claude\\{PROFILE}\\statsig"',
            ),
            RerootedPath(
                'user-settings', 'apiKeyHelper',
                'uv run --no-project --python 3.12 ~/.claude/scripts/username.py',
                f'uv run --no-project --python 3.12 ~/.claude/{PROFILE}/scripts/username.py',
            ),
            RerootedPath(
                'user-settings', 'awsCredentialExport', '~/.claude/scripts/aws.sh', f'~/.claude/{PROFILE}/scripts/aws.sh',
            ),
        ]

    def test_nothing_to_rewrite_reports_nothing_and_leaves_the_config_alone(self, tmp_path: Path) -> None:
        """A configuration without config-home paths is untouched."""
        config: dict[str, Any] = {
            'name': 'Plain',
            'files-to-download': [{'source': 'a.txt', 'dest': '~/.serena/a.txt'}],
            'dependencies': {'common': ['uv tool install ruff']},
            'user-settings': {'theme': 'dark', 'apiKeyHelper': 'get-key'},
        }
        before = {key: (list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value)
                  for key, value in config.items()}

        assert _reroot(tmp_path).apply(config) == []
        assert config == before

    def test_deselected_download_entries_are_rewritten_without_a_record(self, tmp_path: Path) -> None:
        """The removal plan's entries move with the installed ones, so cleanup removes what the run wrote."""
        config: dict[str, Any] = {'name': 'Reroot', 'files-to-download': []}
        deselected: dict[str, list[Any]] = {
            'agents': [], 'slash-commands': [], 'rules': [], 'skills': [], 'mcp-servers': [],
            'files-to-download': [{'source': 'files/extra.txt', 'dest': '~/.claude/opt/extra.txt'}],
            'hooks-files': [], 'hooks-events': [],
        }

        records = _reroot(tmp_path).apply(config, deselected)

        assert deselected['files-to-download'][0]['dest'] == f'~/.claude/{PROFILE}/opt/extra.txt'
        assert records == []

    def test_malformed_sections_are_tolerated(self, tmp_path: Path) -> None:
        """Entries without a string dest, non-list dependency groups and non-dict sections are skipped."""
        config: dict[str, Any] = {
            'files-to-download': ['not-a-dict', {'source': 'x', 'dest': 7}],
            'dependencies': {'common': 'not-a-list', 'linux': ['echo ~/.claude']},
            'user-settings': 'not-a-dict',
        }

        records = _reroot(tmp_path).apply(config)

        assert config['dependencies']['linux'] == [f'echo ~/.claude/{PROFILE}']
        assert records == [RerootedPath('dependencies', 'linux', 'echo ~/.claude', f'echo ~/.claude/{PROFILE}')]


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every home lookup at a temporary home."""
    home = tmp_path / 'home'
    (home / '.claude').mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setattr(setup_environment, 'get_real_user_home', lambda: home)
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    return home


class TestRecordsAndSummaryFollowTheRewrittenPaths:
    """The consumers of a rewritten configuration see the profile paths."""

    def test_rewritten_destination_is_no_longer_machine_wide(self, isolated_home: Path) -> None:
        """collect_machine_wide_writes lists only the destination that stays outside the profile."""
        profile_dir = isolated_home / '.claude' / PROFILE
        config: dict[str, Any] = {'files-to-download': [
            {'source': 'a', 'dest': '~/.claude/CLAUDE.md'},
            {'source': 'b', 'dest': '~/.serena/x.yml'},
        ]}
        _reroot(isolated_home).apply(config)

        writes = setup_environment.collect_machine_wide_writes(
            profile_dir=profile_dir, command_names=[PROFILE], skip_install=True, install_version=None,
            keep_installed=False, pinned_version=None, ide_clis=[], os_level_env={}, mcp_servers=[],
            files_to_download=config['files-to-download'], has_dependency_commands=False,
        )

        download_rows = [row for row in writes if row.startswith('files-to-download')]
        assert download_rows == ['files-to-download outside the profile: ~/.serena/x.yml']

    def test_manifest_records_list_the_profile_file_and_skip_it_as_machine_wide(self, isolated_home: Path) -> None:
        """files_written holds the re-rooted path; machine_wide_destinations records only the outside one."""
        profile_dir = isolated_home / '.claude' / PROFILE
        outside = isolated_home / '.serena' / 'x.yml'
        config: dict[str, Any] = {'files-to-download': [
            {'source': str(isolated_home / 'src' / 'claude.md'), 'dest': '~/.claude/CLAUDE.md'},
            {'source': str(isolated_home / 'src' / 'x.yml'), 'dest': '~/.serena/x.yml'},
        ]}
        _reroot(isolated_home).apply(config)

        assert setup_environment.planned_profile_files(config, profile_dir) == ['CLAUDE.md']
        records = setup_environment.machine_wide_download_records(
            config['files-to-download'], str(isolated_home / 'env.yaml'), None, isolated_home / '.claude',
        )
        assert [record['dest'] for record in records] == [str(outside)]

    def test_summary_marks_each_rewritten_item(self) -> None:
        """The installation summary lists every rewritten item with its original and its new path."""
        plan = setup_environment.InstallationPlan(
            config_name='Reroot', config_source='env.yaml', config_source_type='local', config_version=None,
            command_names=[PROFILE],
            dependency_commands={'common': ['uv tool install ruff', f'echo ~/.claude/{PROFILE}/x']},
            rerooted_paths=[
                RerootedPath('files-to-download', '', '~/.claude/CLAUDE.md', f'~/.claude/{PROFILE}/CLAUDE.md'),
                RerootedPath('dependencies', 'common', 'echo ~/.claude/x', f'echo ~/.claude/{PROFILE}/x'),
                RerootedPath('user-settings', 'apiKeyHelper', 'run ~/.claude/k.py', f'run ~/.claude/{PROFILE}/k.py'),
            ],
        )
        output = io.StringIO()

        with patch.object(setup_environment.Colors, 'GREEN', ''), patch.object(setup_environment.Colors, 'NC', ''), \
                patch.object(setup_environment.Colors, 'BOLD', ''), patch.object(setup_environment.Colors, 'YELLOW', ''):
            setup_environment.display_installation_summary(plan, output=output)

        text = output.getvalue()
        assert 'Re-rooted into the profile (base config-home paths of an isolated run):' in text
        assert f'[re-rooted] files-to-download: ~/.claude/CLAUDE.md -> ~/.claude/{PROFILE}/CLAUDE.md' in text
        assert f'[re-rooted] dependencies [common]: echo ~/.claude/x -> echo ~/.claude/{PROFILE}/x' in text
        assert f'[re-rooted] user-settings apiKeyHelper: run ~/.claude/k.py -> run ~/.claude/{PROFILE}/k.py' in text
        assert f'    $ echo ~/.claude/{PROFILE}/x [re-rooted]' in text
        assert '    $ uv tool install ruff\n' in text

    def test_summary_has_no_block_without_rewritten_items(self) -> None:
        """A base run, or an isolated run without config-home paths, prints no re-rooted block."""
        plan = setup_environment.InstallationPlan(
            config_name='Plain', config_source='env.yaml', config_source_type='local', config_version=None,
            dependency_commands={'common': ['uv tool install ruff']},
        )
        output = io.StringIO()

        setup_environment.display_installation_summary(plan, output=output)

        assert 're-rooted' not in output.getvalue()


class TestDeselectionMirror:
    """Cleanup removes the file the install wrote into the profile and leaves the base copy."""

    def test_rewritten_deselected_entry_removes_the_profile_copy_only(self, isolated_home: Path) -> None:
        """The removal target of a re-rooted entry is the profile file, never the base file."""
        base_copy = isolated_home / '.claude' / 'opt' / 'extra.txt'
        profile_copy = isolated_home / '.claude' / PROFILE / 'opt' / 'extra.txt'
        for copy in (base_copy, profile_copy):
            copy.parent.mkdir(parents=True)
            copy.write_text('x', encoding='utf-8')
        deselected: dict[str, list[Any]] = {
            'agents': [], 'slash-commands': [], 'rules': [], 'skills': [], 'mcp-servers': [],
            'files-to-download': [{'source': 'files/extra.txt', 'dest': '~/.claude/opt/extra.txt'}],
            'hooks-files': [], 'hooks-events': [],
        }
        surviving: dict[str, Any] = {'files-to-download': [{'source': 'files/keep.txt', 'dest': '~/.claude/keep.txt'}]}
        reroot = _reroot(isolated_home)
        reroot.apply(surviving, deselected)
        dirs = {
            name: isolated_home / '.claude' / PROFILE / name
            for name in ('agents', 'commands', 'rules', 'skills', 'hooks')
        }

        setup_environment.execute_deselection_cleanup(
            deselected, surviving,
            agents_dir=dirs['agents'], commands_dir=dirs['commands'], rules_dir=dirs['rules'],
            skills_dir=dirs['skills'], hooks_dir=dirs['hooks'], is_isolated=True,
        )

        assert not profile_copy.exists()
        assert base_copy.read_text(encoding='utf-8') == 'x'


class TestWindowsTildeExpansionFollowsRerooting:
    """The Windows tilde expansion of the settings keys runs on the rewritten value."""

    def test_expanded_api_key_helper_points_into_the_profile(self, isolated_home: Path) -> None:
        """After re-rooting, the expanded helper path lies inside the profile directory."""
        settings = {'apiKeyHelper': 'uv run ~/.claude/scripts/username.py'}
        _reroot(isolated_home).apply({'user-settings': settings})

        with patch.object(setup_environment.sys, 'platform', 'win32'):
            expanded = setup_environment._expand_tilde_keys_in_settings(settings)

        expected = os.path.normpath(str(isolated_home / '.claude' / PROFILE / 'scripts' / 'username.py'))
        assert expanded['apiKeyHelper'] == f'uv run {expected}'


def _linked_config() -> dict[str, Any]:
    """Build a configuration with one destination inside hooks/ and one beside it, both naming the base config home."""
    return {'files-to-download': [
        {'source': 'files/override.yaml', 'dest': '~/.claude/hooks/project-overrides/override.yaml'},
        {'source': 'files/a.txt', 'dest': '~/.claude/x.txt'},
    ]}


class TestLinkedEntriesSeeTheRewrittenDestinations:
    """A dependent's run splits its downloads by linked entry after the rewrite, so a re-rooted hooks/ path is left alone."""

    def test_rewritten_destination_inside_a_linked_entry_is_split_out(self, isolated_home: Path) -> None:
        """The split sees the profile path the rewrite produced, not the base path the configuration spelled."""
        profile_dir = isolated_home / '.claude' / PROFILE
        config = _linked_config()
        _reroot(isolated_home).apply(config)

        kept, skipped = setup_environment.split_downloads_by_linked_entries(
            config['files-to-download'], profile_dir, frozenset({'hooks'}),
        )

        assert kept == [{'source': 'files/a.txt', 'dest': f'~/.claude/{PROFILE}/x.txt'}]
        assert skipped == [(f'~/.claude/{PROFILE}/hooks/project-overrides/override.yaml', 'hooks')]

    def test_files_written_leaves_out_the_destination_a_link_provides(self, isolated_home: Path) -> None:
        """planned_profile_files records the re-rooted file only when the profile holds its directory itself."""
        profile_dir = isolated_home / '.claude' / PROFILE
        config = _linked_config()
        _reroot(isolated_home).apply(config)

        assert setup_environment.planned_profile_files(config, profile_dir) == [
            'hooks/project-overrides/override.yaml', 'x.txt',
        ]
        assert setup_environment.planned_profile_files(config, profile_dir, linked_entries=frozenset({'hooks'})) == [
            'x.txt',
        ]

    def test_summary_lists_the_destinations_links_provide(self) -> None:
        """The summary names each provided destination with the entry and the source profile, after the re-rooted rows."""
        plan = setup_environment.InstallationPlan(
            config_name='Linked', config_source='env.yaml', config_source_type='local', config_version=None,
            command_names=[PROFILE],
            link_plan=setup_environment.LinkPlan(source='p1', actions=[], errors=[]),
            rerooted_paths=[
                RerootedPath(
                    'files-to-download', '', '~/.claude/hooks/project-overrides/override.yaml',
                    f'~/.claude/{PROFILE}/hooks/project-overrides/override.yaml',
                ),
            ],
            linked_downloads=[(f'~/.claude/{PROFILE}/hooks/project-overrides/override.yaml', 'hooks')],
        )
        output = io.StringIO()

        with patch.object(setup_environment.Colors, 'GREEN', ''), patch.object(setup_environment.Colors, 'NC', ''), \
                patch.object(setup_environment.Colors, 'BOLD', ''), patch.object(setup_environment.Colors, 'CYAN', ''):
            setup_environment.display_installation_summary(plan, output=output)

        text = output.getvalue()
        heading = 'Provided by links (files-to-download destinations inside linked entries, written by the source):'
        assert heading in text
        assert (
            f'[linked] ~/.claude/{PROFILE}/hooks/project-overrides/override.yaml: hooks/ is linked from profile "p1"'
        ) in text
        assert text.index('Re-rooted into the profile') < text.index(heading)

    def test_summary_has_no_provided_block_without_linked_downloads(self) -> None:
        """A run whose downloads all land in directories it holds itself prints no provided block."""
        plan = setup_environment.InstallationPlan(
            config_name='Plain', config_source='env.yaml', config_source_type='local', config_version=None,
            link_plan=setup_environment.LinkPlan(source='p1', actions=[], errors=[]),
        )
        output = io.StringIO()

        setup_environment.display_installation_summary(plan, output=output)

        assert 'Provided by links' not in output.getvalue()
        assert '[linked]' not in output.getvalue()

    def test_deselected_rewritten_destination_inside_a_linked_entry_is_kept(
        self, isolated_home: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The removal plan resolves the re-rooted path inside the linked hooks/ and leaves the source's file alone."""
        source_file = isolated_home / '.claude' / 'p1' / 'hooks' / 'project-overrides' / 'override.yaml'
        source_file.parent.mkdir(parents=True)
        source_file.write_text('override: true\n', encoding='utf-8')
        profile_dir = isolated_home / '.claude' / PROFILE
        profile_dir.mkdir()
        setup_environment.link_profile_directory(profile_dir / 'hooks', source_file.parent.parent)
        deselected: dict[str, list[Any]] = {
            'agents': [], 'slash-commands': [], 'rules': [], 'skills': [], 'mcp-servers': [],
            'files-to-download': [
                {'source': 'files/override.yaml', 'dest': '~/.claude/hooks/project-overrides/override.yaml'},
            ],
            'hooks-files': [], 'hooks-events': [],
        }
        surviving: dict[str, Any] = {'files-to-download': []}
        _reroot(isolated_home, others=('p1',)).apply(surviving, deselected)
        dirs = {name: profile_dir / name for name in ('agents', 'commands', 'rules', 'skills', 'hooks')}

        setup_environment.execute_deselection_cleanup(
            deselected, surviving,
            agents_dir=dirs['agents'], commands_dir=dirs['commands'], rules_dir=dirs['rules'],
            skills_dir=dirs['skills'], hooks_dir=dirs['hooks'], is_isolated=True,
            linked_entries=frozenset({'hooks'}),
        )

        assert source_file.read_text(encoding='utf-8') == 'override: true\n'
        assert "Keeping file 'override.yaml': it lies inside an entry linked to another profile" in capsys.readouterr().out
