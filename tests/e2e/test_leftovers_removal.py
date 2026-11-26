"""E2E tests for --remove-leftovers: Step 23 removes what earlier runs installed and the configuration no longer installs.

The tests install real local YAML files into an isolated home through main(),
edit the configuration in place (its identity stays the same, as an update of
a remote configuration does), and re-run the profile with the flag: the
summary and --dry-run mark what Step 23 removes, Step 23 removes each leftover
that still holds what the setup wrote, keeps a hook file a settings file still
wires and a dropped hook helper while any hook file of the folder is wired,
skips every removal after a failed content download, and the manifest records
what was removed and what stays.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e.leftovers_support import HEADING
from tests.e2e.leftovers_support import REMOVES
from tests.e2e.leftovers_support import REMOVES_OTHERS_STAY
from tests.e2e.leftovers_support import SKIP
from tests.e2e.leftovers_support import leftover_rows as _block
from tests.e2e.leftovers_support import printed as _output
from tests.e2e.profile_support import home_state
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_child_runner
from tests.e2e.profile_support import write_config
from tests.e2e.validators import validate_manifest


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the resources they install beside them."""
    directory = tmp_path / 'configs'
    for relative, content in (
        ('agents/core.md', '# core agent\n'),
        ('agents/extra.md', '# extra agent\n'),
        ('rules/rule.md', '# rule\n'),
        ('rules/other.md', '# other rule\n'),
        ('files/tool.txt', 'tool content\n'),
        ('hooks/a.py', 'import h\n'),
        ('hooks/b.py', 'print("b")\n'),
        ('hooks/h.py', 'VALUE = 1\n'),
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _full(outside: Path) -> dict[str, Any]:
    """The first version of a configuration: two agents, two rules and a destination outside ~/.claude."""
    return {
        'name': 'Leftovers Env',
        'agents': ['agents/core.md', 'agents/extra.md'],
        'rules': ['rules/rule.md', 'rules/other.md'],
        'files-to-download': [{'source': 'files/tool.txt', 'dest': str(outside)}],
    }


def _trimmed() -> dict[str, Any]:
    """The next version of the same configuration: it drops an agent, a rule and the destination."""
    return {'name': 'Leftovers Env', 'agents': ['agents/core.md'], 'rules': ['rules/rule.md']}


def _hooked(script: str, helpers: list[str]) -> dict[str, Any]:
    """A configuration whose one Stop hook runs a hooks.files script, with helper modules beside it."""
    return {
        'name': 'Hooks Env',
        'rules': ['rules/rule.md'],
        'hooks': {
            'files': [f'hooks/{script}'],
            'helpers': [f'hooks/{name}' for name in helpers],
            'events': [{'event': 'Stop', 'type': 'command', 'command': script}],
        },
    }


@contextlib.contextmanager
def _undeletable(path: Path) -> Generator[None]:
    """Make a file impossible to remove for as long as the block runs.

    Windows refuses to delete a file another handle holds open; elsewhere a
    file cannot be unlinked from a directory without write permission. The
    file sits in a directory of its own, so no other step writes there.
    """
    if sys.platform == 'win32':
        with path.open('rb'):
            yield
        return
    mode = path.parent.stat().st_mode
    path.parent.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    try:
        yield
    finally:
        path.parent.chmod(mode)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestFlaggedRunRemovesLeftovers:
    """A run given the flag removes the leftovers in Step 23 and records each removal."""

    @pytest.mark.parametrize('profile', ['prof-a', None], ids=['isolated', 'base'])
    def test_dry_run_previews_and_the_flagged_run_removes(
        self,
        e2e_isolated_home: dict[str, Path],
        configs: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        profile: str | None,
    ) -> None:
        outside = tmp_path / 'shared' / 'tool.txt'
        cfg = write_config(configs, 'env.yaml', _full(outside))
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / profile if profile else claude_dir
        names = ['--command-names', profile] if profile else []
        rerun = ['--profile', profile or 'base', *SKIP, '--remove-leftovers']
        assert run_main([str(cfg), *SKIP, '--yes', *names]) == 0
        write_config(configs, 'env.yaml', _trimmed())
        capsys.readouterr()

        before = home_state(e2e_isolated_home['home'])
        assert run_main([*rerun, '--dry-run']) == 0
        dry = _output(capsys)
        assert home_state(e2e_isolated_home['home']) == before, 'a dry run removes nothing'
        assert _block(dry) == [
            f'  [would be removed in Step 23] file: {profile_dir / "agents" / "extra.md"}',
            f'  [would be removed in Step 23] file: {profile_dir / "rules" / "other.md"}',
            f'  [would be removed in Step 23] file outside ~/.claude: {outside}',
            (
                '  Step 23 removes each item marked [would be removed in Step 23] only while it still holds what the '
                'setup wrote.'
            ),
        ]
        if profile:
            assert f'[machine-wide] remove leftover file: {outside}' in dry
        else:
            assert 'remove leftover file' not in dry, 'a base run lists no machine-wide writes'

        assert run_main([*rerun, '--yes']) == 0

        output = _output(capsys)
        assert _block(output) == [
            f'  [remove] file: {profile_dir / "agents" / "extra.md"}',
            f'  [remove] file: {profile_dir / "rules" / "other.md"}',
            f'  [remove] file outside ~/.claude: {outside}',
            f'  {REMOVES}',
        ]
        assert 'Step 23: Removing leftovers...' in output
        assert output.index('Step 20:') < output.index('Step 23: Removing leftovers...')
        assert f'Removed leftover file: {profile_dir / "rules" / "other.md"}' in output
        assert '   * Leftovers removed (3):' in output
        for path in (profile_dir / 'agents' / 'extra.md', profile_dir / 'rules' / 'other.md', outside):
            assert not path.exists(), f'{path} was not removed'
        assert (profile_dir / 'agents' / 'core.md').is_file()
        assert (profile_dir / 'rules' / 'rule.md').is_file()
        manifest = read_manifest(profile_dir)
        assert manifest['leftovers']['items'] == []
        assert manifest['leftovers']['removed'] == [
            'file: agents/extra.md', 'file: rules/other.md', f'file outside ~/.claude: {outside}',
        ]
        config = {**_trimmed(), 'command-names': [profile]} if profile else _trimmed()
        assert not validate_manifest(profile_dir / 'manifest.json', config)

        assert run_main(['--profile', profile or 'base', *SKIP, '--yes']) == 0

        assert HEADING not in _output(capsys), 'nothing is left to list'

    def test_the_variable_turns_the_flag_on(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'env.yaml', _full(tmp_path / 'shared' / 'tool.txt'))
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        write_config(configs, 'env.yaml', _trimmed())
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS', '1')
        capsys.readouterr()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes']) == 0

        assert f'  [remove] file: {profile_dir / "rules" / "other.md"}' in _block(_output(capsys))
        assert not (profile_dir / 'rules' / 'other.md').exists()

    def test_without_the_flag_the_summary_names_it(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'env.yaml', _full(tmp_path / 'shared' / 'tool.txt'))
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        write_config(configs, 'env.yaml', _trimmed())
        capsys.readouterr()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert f'  {setup_environment.LEFTOVERS_FLAG_FOOTER}' in _block(output)
        assert '   * Leftovers left in place (3; --remove-leftovers removes them):' in output
        assert 'Step 23' not in output, 'without the flag Step 23 has nothing to do'
        assert (profile_dir / 'rules' / 'other.md').is_file()


@pytest.mark.usefixtures('e2e_isolated_home')
class TestFailedRemoval:
    """A leftover Step 23 cannot remove stays recorded, is named in the errors block and ends the run with exit 1."""

    def test_failed_removal_is_carried_and_retried(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        outside = tmp_path / 'locked' / 'tool.txt'
        cfg = write_config(configs, 'env.yaml', _full(outside))
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        write_config(configs, 'env.yaml', _trimmed())
        digest = setup_environment._sha256_of_file(outside)
        capsys.readouterr()

        with _undeletable(outside):
            code = run_main(['--profile', 'prof-a', *SKIP, '--yes', '--remove-leftovers'])

        output = _output(capsys)
        assert code == 1, output
        assert 'The following leftovers could not be removed (they stay recorded):' in output
        assert f'file outside ~/.claude: {outside}: ' in output
        assert 'Retry with --profile prof-a --remove-leftovers.' in output
        assert outside.is_file()
        assert not (profile_dir / 'rules' / 'other.md').exists(), 'the other leftovers are still removed'
        leftovers = read_manifest(profile_dir)['leftovers']
        assert leftovers['failed'] == [f'file outside ~/.claude: {outside}']
        assert leftovers['items'] == [{'kind': 'destination', 'path': str(outside), 'sha256': digest}]

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes', '--remove-leftovers']) == 0

        output = _output(capsys)
        assert f'  [remove] file outside ~/.claude: {outside}' in _block(output), 'the carried leftover is listed again'
        assert not outside.exists()
        assert read_manifest(profile_dir)['leftovers']['items'] == []


@pytest.mark.usefixtures('e2e_isolated_home')
class TestContentDownloadFailure:
    """A run whose content download fails removes no leftover, because what replaces them may be missing."""

    def test_removal_is_skipped_and_the_leftovers_stay_recorded(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'env.yaml', _full(tmp_path / 'shared' / 'tool.txt'))
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        write_config(configs, 'env.yaml', {**_trimmed(), 'rules': ['rules/rule.md', 'rules/missing.md']})
        capsys.readouterr()

        code = run_main(['--profile', 'prof-a', *SKIP, '--yes', '--remove-leftovers'])

        output = _output(capsys)
        assert code == 1, output
        assert 'The following resources failed to download:' in output
        assert 'Leftovers not removed: content downloads failed' in output
        assert (profile_dir / 'rules' / 'other.md').is_file()
        assert (profile_dir / 'agents' / 'extra.md').is_file()
        leftovers = read_manifest(profile_dir)['leftovers']
        assert leftovers['skipped'] == 'content downloads failed'
        assert [item['path'] for item in leftovers['items']] == [
            'agents/extra.md', 'rules/other.md', str(tmp_path / 'shared' / 'tool.txt'),
        ]


@pytest.mark.usefixtures('e2e_isolated_home')
class TestConfigurationSwitchAfterAFailedDownload:
    """A switch whose content download fails removes nothing in Step 23 and keeps the previous files recorded."""

    def test_a_later_flagged_run_removes_what_the_switch_left(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg_a = write_config(configs, 'a.yaml', {'name': 'A', 'agents': ['agents/core.md'], 'rules': ['rules/rule.md']})
        cfg_b = write_config(configs, 'b.yaml', {'name': 'B', 'rules': ['rules/rule.md', 'rules/missing.md']})
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg_a), *SKIP, '--yes']) == 0
        digest = setup_environment._sha256_of_file(claude_dir / 'agents' / 'core.md')
        capsys.readouterr()

        code = run_main([str(cfg_b), *SKIP, '--yes', '--switch-config'])

        output = _output(capsys)
        assert code == 1, output
        assert 'Leftovers not removed: content downloads failed' in output
        assert 'Removed leftover' not in output
        assert (claude_dir / 'agents' / 'core.md').is_file()
        leftovers = read_manifest(claude_dir)['leftovers']
        assert leftovers['skipped'] == 'content downloads failed'
        assert leftovers['items'] == [{'kind': 'file', 'path': 'agents/core.md', 'sha256': digest}]
        write_config(configs, 'b.yaml', {'name': 'B', 'rules': ['rules/rule.md']})

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert f'  [remove] file: {claude_dir / "agents" / "core.md"}' in _block(_output(capsys))
        assert not (claude_dir / 'agents' / 'core.md').exists()
        assert read_manifest(claude_dir)['leftovers']['removed'] == ['file: agents/core.md']


