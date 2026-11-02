"""E2E tests for HTTPS certificate verification of configuration and file downloads.

A configuration from a private project of a self-hosted GitLab whose
certificate the interpreter does not trust loads through main() with
GITLAB_TOKEN: the setup falls back to an unverified connection with a
warning, and the 404 GitLab answers without the token escalates to the
token exactly as on a verified connection, for the configuration, the
validation of its files and their downloads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.e2e.profile_support import run_main
from tests.e2e.tls_support import GitLabLikeServer
from tests.e2e.tls_support import self_signed_server_certificate

TOKEN = 'glpat-e2e-certificate'
FALLBACK_WARNING = 'SSL certificate verification failed, trying with unverified context'
SKIP = ['--yes', '--skip-install', '--no-admin']

AGENT = b'# Reviewer\n\nReviews changes.\n'
COMMAND = b'# Review\n\nRun a review.\n'
NOTES = b'Team notes\n'


def _configuration(command_name: str) -> bytes:
    return yaml.safe_dump({
        'name': 'Private GitLab Env',
        'command-names': [command_name],
        'agents': ['agents/reviewer.md'],
        'slash-commands': ['commands/review.md'],
        'files-to-download': [{'source': 'files/notes.txt', 'dest': f'~/{command_name}-assets/notes.txt'}],
    }, sort_keys=False).encode('utf-8')


def _project_files(command_name: str) -> dict[str, bytes]:
    return {
        'env.yaml': _configuration(command_name),
        'agents/reviewer.md': AGENT,
        'commands/review.md': COMMAND,
        'files/notes.txt': NOTES,
    }


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    return (captured.out + captured.err).replace('\r\n', '\n')


def _assert_installed(home: Path, command_name: str) -> None:
    profile = home / '.claude' / command_name
    assert (profile / 'agents' / 'reviewer.md').read_bytes() == AGENT
    assert (profile / 'commands' / 'review.md').read_bytes() == COMMAND
    assert (home / f'{command_name}-assets' / 'notes.txt').read_bytes() == NOTES


def _assert_every_file_served_with_the_token(server: GitLabLikeServer) -> None:
    for file_path in server.files:
        served = [request for request in server.requests_for(file_path) if request.status == 200]
        assert served, f'{file_path} was never served'
        assert all(request.token == TOKEN for request in served)
    assert all(request.status == 404 for request in server.requests if request.token != TOKEN)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestUntrustedCertificateAuthenticates:
    """A server certificate no trust store holds falls back, and authentication works over the fallback."""

    def test_private_gitlab_configuration_loads_with_the_token(
        self, e2e_isolated_home: dict[str, Path], tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv('GITLAB_TOKEN', TOKEN)
        certificate = self_signed_server_certificate(tmp_path / 'tls')
        with GitLabLikeServer(certificate, _project_files('tls-e2e'), TOKEN) as server:
            code = run_main([server.url('env.yaml'), *SKIP], validation_result=None)
        output = _output(capsys)
        assert code == 0, output

        _assert_installed(e2e_isolated_home['home'], 'tls-e2e')
        _assert_every_file_served_with_the_token(server)
        configuration_requests = server.requests_for('env.yaml')
        assert [(request.token, request.status) for request in configuration_requests[:2]] == [
            (None, 404),
            (TOKEN, 200),
        ]
        assert FALLBACK_WARNING in output
        assert 'Retrying with authentication...' in output
        assert 'Configuration loaded from URL: Private GitLab Env' in output

    def test_without_a_token_the_configuration_is_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        for variable in ('GITLAB_TOKEN', 'REPO_TOKEN', 'CLAUDE_CODE_TOOLBOX_ENV_AUTH'):
            monkeypatch.delenv(variable, raising=False)
        monkeypatch.setenv('PATH', str(tmp_path / 'no-cli'))
        certificate = self_signed_server_certificate(tmp_path / 'tls')
        with GitLabLikeServer(certificate, _project_files('tls-e2e'), TOKEN) as server:
            code = run_main([server.url('env.yaml'), *SKIP], validation_result=None)
        output = _output(capsys)
        assert code == 1
        assert FALLBACK_WARNING in output
        assert f'Authentication required for {server.url("env.yaml")}' in output
        assert 'HTTP Error 404: Not Found' in output
        assert all(request.token is None for request in server.requests)
