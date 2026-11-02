"""Tests for HTTPS certificate verification and its unverified fallback in setup_environment.py.

Every HTTPS request the setup sends verifies the server certificate first.
When verification fails, CertificateFallbackOpener sends that request again
over an unverified connection, and every later request of the same fetch
goes there directly. The fallback is independent of authentication: a fetch
that falls back escalates on 401/403/404 to the credentials exactly as a
verified fetch does.
"""

import io
import ssl
import sys
import urllib.error
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from typing import IO
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch
from urllib.request import Request

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment
from setup_environment import AuthHeaderCache
from setup_environment import CertificateFallbackOpener
from setup_environment import FileValidator

# The ssl module's own class, read before any test points ssl.SSLContext at
# the operating system's trust store
STDLIB_SSL_CONTEXT = ssl.SSLContext

GITLAB_CONFIG_URL = 'https://gitlab.example.com/api/v4/projects/team%2Fconfigs/repository/files/env.yaml/raw?ref=main'
FALLBACK_WARNING = 'SSL certificate verification failed, trying with unverified context'


def _certificate_failure(message: str = 'certificate verify failed: self-signed certificate') -> urllib.error.URLError:
    """The URLError urlopen raises when the server certificate fails verification."""
    return urllib.error.URLError(ssl.SSLCertVerificationError(1, message))


def _refused() -> urllib.error.URLError:
    return urllib.error.URLError(ConnectionRefusedError(10061, 'refused'))


