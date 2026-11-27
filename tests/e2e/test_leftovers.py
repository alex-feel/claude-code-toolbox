"""E2E tests for the leftovers a re-run lists: what earlier runs wrote and the configuration no longer installs.

A profile's manifest records every profile file and every destination
outside ~/.claude a run wrote, with the sha256 of its content, and carries
the leftovers the run found. The tests install real local YAML files into an
isolated home through main(), edit the configuration in place (so its
identity stays the same, as an update of a remote configuration does), and
re-run the profile: the installation summary, --dry-run and the completion
summary list each leftover with what the run found at its path, the files
stay in place, and the manifest carries them to the next run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e.profile_support import home_state
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config
from tests.e2e.profile_support import written_files
from tests.e2e.validators import validate_manifest

SKIP = ['--skip-install', '--no-admin']
HEADING = 'Leftovers of earlier runs (this configuration no longer installs them):'
NOTE = 'was installed by a release that recorded no leftovers; they are tracked from this run on.'
FLAG_FOOTER = f'  {setup_environment.LEFTOVERS_FLAG_FOOTER}'


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
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """Everything the run printed, with Windows line endings normalized."""
    captured = capsys.readouterr()
    return (captured.out + captured.err).replace('\r\n', '\n')


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


def _block(output: str) -> str:
    """The rows of the installation summary's leftovers block, below its heading line."""
    assert HEADING in output, output
    return output.split(HEADING)[1].split('\n', 1)[1].split('\n\n')[0]


