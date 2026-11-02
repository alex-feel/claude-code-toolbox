"""Tests for the plan and summary steps of the Test & Coverage workflow.

`.github/workflows/test.yml` runs its matrix jobs on Linux and Windows for
every pull request and adds macOS only when the pull request changes a file
that macOS behavior depends on; the release pull request keeps Package Smoke
on macOS, and a workflow_dispatch run puts every job on every operating
system. The plan step makes that decision from the changed files, and the
summary step reports each job's result. Both steps read their inputs from
environment variables alone, so these tests run each step script exactly as
the workflow holds it, with the bash invocation GitHub Actions uses for a
`shell: bash` step, against a scratch git repository.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.e2e.shells import find_bash

WORKFLOW_PATH = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'test.yml'

ALL_SYSTEMS = ['ubuntu-latest', 'windows-latest', 'macos-latest']
WITHOUT_MACOS = ['ubuntu-latest', 'windows-latest']

# The matrix jobs that skip on the release pull request; package-smoke runs there.
SKIPPED_ON_RELEASE_JOBS = ('test', 'test-install-scripts', 'e2e-tests')
RELEASE_HEAD_REF = 'release-please--branches--main--components--cc-toolbox'

# The base commit of the scratch repository: one file for each kind of path the plan tells apart.
BASE_FILES = (
    'README.md',
    'docs/guide.md',
    '.github/workflows/lint.yml',
    '.github/workflows/test.yml',
    'scripts/windows/install-claude-windows.ps1',
    'scripts/linux/install-claude-linux.sh',
    'scripts/macos/install-claude-macos.sh',
    'scripts/setup_environment.py',
    'scripts/install_claude.py',
    'scripts/models/environment_config.py',
    'tests/test_setup_environment.py',
    'tests/e2e/test_output_files.py',
    'pyproject.toml',
    'uv.lock',
    '.python-version',
)


@dataclass(frozen=True)
class Change:
    """What one pull request changes relative to the base commit."""

    edits: tuple[str, ...] = ()
    deletions: tuple[str, ...] = ()
    renames: tuple[tuple[str, str], ...] = ()


PULL_REQUEST_CASES = [
    pytest.param(Change(edits=('docs/guide.md', 'docs/new-page.md')), False, id='docs-only'),
    pytest.param(Change(edits=('README.md',)), False, id='readme-only'),
    pytest.param(Change(edits=('scripts/windows/install-claude-windows.ps1',)), False, id='windows-scripts-only'),
    pytest.param(Change(edits=('scripts/linux/install-claude-linux.sh',)), False, id='linux-scripts-only'),
    pytest.param(Change(edits=('.github/workflows/lint.yml',)), False, id='lint-workflow'),
    pytest.param(Change(edits=('docs/examples/pyproject.toml',)), False, id='pyproject-below-docs'),
    pytest.param(
        Change(edits=(
            'README.md',
            'docs/guide.md',
            'scripts/windows/install-claude-windows.ps1',
            'scripts/linux/install-claude-linux.sh',
            '.github/workflows/lint.yml',
        )),
        False,
        id='mix-without-macos-paths',
    ),
    pytest.param(Change(edits=('scripts/setup_environment.py',)), True, id='setup-environment'),
    pytest.param(Change(edits=('scripts/install_claude.py',)), True, id='install-claude'),
    pytest.param(Change(edits=('scripts/macos/install-claude-macos.sh',)), True, id='macos-scripts'),
    pytest.param(Change(edits=('scripts/models/environment_config.py',)), True, id='models'),
    pytest.param(Change(edits=('scripts/new_module.py',)), True, id='new-script'),
    pytest.param(Change(edits=('tests/test_setup_environment.py',)), True, id='unit-tests'),
    pytest.param(Change(edits=('tests/e2e/test_output_files.py',)), True, id='e2e-tests'),
    pytest.param(Change(edits=('pyproject.toml',)), True, id='pyproject'),
    pytest.param(Change(edits=('uv.lock',)), True, id='uv-lock'),
    pytest.param(Change(edits=('.python-version',)), True, id='python-version'),
    pytest.param(Change(edits=('.github/workflows/test.yml',)), True, id='test-workflow'),
    pytest.param(
        Change(edits=('docs/guide.md', 'scripts/windows/install-claude-windows.ps1', 'tests/test_setup_environment.py')),
        True,
        id='mix-with-a-macos-path',
    ),
    pytest.param(Change(deletions=('scripts/macos/install-claude-macos.sh',)), True, id='deleted-macos-script'),
    pytest.param(
        Change(renames=(('scripts/macos/install-claude-macos.sh', 'docs/install-claude-macos.sh'),)),
        True,
        id='macos-script-moved-to-docs',
    ),
    pytest.param(Change(edits=('tests/fixtures/données.yaml',)), True, id='non-ascii-test-fixture'),
]


def _workflow() -> dict[str, Any]:
    """Load the Test & Coverage workflow."""
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))


def _step(job: str, step_id: str) -> dict[str, Any]:
    """Return the step of a workflow job that carries the given id."""
    for step in _workflow()['jobs'][job]['steps']:
        if step.get('id') == step_id:
            return step
    raise AssertionError(f'job {job} has no step with id {step_id}')


def _run_step(
    bash: str, step: dict[str, Any], env: dict[str, str], cwd: Path, script_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Run a workflow step's script the way GitHub Actions runs a `shell: bash` step.

    Args:
        bash: The bash that runs the script.
        step: The workflow step whose `run` script runs.
        env: The complete environment of the step.
        cwd: The working directory of the step.
        script_path: Where the script is written before bash runs it.

    Returns:
        The completed bash process.
    """
    assert step['shell'] == 'bash'
    script_path.write_text(step['run'], encoding='utf-8', newline='\n')
    return subprocess.run(
        [bash, '--noprofile', '--norc', '-eo', 'pipefail', str(script_path)],
        cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', check=False, timeout=60,
    )


