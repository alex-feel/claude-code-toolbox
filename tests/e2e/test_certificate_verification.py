"""E2E tests for HTTPS certificate verification of configuration and file downloads.

A configuration from a private project of a self-hosted GitLab whose
certificate the interpreter does not trust loads through main() with
GITLAB_TOKEN: the setup falls back to an unverified connection with a
warning, and the 404 GitLab answers without the token escalates to the
token exactly as on a verified connection, for the configuration, the
validation of its files and their downloads.

Two tests change the machine's certificate state, so they run only where
CLAUDE_CODE_TOOLBOX_E2E_REAL_TRUST_STORE=1, which the E2E CI job sets, and
undo the change whatever the outcome. The real trust-store test installs a
certificate authority made for the run into the operating system's trust
store and proves that main() then verifies a server certificate it issued,
with no fallback at all. The Windows chain-engine test proves that, under
the OS trust store, a server certificate whose intermediate the server
leaves out verifies on Windows: the chain engine downloads the intermediate
from the address the certificate names, keeps a copy in the user's
intermediate certificate store and the address in its URL cache, and the
test deletes both and checks that they are gone.
"""

from __future__ import annotations

import hashlib
import os
import ssl
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.request import Request

import pytest
import yaml

from scripts import setup_environment
from tests.e2e.profile_support import run_main
from tests.e2e.tls_support import CertificateAuthority
from tests.e2e.tls_support import GitLabLikeServer
from tests.e2e.tls_support import make_certificate_authority
from tests.e2e.tls_support import self_signed_server_certificate
from tests.e2e.tls_support import server_naming_its_issuer

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
    # Well inside the test's own timeout, so a command waiting for an
    # authorization prompt fails here with its name instead of stalling
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    except subprocess.TimeoutExpired:
        pytest.fail(f'{" ".join(command)} did not finish within 30 seconds')
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
    """Remove the authority from the operating system's trust store again.

    On macOS the certificate leaves the System keychain. Its admin trust
    setting stays: removing that setting waits for an authorization prompt
    even under sudo, and a trust setting whose certificate no keychain holds
    trusts nothing, because the server sends only its own certificate and
    every run makes a new authority.
    """
    if sys.platform == 'win32':
        _run(['certutil', '-delstore', 'Root', authority.fingerprint])
    elif sys.platform == 'darwin':
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


def _certutil(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['certutil', *arguments], capture_output=True, text=True, check=False, timeout=120)


def _kept_by_the_chain_engine(intermediate: CertificateAuthority, issuer_url: str) -> list[str]:
    """What the Windows chain engine still keeps of a downloaded intermediate.

    The intermediate counts when any certificate store of the machine or the
    user holds a certificate with its DER bytes, and the address counts when
    certutil lists it in the URL cache of the current user.

    Returns:
        A description of each copy found; empty when nothing is left.
    """
    kept: list[str] = []
    fingerprint = intermediate.fingerprint.lower()
    if sys.platform == 'win32' and any(
        hashlib.sha1(certificate, usedforsecurity=False).hexdigest() == fingerprint
        for certificate, _, _ in ssl.enum_certificates('CA')
    ):
        kept.append(f'intermediate {intermediate.fingerprint} in the CA certificate store')
    if issuer_url in (line.strip() for line in _certutil('-urlcache', issuer_url).stdout.splitlines()):
        kept.append(f'{issuer_url} in the URL cache')
    return kept


def _forget_downloaded_intermediate(intermediate: CertificateAuthority, issuer_url: str) -> None:
    """Delete the copy of the intermediate and the cached address the chain engine keeps after a download."""
    _certutil('-user', '-delstore', 'CA', intermediate.fingerprint)
    _certutil('-urlcache', issuer_url, 'delete')


@pytest.mark.real_trust_store
@pytest.mark.skipif(sys.platform != 'win32', reason='exercises the Windows certificate chain engine')
@pytest.mark.skipif(
    os.environ.get(REAL_TRUST_STORE_VARIABLE) != '1',
    reason=(
        'the Windows chain engine keeps a downloaded intermediate in the certificate store and URL cache of the user; '
        f'runs where {REAL_TRUST_STORE_VARIABLE}=1 (the E2E CI job)'
    ),
)
class TestWindowsChainEngineDownloadsTheIntermediate:
    """Under the OS trust store, Windows completes a chain whose intermediate the server leaves out."""

    def test_missing_intermediate_is_downloaded_and_verifies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        run = uuid.uuid4().hex[:12]
        root = make_certificate_authority(tmp_path / 'root', f'cc-toolbox E2E root CA {run}', path_length=1)
        monkeypatch.setenv('SSL_CERT_FILE', str(root.authority.certificate))
        configuration = _configuration('chain-e2e')
        with server_naming_its_issuer(
            root, tmp_path, {'env.yaml': configuration}, TOKEN, intermediate_name=f'cc-toolbox E2E intermediate CA {run}',
        ) as (server, issuer, intermediate):
            try:
                setup_environment.use_os_trust_store()
                opener = setup_environment.CertificateFallbackOpener()
                with opener.open(Request(server.url('env.yaml'), headers={'PRIVATE-TOKEN': TOKEN})) as response:
                    body = response.read()
                downloads = issuer.recorded()
            finally:
                _forget_downloaded_intermediate(intermediate, issuer.url)
            left_behind = _kept_by_the_chain_engine(intermediate, issuer.url)
        assert body == configuration
        assert opener.verifies is True
        assert FALLBACK_WARNING not in _output(capsys)
        assert downloads
        assert set(downloads) == {('GET', issuer.path)}
        assert left_behind == []