def _items(profile_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = read_manifest(profile_dir)['leftovers']['items']
    return items


@pytest.mark.usefixtures('e2e_isolated_home')
class TestLeftoversAreListedAndKept:
    """A re-run lists what the configuration no longer installs, leaves it in place and carries it on."""

    @pytest.mark.parametrize('profile', ['prof-a', None], ids=['isolated', 'base'])
    def test_dropped_files_and_destination(
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
        rerun = ['--profile', profile or 'base', *SKIP]
        assert run_main([str(cfg), *SKIP, '--yes', *names]) == 0
        first = read_manifest(profile_dir)
        assert first['leftovers']['items'] == [], 'a first install records no leftover'
        assert {record['path']: record['sha256'] for record in first['files_written']}['rules/other.md'] == (
            setup_environment._sha256_of_file(profile_dir / 'rules' / 'other.md')
        )
        write_config(configs, 'env.yaml', _trimmed())
        capsys.readouterr()

        before = home_state(e2e_isolated_home['home'])
        assert run_main([*rerun, '--dry-run']) == 0
        dry_block = _block(_output(capsys))
        assert home_state(e2e_isolated_home['home']) == before, 'a dry run changes nothing'

        assert run_main([*rerun, '--yes']) == 0

        output = _output(capsys)
        expected_rows = [
            f'  [leftover] file: {profile_dir / "agents" / "extra.md"}',
            f'  [leftover] file: {profile_dir / "rules" / "other.md"}',
            f'  [leftover] file outside ~/.claude: {outside}',
            '  They stay in place.',
            FLAG_FOOTER,
        ]
        assert _block(output).strip('\n').split('\n') == expected_rows
        assert dry_block == _block(output), '--dry-run lists the same leftovers'
        assert '   * Leftovers left in place (3; --remove-leftovers removes them):' in output
        assert f'       - file: {profile_dir / "rules" / "other.md"}' in output
        assert NOTE not in output
        for path in (profile_dir / 'agents' / 'extra.md', profile_dir / 'rules' / 'other.md', outside):
            assert path.is_file(), f'{path} was removed'
        manifest = read_manifest(profile_dir)
        assert written_files(manifest) == ['agents/core.md', 'rules/rule.md']
        assert manifest['machine_wide_destinations'] == []
        assert _items(profile_dir) == [
            {'kind': 'file', 'path': 'agents/extra.md', 'sha256': setup_environment._sha256_of_file(
                profile_dir / 'agents' / 'extra.md')},
            {'kind': 'file', 'path': 'rules/other.md', 'sha256': setup_environment._sha256_of_file(
                profile_dir / 'rules' / 'other.md')},
            {'kind': 'destination', 'path': str(outside), 'sha256': setup_environment._sha256_of_file(outside)},
        ]
        config = {**_trimmed(), 'command-names': [profile]} if profile else _trimmed()
        assert not validate_manifest(profile_dir / 'manifest.json', config)

        assert run_main([*rerun, '--yes']) == 0

        assert _block(_output(capsys)).strip('\n').split('\n') == expected_rows, 'the carried leftovers are listed again'
        assert len(_items(profile_dir)) == 3

    def test_configuration_listing_a_leftover_again_takes_it_back(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'env.yaml', _full(tmp_path / 'shared' / 'tool.txt'))
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        write_config(configs, 'env.yaml', _trimmed())
        assert run_main(['--profile', 'prof-a', *SKIP, '--yes']) == 0
        assert len(_items(profile_dir)) == 3
        write_config(configs, 'env.yaml', {**_trimmed(), 'rules': ['rules/rule.md', 'rules/other.md']})
        capsys.readouterr()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes']) == 0

        block = _block(_output(capsys))
        assert 'rules' not in block, 'a file the configuration installs again is no leftover'
        assert [item['path'] for item in _items(profile_dir)] == ['agents/extra.md', str(tmp_path / 'shared' / 'tool.txt')]
        assert 'rules/other.md' in written_files(read_manifest(profile_dir))


@pytest.mark.usefixtures('e2e_isolated_home')
class TestChangedAndGoneLeftovers:
    """A leftover changed or removed by hand is reported once and no longer tracked."""

    def test_hand_edited_and_hand_removed(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        outside = tmp_path / 'shared' / 'tool.txt'
        cfg = write_config(configs, 'env.yaml', _full(outside))
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        write_config(configs, 'env.yaml', _trimmed())
        (profile_dir / 'rules' / 'other.md').write_text('# edited by hand\n', encoding='utf-8')
        (profile_dir / 'agents' / 'extra.md').unlink()
        capsys.readouterr()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert _block(output).strip('\n').split('\n') == [
            f'  [already gone: no longer tracked] file: {profile_dir / "agents" / "extra.md"}',
            f'  [changed since written: left in place, no longer tracked] file: {profile_dir / "rules" / "other.md"}',
            f'  [leftover] file outside ~/.claude: {outside}',
            '  They stay in place.',
            FLAG_FOOTER,
        ]
        assert '   * No longer tracked:' in output
        assert f'       - file: {profile_dir / "rules" / "other.md"} (changed since written)' in output
        assert f'       - file: {profile_dir / "agents" / "extra.md"} (already gone)' in output
        assert (profile_dir / 'rules' / 'other.md').read_text(encoding='utf-8') == '# edited by hand\n'
        leftovers = read_manifest(profile_dir)['leftovers']
        assert [item['path'] for item in leftovers['items']] == [str(outside)]
        assert leftovers['dropped'] == [
            {'label': 'file: agents/extra.md', 'reason': 'gone'},
            {'label': 'file: rules/other.md', 'reason': 'changed'},
        ]

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes']) == 0

        assert _block(_output(capsys)).strip('\n').split('\n') == [
            f'  [leftover] file outside ~/.claude: {outside}',
            '  They stay in place.',
            FLAG_FOOTER,
        ], 'a dropped leftover is reported only once'
        assert read_manifest(profile_dir)['leftovers']['dropped'] == []


@pytest.mark.usefixtures('e2e_isolated_home')
class TestDestinationAnotherProfileRecords:
    """A destination outside ~/.claude another installed profile records is listed as kept."""

    def test_held_destination(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        outside = tmp_path / 'shared' / 'tool.txt'
        cfg = write_config(configs, 'base.yaml', _full(outside))
        other = write_config(configs, 'other.yaml', {
            'name': 'Other', 'files-to-download': [{'source': 'files/tool.txt', 'dest': str(outside)}],
        })
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        write_config(configs, 'base.yaml', _trimmed())
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert f'  [kept: recorded by profile team-1] file outside ~/.claude: {outside}' in _block(output)
        assert f'       - file outside ~/.claude: {outside} (kept: recorded by profile team-1)' in output
        assert outside.is_file()
        assert str(outside) in [item['path'] for item in _items(claude_dir)], 'a kept destination stays recorded'


GUARD = 'The previous configuration leaves behind:'


def _guard(output: str) -> str:
    """The lines the switch guard lists, up to the line that accepts the switch."""
    assert GUARD in output, output
    return output.split(GUARD)[1].split('Accepted via')[0]


@pytest.mark.usefixtures('e2e_isolated_home')
class TestConfigurationSwitch:
    """An accepted configuration switch removes the leftovers in Step 23 exactly as --remove-leftovers does."""

    def test_the_switch_removes_its_leftovers_and_keeps_what_another_profile_records(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        own, held = tmp_path / 'shared' / 'own.txt', tmp_path / 'shared' / 'held.txt'
        cfg_a = write_config(configs, 'a.yaml', {
            'name': 'A', 'agents': ['agents/core.md'], 'rules': ['rules/rule.md'],
            'files-to-download': [
                {'source': 'files/tool.txt', 'dest': str(own)}, {'source': 'files/tool.txt', 'dest': str(held)},
            ],
        })
        other = write_config(configs, 'other.yaml', {
            'name': 'Other', 'files-to-download': [{'source': 'files/tool.txt', 'dest': str(held)}],
        })
        cfg_b = write_config(configs, 'b.yaml', {'name': 'B', 'rules': ['rules/rule.md']})
        claude_dir = e2e_isolated_home['claude_dir']
        core = claude_dir / 'agents' / 'core.md'
        assert run_main([str(cfg_a), *SKIP, '--yes']) == 0
        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--yes', '--switch-config']) == 0

        output = _output(capsys)
        rows = [
            f'  [remove] file: {core}',
            f'  [kept: recorded by profile team-1] file outside ~/.claude: {held}',
            f'  [remove] file outside ~/.claude: {own}',
            (
                '  Step 23 removes each item marked [remove] only while it still holds what the setup wrote; '
                'the others stay in place.'
            ),
        ]
        guard = _guard(output)
        assert all(row.strip() in guard for row in rows), guard
        assert _block(output).strip('\n').split('\n') == rows, 'the summary lists what Step 23 removes'
        assert output.index('Step 18:') < output.index(f'Removed leftover file outside ~/.claude: {own}'), (
            'the switch removes after the new configuration is in place'
        )
        assert not core.exists()
        assert not own.exists()
        assert held.is_file()
        assert '   * Leftovers removed (2):' in output
        leftovers = read_manifest(claude_dir)['leftovers']
        assert leftovers['items'] == [
            {'kind': 'destination', 'path': str(held), 'sha256': setup_environment._sha256_of_file(held)},
        ]
        assert sorted(leftovers['removed']) == sorted(['file: agents/core.md', f'file outside ~/.claude: {own}'])

    def test_a_hand_edited_file_stays_and_a_carried_leftover_leaves_with_the_switch(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        outside = tmp_path / 'shared' / 'tool.txt'
        cfg = write_config(configs, 'env.yaml', _full(outside))
        cfg_b = write_config(configs, 'b.yaml', {'name': 'B', 'rules': ['rules/rule.md']})
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        write_config(configs, 'env.yaml', _trimmed())
        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0
        assert len(_items(claude_dir)) == 3, 'the trimmed run carries three leftovers'
        core = claude_dir / 'agents' / 'core.md'
        core.write_text('# my own agent\n', encoding='utf-8')
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--yes', '--switch-config']) == 0

        guard = _guard(_output(capsys))
        assert f'[changed since written: left in place, no longer tracked] file: {core}' in guard
        for path in (claude_dir / 'agents' / 'extra.md', claude_dir / 'rules' / 'other.md'):
            assert f'[remove] file: {path}' in guard
            assert not path.exists(), f'{path} was carried from an earlier run and leaves with the switch'
        assert f'[remove] file outside ~/.claude: {outside}' in guard
        assert not outside.exists()
        assert core.read_text(encoding='utf-8') == '# my own agent\n', 'a file edited by hand stays'
        assert (claude_dir / 'rules' / 'rule.md').is_file()
        leftovers = read_manifest(claude_dir)['leftovers']
        assert leftovers['items'] == []
        assert {'label': 'file: agents/core.md', 'reason': 'changed'} in leftovers['dropped']

    @pytest.mark.parametrize('how', ['flag', 'variable'])
    def test_the_switch_flag_on_the_same_configuration_removes_nothing(
        self, how: str, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--switch-config accepts a switch; without one it is no request to remove leftovers."""
        cfg = write_config(configs, 'env.yaml', _full(tmp_path / 'shared' / 'tool.txt'))
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        write_config(configs, 'env.yaml', _trimmed())
        argv = ['--profile', 'base', *SKIP, '--yes']
        if how == 'flag':
            argv.append('--switch-config')
        else:
            monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG', '1')
        capsys.readouterr()

        assert run_main(argv) == 0

        output = _output(capsys)
        assert 'Accepted via' not in output
        assert f'  [leftover] file: {claude_dir / "agents" / "extra.md"}' in _block(output)
        assert 'Step 23: Removing leftovers' not in output
        assert (claude_dir / 'agents' / 'extra.md').is_file()
        assert (claude_dir / 'rules' / 'other.md').is_file()

    def test_a_switch_dry_run_names_what_step_23_would_remove(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        outside = tmp_path / 'shared' / 'tool.txt'
        cfg = write_config(configs, 'env.yaml', _full(outside))
        cfg_b = write_config(configs, 'b.yaml', {'name': 'B', 'rules': ['rules/rule.md']})
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        before = home_state(e2e_isolated_home['home'])
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--dry-run', '--switch-config', '--command-names', 'prof-a']) == 0

        output = _output(capsys)
        assert home_state(e2e_isolated_home['home']) == before, 'a dry run removes nothing'
        assert outside.is_file()
        marker = '[would be removed in Step 23]'
        guard = _guard(output)
        block = _block(output)
        for row in (
            f'{marker} file: {profile_dir / "agents" / "core.md"}',
            f'{marker} file: {profile_dir / "agents" / "extra.md"}',
            f'{marker} file: {profile_dir / "rules" / "other.md"}',
            f'{marker} file outside ~/.claude: {outside}',
        ):
            assert row in guard
            assert f'  {row}' in block
        assert f'remove leftover file: {outside}' in output, 'the removal outside ~/.claude is a machine-wide write'


@pytest.mark.usefixtures('e2e_isolated_home')
class TestFailedDownloadRecords:
    """A run whose content download fails records a digest only for bytes the previous run recorded."""

    def test_failed_download_keeps_only_previously_recorded_digests(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        version_1 = {'name': 'Env', 'agents': ['agents/core.md', 'agents/extra.md'], 'rules': ['rules/rule.md']}
        cfg = write_config(configs, 'env.yaml', version_1)
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        first = {record['path']: record['sha256'] for record in read_manifest(profile_dir)['files_written']}
        assert all(first.values())
        (configs / 'agents' / 'extra.md').write_text('# extra agent, next version\n', encoding='utf-8')
        write_config(configs, 'env.yaml', {
            **version_1, 'rules': ['rules/rule.md', 'rules/other.md', 'rules/missing.md'],
        })
        capsys.readouterr()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes']) == 1

        assert 'The following resources failed to download:' in _output(capsys)
        records = {record['path']: record['sha256'] for record in read_manifest(profile_dir)['files_written']}
        assert records['agents/core.md'] == first['agents/core.md'], 'unchanged bytes the previous run recorded'
        assert records['rules/rule.md'] == first['rules/rule.md']
        assert (profile_dir / 'agents' / 'extra.md').read_text(encoding='utf-8') == '# extra agent, next version\n'
        assert records['agents/extra.md'] is None, 'changed bytes are not vouched for after a failed download'
        assert (profile_dir / 'rules' / 'other.md').is_file()
        assert records['rules/other.md'] is None, 'a path the previous run did not record is not vouched for'
        assert records['rules/missing.md'] is None


@pytest.mark.usefixtures('e2e_isolated_home')
class TestDeselectedComponents:
    """A file of a component deselected this run is a removal-plan row, never a leftover."""

    def test_deselected_component_is_only_removed(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'env.yaml', {
            'name': 'Components Env',
            'agents': ['agents/core.md', 'agents/extra.md'],
            'components': [
                {'name': 'core', 'includes': {'agents': ['agents/core.md']}},
                {'name': 'extra', 'default': False, 'includes': {'agents': ['agents/extra.md']}},
            ],
        })
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a', '--with', 'extra']) == 0
        assert (profile_dir / 'agents' / 'extra.md').is_file()
        capsys.readouterr()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes', '--without', 'extra']) == 0

        output = _output(capsys)
        assert '[REMOVE]' in output
        assert 'extra.md' in output.split('[REMOVE]')[1].split('\n')[0]
        assert HEADING not in output
        assert not (profile_dir / 'agents' / 'extra.md').exists()
        assert _items(profile_dir) == []


@pytest.mark.usefixtures('e2e_isolated_home')
class TestUntrackedManifests:
    """A profile whose manifest has no leftovers field says once that tracking starts with this run."""

    def test_note_is_printed_once(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'env.yaml', _full(tmp_path / 'shared' / 'tool.txt'))
        profile_dir = e2e_isolated_home['claude_dir'] / 'prof-a'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        manifest_path = profile_dir / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.pop('leftovers')
        manifest['files_written'] = [record['path'] for record in manifest['files_written']]
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        write_config(configs, 'env.yaml', _trimmed())
        capsys.readouterr()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes']) == 0

        output = _output(capsys)
        block = _block(output)
        assert f'Profile "prof-a" {NOTE}' in block
        assert 'file: ' not in block.replace('file outside ~/.claude', ''), 'a path-only record is not read'
        assert f'[leftover] file outside ~/.claude: {tmp_path / "shared" / "tool.txt"}' in block
        assert (profile_dir / 'rules' / 'other.md').is_file()

        assert run_main(['--profile', 'prof-a', *SKIP, '--yes']) == 0

        assert NOTE not in _output(capsys), 'the note is printed once'

    def test_unresolvable_recorded_configuration_still_lists_leftovers(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A manifest naming a relative configuration that does not resolve from here is still compared."""
        cfg = write_config(configs, 'env.yaml', _full(tmp_path / 'shared' / 'tool.txt'))
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        manifest_path = claude_dir / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.update({
            'config_source': 'leftovers-unresolvable/env.yaml', 'config_source_url': None, 'config_identity': None,
        })
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        write_config(configs, 'env.yaml', _trimmed())
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert 'records a configuration that cannot be resolved from this directory' in output
        assert f'[leftover] file: {claude_dir / "rules" / "other.md"}' in _block(output)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestConversionToALink:
    """A leftover under an entry the run links belongs to the source from then on."""

    def test_converted_entry_drops_its_leftover_and_the_source_keeps_its_file(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'team.yaml', _full(tmp_path / 'shared' / 'tool.txt'))
        claude_dir = e2e_isolated_home['claude_dir']
        source_dir, lab = claude_dir / 'team-1', claude_dir / 'team-lab'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-lab']) == 0
        write_config(configs, 'team.yaml', _trimmed())
        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0
        assert 'rules/other.md' in [item['path'] for item in _items(source_dir)]
        capsys.readouterr()

        assert run_main(['--profile', 'team-lab', '--link-dirs', 'rules', '--link-from', 'team-1', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert (
            f'  [now linked from profile team-1: no longer tracked] file: {lab / "rules" / "other.md"}'
        ) in _block(output)
        assert f'       - file: {lab / "rules" / "other.md"} (now linked from profile team-1)' in output
        assert setup_environment._is_directory_link(lab / 'rules')
        assert (source_dir / 'rules' / 'other.md').is_file(), "the source's file of the same name stays"
        leftovers = read_manifest(lab)['leftovers']
        assert {'label': 'file: rules/other.md', 'reason': 'linked'} in leftovers['dropped']
        assert 'rules/other.md' not in [item['path'] for item in leftovers['items']]
        assert [item['path'] for item in leftovers['items']] == ['agents/extra.md', str(tmp_path / 'shared' / 'tool.txt')]