def _read_outputs(path: Path) -> dict[str, str]:
    """Parse the key=value lines a step appended to its GITHUB_OUTPUT file.

    Args:
        path: The GITHUB_OUTPUT file.

    Returns:
        Each output name mapped to its value.
    """
    outputs: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        name, _, value = line.partition('=')
        assert name not in outputs, f'output {name} written twice'
        outputs[name] = value
    return outputs


def _git(repo: Path, env: dict[str, str], *args: str) -> str:
    """Run git in the scratch repository and return its trimmed output.

    Args:
        repo: The scratch repository.
        env: The environment git runs with.
        *args: The git arguments.

    Returns:
        The trimmed standard output.
    """
    completed = subprocess.run(
        ['git', *args], cwd=repo, env=env, capture_output=True, text=True, encoding='utf-8', check=True, timeout=60,
    )
    return completed.stdout.strip()


def _commit(repo: Path, env: dict[str, str], message: str) -> str:
    """Commit every change in the scratch repository and return the commit id.

    Args:
        repo: The scratch repository.
        env: The environment git runs with.
        message: The commit message.

    Returns:
        The id of the new commit.
    """
    _git(repo, env, 'add', '--all')
    _git(repo, env, 'commit', '--quiet', '--message', message)
    return _git(repo, env, 'rev-parse', 'HEAD')


