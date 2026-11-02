"""E2E tests for HTTPS certificate verification of configuration and file downloads.

A configuration from a private project of a self-hosted GitLab whose
certificate the interpreter does not trust loads through main() with
GITLAB_TOKEN: the setup falls back to an unverified connection with a
warning, and the 404 GitLab answers without the token escalates to the
token exactly as on a verified connection, for the configuration, the
validation of its files and their downloads.

The real trust-store test installs a certificate authority made for the
run into the operating system's trust store and proves that main() then
verifies a server certificate it issued, with no fallback at all. It changes
the machine's trust store, so it runs only where
CLAUDE_CODE_TOOLBOX_E2E_REAL_TRUST_STORE=1, which the E2E CI job sets, and
removes the authority again whatever the outcome.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import yaml

from tests.e2e.profile_support import run_main
from tests.e2e.tls_support import CertificateAuthority
from tests.e2e.tls_support import GitLabLikeServer
from tests.e2e.tls_support import make_certificate_authority
from tests.e2e.tls_support import self_signed_server_certificate

TOKEN = 'glpat-e2e-certificate'
FALLBACK_WARNING = 'SSL certificate verification failed, trying with unverified context'
REAL_TRUST_STORE_VARIABLE = 'CLAUDE_CODE_TOOLBOX_E2E_REAL_TRUST_STORE'
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


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    if result.returncode != 0:
        pytest.fail(f'{" ".join(command)} exited with {result.returncode}:\n{result.stdout}\n{result.stderr}')


def _linux_anchor(authority: CertificateAuthority) -> Path:
    return Path('/usr/local/share/ca-certificates') / f'cc-toolbox-e2e-{authority.fingerprint.lower()}.crt'


def _trust(authority: CertificateAuthority) -> None:
    """Add the authority to the trust store the operating system verifies TLS servers against."""
    certificate = str(authority.authority.certificate)
    if sys.platform == 'win32':
        _run(['certutil', '-addstore', '-f', 'Root', certificate])
    elif sys.platform == 'darwin':
        _run([
            'sudo', 'security', 'add-trusted-cert', '-d', '-r', 'trustRoot',
            '-k', '/Library/Keychains/System.keychain', certificate,
        ])
    else:
        _run(['sudo', 'cp', certificate, str(_linux_anchor(authority))])
        _run(['sudo', 'update-ca-certificates'])


def _distrust(authority: CertificateAuthority) -> None:
    """Remove the authority from the operating system's trust store again."""
    if sys.platform == 'win32':
        _run(['certutil', '-delstore', 'Root', authority.fingerprint])
    elif sys.platform == 'darwin':
        _run(['sudo', 'security', 'remove-trusted-cert', '-d', str(authority.authority.certificate)])
        _run(['sudo', 'security', 'delete-certificate', '-Z', authority.fingerprint, '/Library/Keychains/System.keychain'])
    else:
        _run(['sudo', 'rm', '-f', str(_linux_anchor(authority))])
        _run(['sudo', 'update-ca-certificates', '--fresh'])


@pytest.mark.real_trust_store
@pytest.mark.usefixtures('e2e_isolated_home')
@pytest.mark.skipif(
    os.environ.get(REAL_TRUST_STORE_VARIABLE) != '1',
    reason=f'changes the operating system trust store; runs where {REAL_TRUST_STORE_VARIABLE}=1 (the E2E CI job)',
)
class TestOsTrustStore:
    """main() verifies HTTPS against the operating system's trust store."""

    def test_authority_in_the_os_trust_store_verifies_without_fallback(
        self, e2e_isolated_home: dict[str, Path], tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv('GITLAB_TOKEN', TOKEN)
        authority = make_certificate_authority(tmp_path / 'tls', f'cc-toolbox E2E trust store CA {uuid.uuid4().hex[:12]}')
        with GitLabLikeServer(authority.server, _project_files('trust-e2e'), TOKEN) as server:
            # Before the authority is trusted, nothing on the machine knows it
            assert run_main([server.url('env.yaml'), *SKIP], validation_result=None) == 0
            assert FALLBACK_WARNING in _output(capsys)

            _trust(authority)
            try:
                code = run_main([server.url('env.yaml'), *SKIP], validation_result=None)
            finally:
                _distrust(authority)
        output = _output(capsys)
        assert code == 0, output
        assert FALLBACK_WARNING not in output
        _assert_installed(e2e_isolated_home['home'], 'trust-e2e')
        _assert_every_file_served_with_the_token(server)