def _http_error(code: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    message = Message()
    for name, value in (headers or {}).items():
        message[name] = value
    return urllib.error.HTTPError(GITLAB_CONFIG_URL, code, 'error', message, None)


def _response(body: bytes, status: int = 200, headers: dict[str, str] | None = None) -> MagicMock:
    """A response object urlopen returns: readable, a context manager, with status and headers."""
    stream = io.BytesIO(body)
    response = MagicMock()
    response.status = status
    response.read.side_effect = stream.read
    response.headers = headers or {}
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    return response


class _Call:
    """One recorded urlopen call."""

    def __init__(self, request: str | Request, kwargs: dict[str, Any]) -> None:
        self.request = request
        self.kwargs = kwargs

    @property
    def verified(self) -> bool:
        return 'context' not in self.kwargs

    def header(self, name: str) -> str | None:
        if isinstance(self.request, str):
            return None
        return self.request.get_header(name.capitalize())


class _Server:
    """A urlopen replacement that answers each call from a function of the call."""

    def __init__(self, answer: Callable[[_Call], object]) -> None:
        self.calls: list[_Call] = []
        self._answer = answer

    def __call__(self, request: str | Request, **kwargs: Any) -> object:
        call = _Call(request, kwargs)
        self.calls.append(call)
        outcome = self._answer(call)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _untrusted(answer: object) -> Callable[[_Call], object]:
    """A server whose certificate fails verification and which answers unverified requests with ``answer``."""
    return lambda call: _certificate_failure() if call.verified else answer


def _untrusted_gitlab(call: _Call, token: str = 'glpat-test', body: bytes = b'name: Private Env\n') -> object:
    """A GitLab whose certificate fails verification and which hides private files without the token."""
    if call.verified:
        return _certificate_failure()
    if call.header('PRIVATE-TOKEN') != token:
        return _http_error(404)
    return _response(body)


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


def _clear_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ('GITLAB_TOKEN', 'GITHUB_TOKEN', 'REPO_TOKEN', 'CLAUDE_CODE_TOOLBOX_ENV_AUTH'):
        monkeypatch.delenv(variable, raising=False)


class TestCertificateFallbackOpener:
    """The opener verifies first and falls back to an unverified connection only on a certificate failure."""

    def test_verified_request_sends_no_context(self) -> None:
        server = _Server(lambda _call: _response(b'ok'))
        with patch.object(setup_environment, 'urlopen', server):
            response = CertificateFallbackOpener().open('https://example.com/file')
        assert response.read() == b'ok'
        assert len(server.calls) == 1
        assert server.calls[0].verified

    def test_certificate_failure_retries_unverified_and_warns_once(self, capsys: pytest.CaptureFixture[str]) -> None:
        server = _Server(lambda call: _certificate_failure() if call.verified else _response(b'ok'))
        opener = CertificateFallbackOpener()
        with patch.object(setup_environment, 'urlopen', server):
            assert opener.open('https://example.com/a').read() == b'ok'
            assert opener.open('https://example.com/b').read() == b'ok'
        assert [call.verified for call in server.calls] == [True, False, False]
        assert _output(capsys).count(FALLBACK_WARNING) == 1
        assert opener.verifies is False

    def test_unverified_context_skips_every_check(self) -> None:
        server = _Server(_untrusted(_response(b'ok')))
        with patch.object(setup_environment, 'urlopen', server):
            CertificateFallbackOpener().open('https://example.com/file')
        context = server.calls[1].kwargs['context']
        assert type(context) is STDLIB_SSL_CONTEXT
        assert context.verify_mode == ssl.CERT_NONE
        assert context.check_hostname is False

    def test_failure_message_does_not_decide_the_fallback(self) -> None:
        """A certificate failure whose text names neither SSL nor a certificate still falls back."""
        server = _Server(
            lambda call: _certificate_failure('The trust provider rejected the chain') if call.verified else _response(b'ok'),
        )
        with patch.object(setup_environment, 'urlopen', server):
            assert CertificateFallbackOpener().open('https://example.com/file').read() == b'ok'
        assert len(server.calls) == 2

    def test_fallback_without_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        server = _Server(_untrusted(_response(b'ok')))
        with patch.object(setup_environment, 'urlopen', server):
            CertificateFallbackOpener(warn_on_fallback=False).open('https://example.com/file')
        assert len(server.calls) == 2
        assert FALLBACK_WARNING not in _output(capsys)

    def test_other_tls_failure_is_raised_without_retry(self) -> None:
        handshake = urllib.error.URLError(ssl.SSLError(1, '[SSL: WRONG_VERSION_NUMBER] wrong version number'))
        server = _Server(lambda _call: handshake)
        with patch.object(setup_environment, 'urlopen', server), pytest.raises(urllib.error.URLError) as raised:
            CertificateFallbackOpener().open('https://example.com/file')
        assert raised.value is handshake
        assert len(server.calls) == 1

    def test_network_failure_is_raised_without_retry(self) -> None:
        server = _Server(lambda _call: _refused())
        with patch.object(setup_environment, 'urlopen', server), pytest.raises(urllib.error.URLError):
            CertificateFallbackOpener().open('https://example.com/file')
        assert len(server.calls) == 1

    def test_http_error_is_raised_without_retry(self) -> None:
        server = _Server(lambda _call: _http_error(404))
        with patch.object(setup_environment, 'urlopen', server), pytest.raises(urllib.error.HTTPError):
            CertificateFallbackOpener().open('https://example.com/file')
        assert len(server.calls) == 1

    def test_timeout_reaches_both_attempts(self) -> None:
        server = _Server(_untrusted(_response(b'ok')))
        with patch.object(setup_environment, 'urlopen', server):
            CertificateFallbackOpener().open('https://example.com/file', timeout=7)
        assert [call.kwargs.get('timeout') for call in server.calls] == [7, 7]

    def test_no_timeout_keeps_the_default(self) -> None:
        server = _Server(lambda _call: _response(b'ok'))
        with patch.object(setup_environment, 'urlopen', server):
            CertificateFallbackOpener().open('https://example.com/file')
        assert 'timeout' not in server.calls[0].kwargs


class TestFetchEscalatesAfterFallback:
    """A fetch that falls back to an unverified connection authenticates exactly as a verified one."""

    def test_unverified_404_escalates_to_the_token(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv('GITLAB_TOKEN', 'glpat-test')
        server = _Server(_untrusted_gitlab)
        with patch.object(setup_environment, 'urlopen', server):
            content = setup_environment.fetch_url_with_auth(GITLAB_CONFIG_URL)
        assert content == 'name: Private Env\n'
        assert [(call.verified, call.header('PRIVATE-TOKEN')) for call in server.calls] == [
            (True, None),
            (False, None),
            (False, 'glpat-test'),
        ]
        output = _output(capsys)
        assert output.count(FALLBACK_WARNING) == 1
        assert 'Retrying with authentication...' in output

    def test_resolved_headers_reach_the_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('GITLAB_TOKEN', 'glpat-test')
        cache = AuthHeaderCache()
        with patch.object(setup_environment, 'urlopen', _Server(_untrusted_gitlab)):
            setup_environment.fetch_url_with_auth(GITLAB_CONFIG_URL, auth_cache=cache)
        assert cache.get_cached_headers(GITLAB_CONFIG_URL) == (True, {'PRIVATE-TOKEN': 'glpat-test'})

    def test_cached_headers_go_unverified_with_the_token(self) -> None:
        cache = AuthHeaderCache()
        cache.cache_headers(GITLAB_CONFIG_URL, {'PRIVATE-TOKEN': 'glpat-test'})
        server = _Server(_untrusted_gitlab)
        with patch.object(setup_environment, 'urlopen', server):
            content = setup_environment.fetch_url_with_auth(GITLAB_CONFIG_URL, auth_cache=cache)
        assert content == 'name: Private Env\n'
        assert [(call.verified, call.header('PRIVATE-TOKEN')) for call in server.calls] == [
            (True, 'glpat-test'),
            (False, 'glpat-test'),
        ]

    def test_without_credentials_the_404_surfaces(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        _clear_credentials(monkeypatch)
        server = _Server(_untrusted_gitlab)
        with (
            patch.object(setup_environment, 'urlopen', server),
            patch.object(setup_environment, 'cli_stored_token', return_value=None),
            pytest.raises(urllib.error.HTTPError) as raised,
        ):
            setup_environment.fetch_url_with_auth(GITLAB_CONFIG_URL)
        assert raised.value.code == 404
        assert len(server.calls) == 2
        output = _output(capsys)
        assert f'Authentication required for {GITLAB_CONFIG_URL}' in output
        assert 'Retrying with authentication...' not in output

    def test_wrong_token_reports_the_missing_resource(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv('GITLAB_TOKEN', 'glpat-wrong')
        with (
            patch.object(setup_environment, 'urlopen', _Server(_untrusted_gitlab)),
            pytest.raises(urllib.error.HTTPError),
        ):
            setup_environment.fetch_url_with_auth(GITLAB_CONFIG_URL)
        assert 'Resource not found. Check URL and permissions.' in _output(capsys)

    def test_unverified_401_without_credentials_names_authentication(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        _clear_credentials(monkeypatch)
        server = _Server(_untrusted(_http_error(401)))
        with (
            patch.object(setup_environment, 'urlopen', server),
            patch.object(setup_environment, 'cli_stored_token', return_value=None),
            pytest.raises(urllib.error.HTTPError),
        ):
            setup_environment.fetch_url_with_auth(GITLAB_CONFIG_URL)
        assert 'Authentication may be required for this URL' in _output(capsys)

    def test_rate_limit_retry_stays_unverified(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv('GITLAB_TOKEN', 'glpat-test')
        answers = iter([_certificate_failure(), _http_error(429, {'Retry-After': '0'}), _response(b'name: Env\n')])
        server = _Server(lambda _call: next(answers))
        with patch.object(setup_environment, 'urlopen', server), patch.object(setup_environment.time, 'sleep'):
            content = setup_environment.fetch_url_with_auth(GITLAB_CONFIG_URL)
        assert content == 'name: Env\n'
        assert [call.verified for call in server.calls] == [True, False, False]
        assert _output(capsys).count(FALLBACK_WARNING) == 1

    def test_non_certificate_failure_is_not_retried(self) -> None:
        refused = _refused()
        server = _Server(lambda _call: refused)
        with patch.object(setup_environment, 'urlopen', server), pytest.raises(urllib.error.URLError) as raised:
            setup_environment.fetch_url_with_auth(GITLAB_CONFIG_URL)
        assert raised.value is refused
        assert len(server.calls) == 1

    def test_bytes_fetch_escalates_after_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('GITLAB_TOKEN', 'glpat-test')
        server = _Server(lambda call: _untrusted_gitlab(call, body=b'\x00\x01binary'))
        with patch.object(setup_environment, 'urlopen', server):
            content = setup_environment.fetch_url_bytes_with_auth(GITLAB_CONFIG_URL)
        assert content == b'\x00\x01binary'

    def test_github_api_headers_reach_the_unverified_requests(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('GITHUB_TOKEN', 'ghp-test')

        def github(call: _Call) -> object:
            if call.verified:
                return _certificate_failure()
            if call.header('Authorization') != 'Bearer ghp-test':
                return _http_error(404)
            return _response(b'name: GitHub Env\n')

        server = _Server(github)
        with patch.object(setup_environment, 'urlopen', server):
            content = setup_environment.fetch_url_with_auth('https://raw.githubusercontent.com/org/repo/main/env.yaml')
        assert content == 'name: GitHub Env\n'
        assert len(server.calls) == 3
        assert all(call.header('Accept') == 'application/vnd.github.raw+json' for call in server.calls)
        assert all(call.header('X-github-api-version') == '2022-11-28' for call in server.calls)


class TestValidatorFallback:
    """Validation falls back silently and escalates on the unverified HTTP code."""

    @pytest.mark.parametrize('method', ['_check_with_head', '_check_with_range'])
    def test_check_falls_back_on_a_certificate_failure(self, method: str, capsys: pytest.CaptureFixture[str]) -> None:
        server = _Server(_untrusted(_response(b'', status=200)))
        with patch.object(setup_environment, 'urlopen', server):
            result = getattr(FileValidator(), method)('https://example.com/file.md', None)
        assert result == (True, 200)
        assert [call.verified for call in server.calls] == [True, False]
        assert FALLBACK_WARNING not in _output(capsys)

    @pytest.mark.parametrize('method', ['_check_with_head', '_check_with_range'])
    def test_check_reports_the_unverified_http_code(self, method: str) -> None:
        server = _Server(_untrusted(_http_error(404)))
        with patch.object(setup_environment, 'urlopen', server):
            assert getattr(FileValidator(), method)('https://example.com/file.md', None) == (False, 404)

    @pytest.mark.parametrize('method', ['_check_with_head', '_check_with_range'])
    def test_check_reports_no_code_for_a_failed_unverified_retry(self, method: str) -> None:
        server = _Server(_untrusted(_refused()))
        with patch.object(setup_environment, 'urlopen', server):
            assert getattr(FileValidator(), method)('https://example.com/file.md', None) == (False, None)

    def test_validation_escalates_after_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('GITLAB_TOKEN', 'glpat-test')
        server = _Server(_untrusted_gitlab)
        with patch.object(setup_environment, 'urlopen', server):
            assert FileValidator(auth_cache=AuthHeaderCache()).validate_remote_url(GITLAB_CONFIG_URL) == (True, 'HEAD')
        assert server.calls[-1].header('PRIVATE-TOKEN') == 'glpat-test'


class TestNodeDownloadsFallBack:
    """The Node.js release documents and installers share the fallback."""

    def test_release_document_falls_back_with_its_timeout(self, capsys: pytest.CaptureFixture[str]) -> None:
        server = _Server(_untrusted(_response(b'[{"version": "v24.1.0"}]')))
        with patch.object(setup_environment, 'urlopen', server):
            document = setup_environment._fetch_node_release_json('https://nodejs.org/dist/index.json')
        assert document == [{'version': 'v24.1.0'}]
        timeout = setup_environment.NODE_RELEASE_FETCH_TIMEOUT_SECONDS
        assert [call.kwargs.get('timeout') for call in server.calls] == [timeout, timeout]
        assert FALLBACK_WARNING in _output(capsys)

    def test_release_document_network_failure_raises(self) -> None:
        with (
            patch.object(setup_environment, 'urlopen', _Server(lambda _call: _refused())),
            pytest.raises(urllib.error.URLError),
        ):
            setup_environment._fetch_node_release_json('https://nodejs.org/dist/index.json')

    def test_installer_download_writes_the_temporary_file(self) -> None:
        body = b'installer bytes' * 1000
        server = _Server(lambda _call: _response(body, headers={'Content-Length': str(len(body))}))
        with patch.object(setup_environment, 'urlopen', server):
            path = setup_environment._download_nodejs_installer('https://nodejs.org/dist/v24.1.0/node-v24.1.0.pkg')
        try:
            assert path.endswith('.pkg')
            assert Path(path).read_bytes() == body
        finally:
            Path(path).unlink()

    def test_installer_download_falls_back(self, capsys: pytest.CaptureFixture[str]) -> None:
        server = _Server(_untrusted(_response(b'msi')))
        with patch.object(setup_environment, 'urlopen', server):
            path = setup_environment._download_nodejs_installer('https://nodejs.org/dist/v24.1.0/node-v24.1.0-x64.msi')
        try:
            assert Path(path).read_bytes() == b'msi'
            assert FALLBACK_WARNING in _output(capsys)
        finally:
            Path(path).unlink()

    def test_truncated_installer_download_raises_and_deletes_the_file(self) -> None:
        server = _Server(lambda _call: _response(b'short', headers={'Content-Length': '100'}))
        created: list[str] = []
        real_named_temporary_file = setup_environment.tempfile.NamedTemporaryFile

        def recording_temporary_file(*args: Any, **kwargs: Any) -> IO[bytes]:
            handle = real_named_temporary_file(*args, **kwargs)
            created.append(handle.name)
            return handle

        with (
            patch.object(setup_environment, 'urlopen', server),
            patch.object(setup_environment.tempfile, 'NamedTemporaryFile', recording_temporary_file),
            pytest.raises(urllib.error.ContentTooShortError, match='got only 5 out of 100 bytes'),
        ):
            setup_environment._download_nodejs_installer('https://nodejs.org/dist/v24.1.0/node-v24.1.0.pkg')
        assert created
        assert not Path(created[0]).exists()


class TestWindowsBootstrapDownloadFallsBack:
    """The Windows bootstrap installer download shares the fallback."""

    def test_bootstrap_script_downloads_after_a_certificate_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        server = _Server(_untrusted(_response(b'# PowerShell script')))
        with (
            patch('pathlib.Path.is_file', return_value=False),
            patch('platform.system', return_value='Windows'),
            patch.object(setup_environment, 'urlopen', server),
            patch.object(setup_environment, 'run_command', return_value=MagicMock(returncode=0)) as run,
        ):
            assert setup_environment.install_claude() is True
        assert [call.verified for call in server.calls] == [True, False]
        assert FALLBACK_WARNING in _output(capsys)
        assert Path(run.call_args[0][0][-1]).suffix == '.ps1'


class TestOsTrustStore:
    """main() verifies HTTPS against the operating system's trust store."""

    def test_injection_replaces_the_ssl_context_class(self) -> None:
        import truststore

        setup_environment.use_os_trust_store()
        assert ssl.SSLContext is truststore.SSLContext
        assert isinstance(ssl.create_default_context(), truststore.SSLContext)

    def test_repeated_injection_keeps_one_context_class(self) -> None:
        import truststore

        setup_environment.use_os_trust_store()
        setup_environment.use_os_trust_store()
        assert ssl.SSLContext is truststore.SSLContext

    def test_missing_truststore_keeps_the_interpreter_bundle(self) -> None:
        with patch.dict(sys.modules, {'truststore': None}):
            setup_environment.use_os_trust_store()
        assert ssl.SSLContext is STDLIB_SSL_CONTEXT

    def test_unverified_context_stays_a_standard_library_context(self) -> None:
        """Under the OS trust store, the fallback still skips every check, on macOS too."""
        setup_environment.use_os_trust_store()
        context = setup_environment._unverified_ssl_context()
        assert type(context) is STDLIB_SSL_CONTEXT
        assert context.verify_mode == ssl.CERT_NONE
        assert context.check_hostname is False

    def test_main_injects_before_parsing_arguments(self) -> None:
        with (
            patch.object(setup_environment, 'use_os_trust_store', side_effect=RuntimeError('trust store first')),
            patch('sys.argv', ['setup_environment.py', '--help']),
            pytest.raises(RuntimeError, match='trust store first'),
        ):
            setup_environment.main()
