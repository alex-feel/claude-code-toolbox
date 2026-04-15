"""E2E regression guard: public GitHub skill URLs must not trigger an auth prompt.

Replays the user's exact failing scenario from the original bug report -- a mini
Playwright CLI skills configuration consumed via setup_environment.validate_all_config_files.
Mocks HTTP responses so the test is deterministic and network-independent.
"""

from __future__ import annotations

import sys
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from scripts import setup_environment

PLAYWRIGHT_SKILLS_BASE = 'https://github.com/microsoft/playwright-cli/tree/main/skills/playwright-cli'

PLAYWRIGHT_SKILL_FILES = [
    'SKILL.md',
    'references/element-attributes.md',
    'references/playwright-tests.md',
    'references/request-mocking.md',
    'references/running-code.md',
    'references/session-management.md',
    'references/storage-state.md',
    'references/test-generation.md',
    'references/tracing.md',
    'references/video-recording.md',
]


@pytest.fixture
def public_github_skill_config_yaml() -> str:
    """Return the YAML text from the user's exact failing scenario."""
    files_yaml = '\n'.join(f'      - {name}' for name in PLAYWRIGHT_SKILL_FILES)
    return (
        'name: Playwright CLI with Skills\n'
        '\n'
        'install-nodejs: true\n'
        '\n'
        'dependencies:\n'
        '  common:\n'
        '    - npm install -g @playwright/cli@latest\n'
        '\n'
        'skills:\n'
        '  - name: playwright-cli\n'
        f'    base: {PLAYWRIGHT_SKILLS_BASE}\n'
        '    files:\n'
        f'{files_yaml}\n'
    )


@pytest.fixture
def public_github_skill_config(
    tmp_path: Path,
    public_github_skill_config_yaml: str,
) -> tuple[dict[str, Any], Path]:
    """Write the failing-scenario YAML to tmp_path and return (parsed_config, path)."""
    config_path = tmp_path / 'add-playwright-cli.yaml'
    config_path.write_text(public_github_skill_config_yaml, encoding='utf-8')
    config = yaml.safe_load(public_github_skill_config_yaml)
    assert isinstance(config, dict)
    return (config, config_path)