@pytest.mark.usefixtures('e2e_isolated_home')
class TestRenamedHookFile:
    """A hook file the configuration renamed leaves once no settings file a session reads wires it."""

    def test_isolated_profile_removes_the_old_script_and_keeps_the_helper_while_a_hook_is_wired(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Step 18 rebuilds config.json without the old script, so the summary already marks it for removal.

        The dropped helper stays while config.json wires the new script, which
        may import it, and leaves with the run whose configuration wires no
        hook file.
        """
        cfg = write_config(configs, 'hooks.yaml', _hooked('a.py', ['h.py']))
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        assert (profile_dir / 'hooks' / 'a.py').as_posix() in (profile_dir / 'config.json').read_text(encoding='utf-8')
        assert [
            (record['path'], record.get('hook_helper')) for record in read_manifest(profile_dir)['files_written']
            if record['path'].startswith('hooks/')
        ] == [('hooks/a.py', None), ('hooks/h.py', True)], 'files_written marks the hooks.helpers module'
        write_config(configs, 'hooks.yaml', _hooked('b.py', []))
        capsys.readouterr()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes', '--remove-leftovers']) == 0

        output = _output(capsys)
        assert _block(output) == [
            f'  [remove] file: {profile_dir / "hooks" / "a.py"}',
            f'  [kept: stays with hooks/b.py, which is still wired] file: {profile_dir / "hooks" / "h.py"}',
            f'  {REMOVES_OTHERS_STAY}',
        ]
        assert not (profile_dir / 'hooks' / 'a.py').exists()
        assert (profile_dir / 'hooks' / 'h.py').is_file(), 'the wired script may import the helper'
        assert (profile_dir / 'hooks' / 'b.py').is_file()
        config = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
        assert (profile_dir / 'hooks' / 'b.py').as_posix() in json.dumps(config['hooks'])
        items = read_manifest(profile_dir)['leftovers']['items']
        assert [(item['path'], item.get('hook_helper')) for item in items] == [('hooks/h.py', True)]
        write_config(configs, 'hooks.yaml', {'name': 'Hooks Env', 'rules': ['rules/rule.md']})

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert _block(_output(capsys)) == [
            f'  [remove] file: {profile_dir / "hooks" / "b.py"}',
            f'  [remove] file: {profile_dir / "hooks" / "h.py"}',
            f'  {REMOVES}',
        ], 'with no hook file wired, nothing can import the helper'
        assert not (profile_dir / 'hooks' / 'h.py').exists()
        assert not (profile_dir / 'hooks' / 'b.py').exists()

    def test_a_helper_stays_in_step_23_while_a_script_edited_by_hand_is_wired(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The edited script is no longer tracked, yet a settings file runs it, so Step 23 keeps the helper too."""
        cfg = write_config(configs, 'hooks.yaml', _hooked('a.py', ['h.py']))
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        (profile_dir / 'hooks' / 'a.py').write_text('import h\nprint("mine")\n', encoding='utf-8')
        command = f'uv run "{(profile_dir / "hooks" / "a.py").as_posix()}"'
        (profile_dir / 'settings.json').write_text(json.dumps({'hooks': {'Stop': [
            {'matcher': '', 'hooks': [{'type': 'command', 'command': command}]},
        ]}}), encoding='utf-8')
        write_config(configs, 'hooks.yaml', {'name': 'Hooks Env', 'rules': ['rules/rule.md']})
        capsys.readouterr()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert _block(_output(capsys)) == [
            f'  [changed since written: left in place, no longer tracked] file: {profile_dir / "hooks" / "a.py"}',
            f'  [kept: stays with hooks/a.py, which is still wired] file: {profile_dir / "hooks" / "h.py"}',
            '  They stay in place.',
        ]
        assert (profile_dir / 'hooks' / 'h.py').is_file(), 'the edited script a session runs still imports it'
        assert [item['path'] for item in read_manifest(profile_dir)['leftovers']['items']] == ['hooks/h.py']

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert (profile_dir / 'hooks' / 'h.py').is_file(), 'the next run keeps it while the script is wired'

    def test_base_profile_without_the_flag_lists_the_script_with_the_group_that_wires_it(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The union-merged base settings.json keeps the old group; both are leftovers the flag removes together.

        Without the flag nothing leaves and the group still runs the old
        script, so no session meets a missing file. The rows marked
        [leftover] are exactly what the flagged run removes.
        """
        cfg = write_config(configs, 'hooks.yaml', _hooked('a.py', ['h.py']))
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        write_config(configs, 'hooks.yaml', _hooked('b.py', []))
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        output = _output(capsys)
        settings = claude_dir / 'settings.json'
        held = f'  [kept: stays with hooks/b.py, which is still wired] file: {claude_dir / "hooks" / "h.py"}'
        assert _block(output) == [
            f'  [leftover] file: {claude_dir / "hooks" / "a.py"}',
            held,
            f'  [leftover] {settings}: hooks.Stop group matcher "" (1 hook)',
            '  They stay in place.',
            f'  {setup_environment.LEFTOVERS_FLAG_FOOTER}',
        ]
        assert (claude_dir / 'hooks' / 'a.py').is_file(), 'nothing leaves without the flag'
        assert (claude_dir / 'hooks' / 'h.py').is_file()
        assert (claude_dir / 'hooks' / 'a.py').as_posix() in settings.read_text(encoding='utf-8'), 'the group stays'
        leftovers = read_manifest(claude_dir)['leftovers']
        assert [(item['kind'], item['path']) for item in leftovers['items']] == [
            ('file', 'hooks/a.py'), ('file', 'hooks/h.py'), ('hook-group', ['hooks', 'Stop']),
        ]
        assert [entry['label'] for entry in leftovers['kept']] == ['file: hooks/h.py']

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert _block(_output(capsys)) == [
            f'  [remove] file: {claude_dir / "hooks" / "a.py"}',
            held,
            f'  [remove] {settings}: hooks.Stop group matcher "" (1 hook)',
            f'  {REMOVES_OTHERS_STAY}',
        ]
        removed = read_manifest(claude_dir)['leftovers']['removed']
        assert sorted(label.split(' group ')[0] for label in removed) == ['file: hooks/a.py', 'settings.json: hooks.Stop']
        assert not (claude_dir / 'hooks' / 'a.py').exists()
        assert (claude_dir / 'hooks' / 'h.py').is_file()

    def test_with_selected_components_a_helper_beside_a_script_only_a_leftover_group_wires_is_a_leftover(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The summary of a run whose components are selected reads the hook folder as the flagged Step 23 leaves it."""
        cfg = write_config(configs, 'hooks.yaml', _hooked('a.py', ['h.py']))
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        write_config(configs, 'hooks.yaml', {
            'name': 'Hooks Env',
            'rules': ['rules/rule.md', 'rules/other.md'],
            'components': [{'name': 'extra', 'includes': {'rules': ['rules/other.md']}}],
        })
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        settings = claude_dir / 'settings.json'
        rows = [
            f'  [leftover] file: {claude_dir / "hooks" / "a.py"}',
            f'  [leftover] file: {claude_dir / "hooks" / "h.py"}',
            f'  [leftover] {settings}: hooks.Stop group matcher "" (1 hook)',
        ]
        assert _block(_output(capsys)) == [*rows, '  They stay in place.', f'  {setup_environment.LEFTOVERS_FLAG_FOOTER}']
        assert read_manifest(claude_dir)['leftovers']['kept'] == []

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert _block(_output(capsys)) == [*(row.replace('[leftover]', '[remove]') for row in rows), f'  {REMOVES}']
        assert len(read_manifest(claude_dir)['leftovers']['removed']) == 3
        assert not (claude_dir / 'hooks' / 'a.py').exists()
        assert not (claude_dir / 'hooks' / 'h.py').exists()

    def test_a_dependent_of_the_base_that_links_hooks_keeps_the_script_without_the_flag(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A dependent's config.json runs the base script after the base group leaves, so the script stays."""
        cfg = write_config(configs, 'hooks.yaml', _hooked('a.py', ['h.py']))
        claude_dir = e2e_isolated_home['claude_dir']
        lab = claude_dir / 'team-lab'
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'team-lab', '--link-dirs', 'hooks', '--link-from', 'base',
        ]) == 0
        assert (lab / 'hooks' / 'a.py').as_posix() in (lab / 'config.json').read_text(encoding='utf-8')
        write_config(configs, 'hooks.yaml', _hooked('b.py', []))
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'base', *SKIP, '--yes'], argv0=str(runner))

        output = _output(capfd)
        assert code == 0, output
        wired = (
            f'still wired in profile team-lab ({lab / "config.json"} hooks.Stop) until that profile is refreshed; '
            'a later run with --remove-leftovers removes it'
        )
        settings = claude_dir / 'settings.json'
        assert _block(output) == [
            f'  [kept: {wired}] file: {claude_dir / "hooks" / "a.py"}',
            f'  [kept: stays with hooks/a.py, which is still wired] file: {claude_dir / "hooks" / "h.py"}',
            f'  [leftover] {settings}: hooks.Stop group matcher "" (1 hook)',
            '  They stay in place.',
            f'  {setup_environment.LEFTOVERS_FLAG_FOOTER}',
        ]
        assert {entry['label']: entry['reason'] for entry in read_manifest(claude_dir)['leftovers']['kept']} == {
            'file: hooks/a.py': f'kept: {wired}',
            'file: hooks/h.py': 'kept: stays with hooks/a.py, which is still wired',
        }
        assert (claude_dir / 'hooks' / 'a.py').is_file()

    @pytest.mark.parametrize(('profile', 'token'), [('prof-a', '$HOME'), (None, '~')], ids=['isolated', 'base'])
    def test_a_script_wired_by_hand_through_the_home_folder_stays(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
        profile: str | None, token: str,
    ) -> None:
        """A settings file that runs the old script as ~/.claude/... or $HOME/.claude/... keeps it in place."""
        cfg = write_config(configs, 'hooks.yaml', _hooked('a.py', []))
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / profile if profile else claude_dir
        names = ['--command-names', profile] if profile else []
        assert run_main([str(cfg), *SKIP, '--yes', *names]) == 0
        settings = profile_dir / 'settings.json'
        content: dict[str, Any] = json.loads(settings.read_text(encoding='utf-8')) if settings.exists() else {}
        relative = f'.claude/{profile}/hooks/a.py' if profile else '.claude/hooks/a.py'
        content.setdefault('hooks', {})['UserPromptSubmit'] = [
            {'matcher': '', 'hooks': [{'type': 'command', 'command': f'uv run {token}/{relative}'}]},
        ]
        settings.write_text(json.dumps(content, indent=2), encoding='utf-8')
        write_config(configs, 'hooks.yaml', _hooked('b.py', []))
        capsys.readouterr()

        assert run_main(['--profile', profile or 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        rows = _block(_output(capsys))
        assert f'  [kept: still wired in {settings} hooks.UserPromptSubmit] file: {profile_dir / "hooks" / "a.py"}' in rows
        assert (profile_dir / 'hooks' / 'a.py').is_file(), 'a script a session still runs is never removed'
        assert [item['path'] for item in read_manifest(profile_dir)['leftovers']['items']] == ['hooks/a.py']

    @pytest.mark.parametrize('profile', ['prof-a', None], ids=['isolated', 'base'])
    def test_a_selection_that_drops_the_only_hook_releases_the_helper(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
        profile: str | None,
    ) -> None:
        """The summary reads the hooks the selected components wire, as Step 23 does after Steps 18 and 23.

        The base settings.json still wires the deselected script before
        consent; Step 23 deletes that script and unwires it before it looks
        at the leftovers.
        """
        def _config(helpers: list[str]) -> dict[str, Any]:
            config = _hooked('a.py', helpers)
            config['hooks']['events'][0]['id'] = 'ea'
            config['components'] = [{'name': 'extra', 'includes': {'hooks': ['hooks/a.py', 'ea']}}]
            return config

        cfg = write_config(configs, 'hooks.yaml', _config(['h.py']))
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / profile if profile else claude_dir
        names = ['--command-names', profile] if profile else []
        assert run_main([str(cfg), *SKIP, '--yes', *names]) == 0
        write_config(configs, 'hooks.yaml', _config([]))
        capsys.readouterr()

        assert run_main([
            '--profile', profile or 'base', *SKIP, '--yes', '--remove-leftovers', '--without', 'extra',
        ]) == 0

        assert _block(_output(capsys)) == [
            f'  [remove] file: {profile_dir / "hooks" / "h.py"}',
            f'  {REMOVES}',
        ], 'with the only hook deselected, nothing wires a file of the folder'
        assert not (profile_dir / 'hooks' / 'h.py').exists()
        assert not (profile_dir / 'hooks' / 'a.py').exists(), 'the deselected script leaves with its component'

    def test_a_dependent_that_links_hooks_keeps_the_script_until_its_refresh(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A dependent's config.json wires the source's script until Step 24 refreshes it; a later flagged run removes it."""
        cfg = write_config(configs, 'hooks.yaml', _hooked('a.py', ['h.py']))
        claude_dir = e2e_isolated_home['claude_dir']
        source, lab = claude_dir / 'team-1', claude_dir / 'team-lab'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        link = ['--command-names', 'team-lab', '--link-dirs', 'hooks', '--link-from', 'team-1']
        assert run_main([str(cfg), *SKIP, '--yes', *link]) == 0
        assert (lab / 'hooks' / 'a.py').as_posix() in (lab / 'config.json').read_text(encoding='utf-8')
        write_config(configs, 'hooks.yaml', _hooked('b.py', []))
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'team-1', *SKIP, '--yes', '--remove-leftovers'], argv0=str(runner))

        output = _output(capfd)
        assert code == 0, output
        wired = (
            f'still wired in profile team-lab ({lab / "config.json"} hooks.Stop) until that profile is refreshed; '
            'a later run with --remove-leftovers removes it'
        )
        assert _block(output) == [
            f'  [kept: {wired}] file: {source / "hooks" / "a.py"}',
            f'  [kept: stays with hooks/a.py, which is still wired] file: {source / "hooks" / "h.py"}',
            '  They stay in place.',
        ], 'the dependent still runs the old script, and the source wires the new one'
        assert (source / 'hooks' / 'a.py').is_file()
        assert (source / 'hooks' / 'h.py').is_file()
        assert '- team-lab: ok' in output
        assert (lab / 'hooks' / 'b.py').as_posix() in (lab / 'config.json').read_text(encoding='utf-8'), (
            'Step 24 rewired the dependent'
        )

        assert run_main(['--profile', 'team-1', *SKIP, '--yes', '--remove-leftovers'], argv0=str(runner)) == 0

        output = _output(capfd)
        assert f'  [remove] file: {source / "hooks" / "a.py"}' in _block(output)
        assert f'  [kept: stays with hooks/b.py, which is still wired] file: {source / "hooks" / "h.py"}' in _block(
            output,
        )
        assert not (source / 'hooks' / 'a.py').exists()
        assert (source / 'hooks' / 'h.py').is_file(), 'the new script both profiles run may import it'
        assert (source / 'hooks' / 'b.py').is_file()
        assert os.path.isfile(lab / 'hooks' / 'b.py'), 'the dependent still reaches the new script through its link'