class ScratchRepository:
    """A git repository whose base commit holds BASE_FILES; each change becomes a commit on that base."""

    def __init__(self, root: Path, env: dict[str, str]) -> None:
        self.root = root
        self.env = env
        root.mkdir()
        _git(root, env, 'init', '--quiet')
        for name in BASE_FILES:
            self._write(name, 'base\n')
        self.base = _commit(root, env, 'base')

    def _write(self, name: str, content: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')

    def head_for(self, change: Change, *, parent: str | None = None) -> str:
        """Commit a change on top of a parent commit and return the new commit id.

        Args:
            change: The files the commit edits, deletes and renames.
            parent: The commit the change starts from; the base commit when omitted.

        Returns:
            The id of the new commit.
        """
        _git(self.root, self.env, 'checkout', '--quiet', '--detach', parent or self.base)
        for name in change.edits:
            self._write(name, f'edited {name}\n')
        for name in change.deletions:
            (self.root / name).unlink()
        for old, new in change.renames:
            target = self.root / new
            target.parent.mkdir(parents=True, exist_ok=True)
            (self.root / old).rename(target)
        return _commit(self.root, self.env, 'change')


@pytest.fixture(scope='module')
def bash() -> str:
    """Return the bash the workflow steps run under, or skip."""
    found = find_bash()
    if found is None:
        pytest.skip('bash unavailable')
    return found


@pytest.fixture(scope='module')
def git_env(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """Return an environment in which git reads no user or system configuration."""
    global_config = tmp_path_factory.mktemp('git-config') / 'gitconfig'
    global_config.write_text('', encoding='utf-8')
    env = dict(os.environ)
    env.update({
        'GIT_CONFIG_GLOBAL': str(global_config),
        'GIT_CONFIG_NOSYSTEM': '1',
        'GIT_AUTHOR_NAME': 'Workflow Test',
        'GIT_AUTHOR_EMAIL': 'workflow-test@example.invalid',
        'GIT_COMMITTER_NAME': 'Workflow Test',
        'GIT_COMMITTER_EMAIL': 'workflow-test@example.invalid',
    })
    return env


@pytest.fixture(scope='module')
def repository(tmp_path_factory: pytest.TempPathFactory, git_env: dict[str, str]) -> ScratchRepository:
    """Provide the scratch repository shared by the plan step tests."""
    return ScratchRepository(tmp_path_factory.mktemp('plan') / 'repo', git_env)


def _run_plan(
    bash: str,
    cwd: Path,
    env: dict[str, str],
    tmp_path: Path,
    *,
    event: str = 'pull_request',
    head_ref: str = '',
    base: str = '',
    head: str = '',
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    """Run the plan step with the inputs the workflow hands it.

    Args:
        bash: The bash that runs the step.
        cwd: The checkout the step runs in.
        env: The environment the step inputs are added to.
        tmp_path: Directory for the step script and its GITHUB_OUTPUT file.
        event: The event that started the run.
        head_ref: The pull request's head branch.
        base: The pull request's base commit.
        head: The pull request's head commit.

    Returns:
        The completed step and the outputs it wrote.
    """
    output = tmp_path / 'github-output'
    output.write_text('', encoding='utf-8')
    step_env = {
        **env,
        'EVENT_NAME': event,
        'HEAD_REF': head_ref,
        'BASE_SHA': base,
        'HEAD_SHA': head,
        'GITHUB_OUTPUT': str(output),
    }
    completed = _run_step(bash, _step('plan', 'plan'), step_env, cwd, tmp_path / 'plan.sh')
    return completed, _read_outputs(output)


class TestPlanStep:
    """The plan step adds macOS exactly when a change needs it, the release pull request, or a manual run."""

    @pytest.mark.parametrize(('change', 'needs_macos'), PULL_REQUEST_CASES)
    def test_pull_request_adds_macos_only_for_the_macos_path_set(
        self, bash: str, repository: ScratchRepository, tmp_path: Path, change: Change, needs_macos: bool,
    ) -> None:
        head = repository.head_for(change)
        completed, outputs = _run_plan(
            bash, repository.root, repository.env, tmp_path, base=repository.base, head=head,
        )

        assert completed.returncode == 0, completed.stderr
        expected = ALL_SYSTEMS if needs_macos else WITHOUT_MACOS
        assert json.loads(outputs['os']) == expected
        assert json.loads(outputs['package-os']) == expected
        if needs_macos:
            assert outputs['reason'].startswith('macOS runs:'), outputs['reason']
        else:
            assert outputs['reason'].startswith('macOS left out:'), outputs['reason']

    def test_moved_file_counts_under_its_old_path(
        self, bash: str, repository: ScratchRepository, tmp_path: Path,
    ) -> None:
        head = repository.head_for(
            Change(renames=(('scripts/macos/install-claude-macos.sh', 'docs/install-claude-macos.sh'),)),
        )
        completed, _ = _run_plan(bash, repository.root, repository.env, tmp_path, base=repository.base, head=head)

        assert completed.returncode == 0, completed.stderr
        assert 'scripts/macos/install-claude-macos.sh' in completed.stdout

    def test_changes_on_the_base_branch_do_not_count(
        self, bash: str, repository: ScratchRepository, tmp_path: Path,
    ) -> None:
        moved_base = repository.head_for(Change(edits=('scripts/setup_environment.py',)))
        head = repository.head_for(Change(edits=('docs/guide.md',)))
        completed, outputs = _run_plan(bash, repository.root, repository.env, tmp_path, base=moved_base, head=head)

        assert completed.returncode == 0, completed.stderr
        assert json.loads(outputs['os']) == WITHOUT_MACOS

    def test_release_pull_request_keeps_package_smoke_on_macos(
        self, bash: str, repository: ScratchRepository, tmp_path: Path,
    ) -> None:
        head = repository.head_for(Change(edits=('docs/guide.md',)))
        completed, outputs = _run_plan(
            bash, repository.root, repository.env, tmp_path,
            head_ref=RELEASE_HEAD_REF, base=repository.base, head=head,
        )

        assert completed.returncode == 0, completed.stderr
        assert json.loads(outputs['os']) == WITHOUT_MACOS
        assert json.loads(outputs['package-os']) == ALL_SYSTEMS
        assert 'release pull request' in outputs['reason']

    def test_workflow_dispatch_runs_every_job_on_every_operating_system(
        self, bash: str, git_env: dict[str, str], tmp_path: Path,
    ) -> None:
        not_a_checkout = tmp_path / 'empty'
        not_a_checkout.mkdir()
        completed, outputs = _run_plan(bash, not_a_checkout, git_env, tmp_path, event='workflow_dispatch')

        assert completed.returncode == 0, completed.stderr
        assert json.loads(outputs['os']) == ALL_SYSTEMS
        assert json.loads(outputs['package-os']) == ALL_SYSTEMS
        assert 'workflow_dispatch' in outputs['reason']

    def test_unknown_base_commit_fails_the_step_without_outputs(
        self, bash: str, repository: ScratchRepository, tmp_path: Path,
    ) -> None:
        head = repository.head_for(Change(edits=('docs/guide.md',)))
        completed, outputs = _run_plan(
            bash, repository.root, repository.env, tmp_path, base='0' * 40, head=head,
        )

        assert completed.returncode != 0
        assert outputs == {}


SUMMARY_RESULT_VARIABLES = (
    'PLAN_RESULT',
    'TEST_RESULT',
    'INSTALL_SCRIPTS_RESULT',
    'E2E_RESULT',
    'PACKAGE_SMOKE_RESULT',
)
REASON = 'macOS left out: the pull request changes nothing macOS behavior depends on.'


def _run_summary(
    bash: str, tmp_path: Path, **overrides: str,
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run the summary step after a run whose jobs all succeeded, unless overridden.

    Args:
        bash: The bash that runs the step.
        tmp_path: Directory for the step script and its GITHUB_STEP_SUMMARY file.
        **overrides: Step environment values that replace the defaults.

    Returns:
        The completed step and the Markdown it appended to GITHUB_STEP_SUMMARY.
    """
    summary = tmp_path / 'step-summary.md'
    summary.write_text('', encoding='utf-8')
    env = dict(os.environ)
    env.update(dict.fromkeys(SUMMARY_RESULT_VARIABLES, 'success'))
    env.update({
        'OS': json.dumps(WITHOUT_MACOS),
        'PACKAGE_OS': json.dumps(WITHOUT_MACOS),
        'REASON': REASON,
        'GITHUB_STEP_SUMMARY': str(summary),
    })
    env.update(overrides)
    completed = _run_step(bash, _step('summary', 'summary'), env, tmp_path, tmp_path / 'summary.sh')
    return completed, summary.read_text(encoding='utf-8')


class TestSummaryStep:
    """The summary reports each job's result and operating systems and fails on a failed or cancelled job."""

    def test_successful_run_names_the_operating_systems_of_each_job(self, bash: str, tmp_path: Path) -> None:
        completed, summary = _run_summary(bash, tmp_path)

        assert completed.returncode == 0, completed.stderr
        assert REASON in summary
        for row in (
            '| Plan Test Matrix | ubuntu-latest | success |',
            '| Test Python | ubuntu-latest, windows-latest | success |',
            '| Test Install Scripts | ubuntu-latest, windows-latest | success |',
            '| E2E Tests | ubuntu-latest, windows-latest | success |',
            '| Package Smoke | ubuntu-latest, windows-latest | success |',
        ):
            assert row in summary.splitlines(), summary
        assert summary in completed.stdout

    @pytest.mark.parametrize('result', ['failure', 'cancelled'])
    @pytest.mark.parametrize('variable', SUMMARY_RESULT_VARIABLES)
    def test_failed_or_cancelled_job_fails_the_summary(
        self, bash: str, tmp_path: Path, variable: str, result: str,
    ) -> None:
        completed, summary = _run_summary(bash, tmp_path, **{variable: result})

        assert completed.returncode == 1
        assert f'| {result} |' in summary

    def test_release_pull_request_with_skipped_jobs_passes(self, bash: str, tmp_path: Path) -> None:
        completed, summary = _run_summary(
            bash,
            tmp_path,
            TEST_RESULT='skipped',
            INSTALL_SCRIPTS_RESULT='skipped',
            E2E_RESULT='skipped',
            PACKAGE_OS=json.dumps(ALL_SYSTEMS),
        )

        assert completed.returncode == 0, completed.stderr
        lines = summary.splitlines()
        for row in (
            '| Test Python | - | skipped |',
            '| Test Install Scripts | - | skipped |',
            '| E2E Tests | - | skipped |',
            '| Package Smoke | ubuntu-latest, windows-latest, macos-latest | success |',
        ):
            assert row in lines, summary

    def test_failed_plan_fails_the_summary(self, bash: str, tmp_path: Path) -> None:
        completed, summary = _run_summary(
            bash,
            tmp_path,
            PLAN_RESULT='failure',
            TEST_RESULT='skipped',
            INSTALL_SCRIPTS_RESULT='skipped',
            E2E_RESULT='skipped',
            PACKAGE_SMOKE_RESULT='skipped',
            OS='',
            PACKAGE_OS='',
            REASON='',
        )

        assert completed.returncode == 1
        assert '| Plan Test Matrix | ubuntu-latest | failure |' in summary.splitlines()


class TestWorkflowWiring:
    """The workflow hands the plan's decision to the matrix jobs and every job's result to the summary."""

    def test_matrix_jobs_take_their_operating_systems_from_the_plan(self) -> None:
        jobs = _workflow()['jobs']
        for name in SKIPPED_ON_RELEASE_JOBS:
            assert jobs[name]['needs'] == 'plan'
            assert jobs[name]['strategy']['matrix']['os'] == '${{ fromJSON(needs.plan.outputs.os) }}'
            assert "startsWith(github.head_ref, 'release-please--branches--')" in jobs[name]['if']
        assert jobs['package-smoke']['needs'] == 'plan'
        assert jobs['package-smoke']['strategy']['matrix']['os'] == '${{ fromJSON(needs.plan.outputs.package-os) }}'
        assert 'if' not in jobs['package-smoke']

    def test_plan_job_reads_the_pull_request_history(self) -> None:
        plan = _workflow()['jobs']['plan']
        checkout = next(step for step in plan['steps'] if step.get('uses', '').startswith('actions/checkout@'))
        assert checkout['with']['fetch-depth'] == 0
        assert _step('plan', 'plan')['env'] == {
            'EVENT_NAME': '${{ github.event_name }}',
            'HEAD_REF': '${{ github.head_ref }}',
            'BASE_SHA': '${{ github.event.pull_request.base.sha }}',
            'HEAD_SHA': '${{ github.event.pull_request.head.sha }}',
        }
        assert plan['outputs'] == {
            name: f'${{{{ steps.plan.outputs.{name} }}}}' for name in ('os', 'package-os', 'reason')
        }

    def test_summary_runs_after_every_job_whatever_their_result(self) -> None:
        summary = _workflow()['jobs']['summary']
        assert set(summary['needs']) == {'plan', *SKIPPED_ON_RELEASE_JOBS, 'package-smoke'}
        assert summary['if'] == '${{ always() }}'
        assert _step('summary', 'summary')['env'] == {
            'PLAN_RESULT': '${{ needs.plan.result }}',
            'TEST_RESULT': '${{ needs.test.result }}',
            'INSTALL_SCRIPTS_RESULT': '${{ needs.test-install-scripts.result }}',
            'E2E_RESULT': '${{ needs.e2e-tests.result }}',
            'PACKAGE_SMOKE_RESULT': '${{ needs.package-smoke.result }}',
            'OS': '${{ needs.plan.outputs.os }}',
            'PACKAGE_OS': '${{ needs.plan.outputs.package-os }}',
            'REASON': '${{ needs.plan.outputs.reason }}',
        }

    @pytest.mark.parametrize(('job', 'step_id'), [('plan', 'plan'), ('summary', 'summary')])
    def test_step_script_takes_every_input_from_its_environment(self, job: str, step_id: str) -> None:
        assert '${{' not in _step(job, step_id)['run']