class TestPublicSkillsNoPrompt:
    """Replay the user's exact failing scenario from the original bug report."""

    def test_public_skill_urls_validate_without_prompt(
        self,
        public_github_skill_config: tuple[dict[str, Any], Path],
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Public microsoft/playwright-cli skill URLs must validate without any auth prompt.

        The lazy-auth contract, 404 disambiguation, and wording changes must together
        make the scenario succeed silently. Assertions:

        1. validate_all_config_files returns all_valid=True with no FAIL results.
        2. get_auth_headers is never called (no credential resolution attempted).
        3. input() is never called (no interactive prompt).
        4. Neither the old warning wording ('Private Github repository detected...')
           nor the new warning wording ('Authentication required for ...') appears
           in stdout/stderr -- public URLs must be fully silent on auth matters.
        5. The y/N prompt string is absent from output.

        The test mocks all HTTP I/O so it is deterministic and offline-capable.
        """
        del e2e_isolated_home  # Fixture used only for isolation side effects.

        config, config_path = public_github_skill_config

        # Mock validation probes (HEAD + Range) to return 200 (public reachable).
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            setup_environment,
            'urlopen',
            MagicMock(return_value=mock_response),
        )

        # Simulate interactive terminal -- the user's failure happened in an
        # interactive PowerShell session where the prompt appeared.
        monkeypatch.setattr(sys.stdin, 'isatty', MagicMock(return_value=True))

        # Guard: input() must NEVER be called for public URLs.
        def _fail_on_input(*_args: Any, **_kwargs: Any) -> str:
            raise AssertionError(
                'input() was called during public-URL validation -- '
                'auth prompt must not fire for public GitHub repositories.',
            )

        monkeypatch.setattr('builtins.input', _fail_on_input)

        # Guard: get_auth_headers must NEVER be called for public URLs.
        mock_get_auth = MagicMock(
            side_effect=AssertionError(
                'get_auth_headers() was called during public-URL validation -- '
                'credential resolution must not start for public GitHub repositories.',
            ),
        )
        monkeypatch.setattr(setup_environment, 'get_auth_headers', mock_get_auth)

        # Run the user's failing scenario verbatim.
        all_valid, results = setup_environment.validate_all_config_files(
            config,
            str(config_path),
        )

        # Assertion 1: Validation succeeds for all skill files.
        assert all_valid is True, f'Validation FAILED for public URLs: {results}'
        skill_results = [r for r in results if r[0] == 'skill']
        assert len(skill_results) == len(PLAYWRIGHT_SKILL_FILES), (
            f'Expected {len(PLAYWRIGHT_SKILL_FILES)} skill results, got {len(skill_results)}: '
            f'{skill_results}'
        )
        for file_type, _path, is_valid, method in skill_results:
            assert file_type == 'skill'
            assert is_valid is True
            assert method in ('HEAD', 'Range')

        # Assertion 2: get_auth_headers was never called.
        mock_get_auth.assert_not_called()

        # Assertions 3-5: No prompt wording, old or new.
        captured = capsys.readouterr()
        combined_output = captured.out + captured.err
        forbidden_phrases = [
            'Private Github repository detected',
            'Private GitHub repository detected',
            'Authentication required for',
            'Would you like to enter the token now',
            'Enter GitHub token',
            'Enter Github token',
        ]
        for phrase in forbidden_phrases:
            assert phrase not in combined_output, (
                f'Forbidden phrase found in output for public URLs: {phrase!r}\n'
                f'Captured output:\n{combined_output}'
            )

    def test_public_skill_urls_with_404_disambiguation(
        self,
        public_github_skill_config: tuple[dict[str, Any], Path],
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """404 on public skill files must skip auth prompt via api.github.com probe.

        Complements the primary test: simulates a 404 on the file URLs (e.g., missing
        reference file) AND a confirmed-public repository. The 404 disambiguation must
        classify the 404 as a genuine missing file and return failure directly without
        any auth prompt.

        This exercises the full disambiguation code path end-to-end.
        """
        del e2e_isolated_home

        config, config_path = public_github_skill_config

        # Mock validation HEAD/Range probes to return 404 (files missing).
        mock_404_error = urllib.error.HTTPError(
            url=PLAYWRIGHT_SKILLS_BASE,
            code=404,
            msg='Not Found',
            hdrs=Message(),
            fp=None,
        )

        # Mock api.github.com/repos/microsoft/playwright-cli disambiguation probe as 200
        # (repo confirmed public). validate_remote_url must return (False, ...) after
        # disambiguation, WITHOUT calling get_auth_headers.
        monkeypatch.setattr(
            setup_environment,
            '_github_repo_is_public',
            MagicMock(return_value=True),
        )

        # HEAD + Range both return 404 via urlopen raising HTTPError.
        monkeypatch.setattr(
            setup_environment,
            'urlopen',
            MagicMock(side_effect=mock_404_error),
        )

        monkeypatch.setattr(sys.stdin, 'isatty', MagicMock(return_value=True))

        def _fail_on_input(*_args: Any, **_kwargs: Any) -> str:
            raise AssertionError('input() was called despite confirmed public repo')

        monkeypatch.setattr('builtins.input', _fail_on_input)

        mock_get_auth = MagicMock(
            side_effect=AssertionError(
                'get_auth_headers() was called despite confirmed public repo',
            ),
        )
        monkeypatch.setattr(setup_environment, 'get_auth_headers', mock_get_auth)

        all_valid, _results = setup_environment.validate_all_config_files(
            config,
            str(config_path),
        )

        # Expected behavior: validation reports FAIL (files 404), but NO auth prompt.
        assert all_valid is False, (
            'Expected validation to report FAIL for 404 file URLs '
            '(the test focus is absence of auth prompt, not validity).'
        )
        mock_get_auth.assert_not_called()

        # No auth prompt wording should appear.
        captured = capsys.readouterr()
        combined_output = captured.out + captured.err
        forbidden_prompt_phrases = [
            'Authentication required for',
            'Would you like to enter the token now',
        ]
        for phrase in forbidden_prompt_phrases:
            assert phrase not in combined_output, (
                f'Auth prompt phrase {phrase!r} appeared despite public-repo disambiguation.\n'
                f'Captured output:\n{combined_output}'
            )
