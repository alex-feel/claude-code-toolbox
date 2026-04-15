"""Tests for pre-download validation functionality in setup_environment.py."""

import os
import sys
import tempfile
import threading
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment
from setup_environment import AuthHeaderCache
from setup_environment import FileValidator


class TestFileValidator:
    """Test the unified FileValidator class."""

    def test_init_with_auth_param(self) -> None:
        """Test FileValidator initialization with auth parameter."""
        validator = FileValidator(auth_param='Bearer token123')
        assert validator.auth_param == 'Bearer token123'

    def test_init_without_auth_param(self) -> None:
        """Test FileValidator initialization without auth parameter."""
        validator = FileValidator()
        assert validator.auth_param is None

    @patch('setup_environment.urlopen')
    def test_check_with_head_success(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request success returns (True, 200)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        result = validator._check_with_head('https://example.com/file.md', None)

        assert result == (True, 200)
        mock_urlopen.assert_called_once()
        request = mock_urlopen.call_args[0][0]
        assert request.get_method() == 'HEAD'
        assert request.full_url == 'https://example.com/file.md'

    @patch('setup_environment.urlopen')
    def test_check_with_head_with_auth(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request with authentication headers returns (True, 200)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        auth_headers = {'Authorization': 'Bearer token'}
        result = validator._check_with_head('https://example.com/file.md', auth_headers)

        assert result == (True, 200)
        request = mock_urlopen.call_args[0][0]
        assert request.headers.get('Authorization') == 'Bearer token'

    @patch('setup_environment.urlopen')
    def test_check_with_head_not_found(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request with 404 returns (False, 404)."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://example.com/file.md',
            404,
            'Not Found',
            {},
            None,
        )

        validator = FileValidator()
        result = validator._check_with_head('https://example.com/file.md', None)

        assert result == (False, 404)

    @patch('setup_environment.urlopen')
    def test_check_with_head_ssl_error_retry(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request with SSL error and successful retry returns (True, 200)."""
        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            MagicMock(status=200),
        ]

        validator = FileValidator()
        result = validator._check_with_head('https://example.com/file.md', None)

        assert result == (True, 200)
        assert mock_urlopen.call_count == 2
        second_call_context = mock_urlopen.call_args_list[1][1].get('context')
        assert second_call_context is not None

    @patch('setup_environment.urlopen')
    def test_check_with_head_non_ssl_error(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request with non-SSL URLError returns (False, None)."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        validator = FileValidator()
        result = validator._check_with_head('https://example.com/file.md', None)

        assert result == (False, None)
        assert mock_urlopen.call_count == 1

    @patch('setup_environment.urlopen')
    def test_check_with_range_success_200(self, mock_urlopen: MagicMock) -> None:
        """Test successful Range request with 200 response returns (True, 200)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result == (True, 200)
        request = mock_urlopen.call_args[0][0]
        assert request.headers.get('Range') == 'bytes=0-0'

    @patch('setup_environment.urlopen')
    def test_check_with_range_success_206(self, mock_urlopen: MagicMock) -> None:
        """Test successful Range request with 206 partial content returns (True, 206)."""
        mock_response = MagicMock()
        mock_response.status = 206
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result == (True, 206)

    @patch('setup_environment.urlopen')
    def test_check_with_range_with_auth(self, mock_urlopen: MagicMock) -> None:
        """Test Range request with authentication headers returns (True, 206)."""
        mock_response = MagicMock()
        mock_response.status = 206
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        auth_headers = {'Authorization': 'Token abc123', 'X-Custom': 'value'}
        result = validator._check_with_range('https://example.com/file.md', auth_headers)

        assert result == (True, 206)
        request = mock_urlopen.call_args[0][0]
        assert request.headers.get('Authorization') == 'Token abc123'
        assert request.headers.get('X-custom') == 'value'
        assert request.headers.get('Range') == 'bytes=0-0'

    @patch('setup_environment.urlopen')
    def test_check_with_range_ssl_error_retry(self, mock_urlopen: MagicMock) -> None:
        """Test Range request with SSL error and successful retry returns (True, 206)."""
        mock_urlopen.side_effect = [
            urllib.error.URLError('certificate verify failed'),
            MagicMock(status=206),
        ]

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result == (True, 206)
        assert mock_urlopen.call_count == 2

    @patch('setup_environment.urlopen')
    def test_check_with_range_http_error(self, mock_urlopen: MagicMock) -> None:
        """Test Range request with HTTP error returns (False, 416)."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://example.com/file.md',
            416,
            'Range Not Satisfiable',
            {},
            None,
        )

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result == (False, 416)

    @patch('setup_environment.urlopen')
    def test_check_with_range_generic_exception(self, mock_urlopen: MagicMock) -> None:
        """Test Range request with generic exception returns (False, None)."""
        mock_urlopen.side_effect = Exception('Network error')

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result == (False, None)

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_validate_remote_url_generates_auth_per_url(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test that validate_remote_url generates auth for the specific URL on escalation.

        Verifies the lazy-auth contract: auth is invoked only after the initial
        unauthenticated probe returns a 401/403/404 status. Mirrors the contract
        honored by _fetch_url_core._do_fetch (lazy-auth gate on HTTP 401/403/404).

        CRITICAL: auth is generated for the FILE URL, not the config source.
        """
        mock_auth.return_value = {'Authorization': 'Bearer token'}
        # Force escalation: initial unauth HEAD returns 404, Range returns 404;
        # retry HEAD with auth succeeds.
        mock_head.side_effect = [(False, 404), (True, 200)]
        mock_range.return_value = (False, 404)

        validator = FileValidator(auth_param='my_token')
        result = validator.validate_remote_url('https://github.com/user/repo/file.md')

        assert result == (True, 'HEAD')
        # CRITICAL: auth must be generated for the FILE URL, not config source.
        mock_auth.assert_called_once_with(
            'https://github.com/user/repo/file.md',
            'my_token',
        )

    @patch.object(FileValidator, '_check_with_head')
    @patch.object(FileValidator, '_check_with_range')
    def test_validate_remote_url_head_success(
        self,
        mock_range: MagicMock,
        mock_head: MagicMock,
    ) -> None:
        """Test validation succeeds with HEAD request."""
        mock_head.return_value = (True, 200)
        mock_range.return_value = (False, 500)

        validator = FileValidator()
        with patch('setup_environment.get_auth_headers', return_value=None):
            is_valid, method = validator.validate_remote_url('https://example.com/file.md')

        assert is_valid is True
        assert method == 'HEAD'
        mock_head.assert_called_once()
        mock_range.assert_not_called()

    @patch.object(FileValidator, '_check_with_head')
    @patch.object(FileValidator, '_check_with_range')
    def test_validate_remote_url_fallback_to_range(
        self,
        mock_range: MagicMock,
        mock_head: MagicMock,
    ) -> None:
        """Test validation falls back to Range when HEAD fails with non-auth code."""
        mock_head.return_value = (False, 500)
        mock_range.return_value = (True, 206)

        validator = FileValidator()
        with patch('setup_environment.get_auth_headers', return_value=None):
            is_valid, method = validator.validate_remote_url('https://example.com/file.md')

        assert is_valid is True
        assert method == 'Range'
        mock_head.assert_called_once()
        mock_range.assert_called_once()

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_head')
    @patch.object(FileValidator, '_check_with_range')
    def test_validate_remote_url_both_fail(
        self,
        mock_range: MagicMock,
        mock_head: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test validation fails when both methods fail with non-auth codes."""
        mock_head.return_value = (False, 500)
        mock_range.return_value = (False, 500)

        validator = FileValidator()
        is_valid, method = validator.validate_remote_url('https://example.com/file.md')

        assert is_valid is False
        assert method == 'None'
        mock_head.assert_called_once()
        mock_range.assert_called_once()
        # Non-auth failure codes MUST NOT trigger auth resolution.
        mock_auth.assert_not_called()

    @patch('setup_environment.info')
    @patch('setup_environment.convert_gitlab_url_to_api')
    @patch('setup_environment.detect_repo_type')
    @patch.object(FileValidator, '_check_with_head')
    def test_validate_remote_url_gitlab_url_conversion(
        self,
        mock_head: MagicMock,
        mock_detect: MagicMock,
        mock_convert: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test that GitLab URLs are converted to API format for validation."""
        gitlab_web_url = 'https://gitlab.com/namespace/project/-/raw/main/file.md'
        gitlab_api_url = 'https://gitlab.com/api/v4/projects/namespace%2Fproject/repository/files/file.md/raw?ref=main'

        mock_detect.return_value = 'gitlab'
        mock_convert.return_value = gitlab_api_url
        mock_head.return_value = (True, 200)

        validator = FileValidator()
        with patch('setup_environment.get_auth_headers', return_value=None):
            is_valid, method = validator.validate_remote_url(gitlab_web_url)

        assert is_valid is True
        assert method == 'HEAD'
        mock_detect.assert_called_once_with(gitlab_web_url)
        mock_convert.assert_called_once_with(gitlab_web_url)
        mock_info.assert_called_once_with(f'Using API URL for validation: {gitlab_api_url}')

    def test_validate_local_path_exists(self) -> None:
        """Test local file validation when file exists."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'content')
            temp_path = f.name

        try:
            validator = FileValidator()
            result = validator.validate_local_path(temp_path)
            assert result == (True, 'Local')
        finally:
            Path(temp_path).unlink()

    def test_validate_local_path_not_exists(self) -> None:
        """Test local file validation when file doesn't exist."""
        validator = FileValidator()
        result = validator.validate_local_path('/nonexistent/path/file.md')
        assert result == (False, 'Local')

    def test_validate_local_path_is_directory(self) -> None:
        """Test local file validation when path is a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = FileValidator()
            result = validator.validate_local_path(tmpdir)
            assert result == (False, 'Local')

    def test_validate_chooses_remote_for_is_remote_true(self) -> None:
        """Test validate() uses validate_remote_url when is_remote=True."""
        with patch.object(FileValidator, 'validate_remote_url', return_value=(True, 'HEAD')) as mock:
            validator = FileValidator()
            result = validator.validate('https://example.com/file.md', is_remote=True)

            mock.assert_called_once_with('https://example.com/file.md')
            assert result == (True, 'HEAD')

    def test_validate_chooses_local_for_is_remote_false(self) -> None:
        """Test validate() uses validate_local_path when is_remote=False."""
        with patch.object(FileValidator, 'validate_local_path', return_value=(True, 'Local')) as mock:
            validator = FileValidator()
            result = validator.validate('/local/file.md', is_remote=False)

            mock.assert_called_once_with('/local/file.md')
            assert result == (True, 'Local')

    def test_results_accumulation(self) -> None:
        """Test that results are properly accumulated."""
        validator = FileValidator()
        validator.add_result('agent', 'agent.md', True, 'HEAD')
        validator.add_result('hook', 'hook.py', False, 'None')

        assert len(validator.results) == 2
        assert validator.results[0] == ('agent', 'agent.md', True, 'HEAD')
        assert validator.results[1] == ('hook', 'hook.py', False, 'None')

    def test_clear_results(self) -> None:
        """Test clearing accumulated results."""
        validator = FileValidator()
        validator.add_result('agent', 'agent.md', True, 'HEAD')
        validator.clear_results()

        assert len(validator.results) == 0

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_public_url_succeeds_without_calling_get_auth_headers(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Public URL returning 200 unauth must NOT trigger auth resolution.

        Verifies the lazy-auth contract: successful unauthenticated probes
        bypass get_auth_headers entirely. The auth_cache receives a None
        sentinel (public-origin marker) for downstream consumers.
        """

        mock_head.return_value = (True, 200)
        mock_range.return_value = (True, 200)  # Would also succeed, but HEAD returns first.

        cache = AuthHeaderCache()
        validator = FileValidator(auth_cache=cache)
        result = validator.validate_remote_url('https://example.com/public/file.md')

        assert result == (True, 'HEAD')
        # Auth MUST NOT be called for a public URL.
        mock_auth.assert_not_called()
        # Cache MUST contain the None sentinel for the public origin.
        is_cached, cached_headers = cache.get_cached_headers('https://example.com/public/file.md')
        assert is_cached is True
        assert cached_headers is None
        mock_range.assert_not_called()

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_404_triggers_auth_escalation(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Unauth probe returning 404 must trigger auth resolution exactly once."""

        resolved = {'Authorization': 'Bearer resolved-token'}
        mock_auth.return_value = resolved
        # Initial unauth: HEAD=404, Range=404. After resolution: HEAD=200.
        mock_head.side_effect = [(False, 404), (True, 200)]
        mock_range.return_value = (False, 404)

        cache = AuthHeaderCache(auth_param='test-token')
        validator = FileValidator(auth_param='test-token', auth_cache=cache)
        result = validator.validate_remote_url('https://github.com/org/repo/file.md')

        assert result == (True, 'HEAD')
        # get_auth_headers called exactly once via resolve_and_cache.
        mock_auth.assert_called_once_with('https://github.com/org/repo/file.md', 'test-token')
        # Cache now contains the resolved headers for the origin.
        is_cached, cached_headers = cache.get_cached_headers(
            'https://github.com/org/repo/file.md',
        )
        assert is_cached is True
        assert cached_headers == resolved

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_401_triggers_auth_escalation(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Unauth probe returning 401 must trigger auth resolution."""
        mock_auth.return_value = {'Authorization': 'Bearer token'}
        mock_head.side_effect = [(False, 401), (True, 200)]
        mock_range.return_value = (False, 401)

        validator = FileValidator(auth_param='token')
        result = validator.validate_remote_url('https://github.com/org/repo/file.md')

        assert result == (True, 'HEAD')
        mock_auth.assert_called_once()

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_403_triggers_auth_escalation(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Unauth probe returning 403 must trigger auth resolution."""
        mock_auth.return_value = {'Authorization': 'Bearer token'}
        mock_head.side_effect = [(False, 403), (True, 200)]
        mock_range.return_value = (False, 403)

        validator = FileValidator(auth_param='token')
        result = validator.validate_remote_url('https://github.com/org/repo/file.md')

        assert result == (True, 'HEAD')
        mock_auth.assert_called_once()

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_500_does_not_prompt(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """HTTP 5xx failures must NOT trigger auth resolution (no spurious prompts).

        Non-authentication failures such as 500 Internal Server Error are
        transient network conditions, not authentication problems. The lazy-auth
        contract escalates to authentication ONLY on 401/403/404.
        """
        mock_head.return_value = (False, 500)
        mock_range.return_value = (False, 500)

        validator = FileValidator(auth_param='token')
        result = validator.validate_remote_url('https://github.com/org/repo/file.md')

        assert result == (False, 'None')
        mock_auth.assert_not_called()

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_ssl_failure_does_not_prompt(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """SSL/DNS/URL errors (http_code=None) must NOT trigger auth resolution."""
        mock_head.return_value = (False, None)
        mock_range.return_value = (False, None)

        validator = FileValidator(auth_param='token')
        result = validator.validate_remote_url('https://nonexistent.example.com/file.md')

        assert result == (False, 'None')
        mock_auth.assert_not_called()

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_parallel_validation_does_not_double_prompt(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Two threads validating URLs from same origin must resolve auth only once.

        Verifies that AuthHeaderCache.resolve_and_cache double-checked locking
        serializes authentication resolution across parallel validation threads,
        preventing duplicate prompts observed in the regression.
        """
        mock_auth.return_value = {'Authorization': 'Bearer shared-token'}
        # Both threads see HEAD=404 first, then 200 after auth.
        mock_head.side_effect = lambda _url, headers: (
            (True, 200) if headers else (False, 404)
        )
        mock_range.side_effect = lambda _url, headers: (
            (True, 206) if headers else (False, 404)
        )

        cache = AuthHeaderCache(auth_param='shared-token')
        validator = FileValidator(auth_param='shared-token', auth_cache=cache)

        results: list[tuple[bool, str]] = []
        results_lock = threading.Lock()

        def worker(url: str) -> None:
            result = validator.validate_remote_url(url)
            with results_lock:
                results.append(result)

        urls = [
            'https://github.com/org/repo/file1.md',
            'https://github.com/org/repo/file2.md',
        ]
        threads = [threading.Thread(target=worker, args=(u,)) for u in urls]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 2
        for r in results:
            assert r[0] is True
        # Auth MUST be resolved exactly ONCE via double-checked locking.
        mock_auth.assert_called_once()

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_auth_cache_empty_result_does_not_retry(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """When resolve_and_cache returns {}, validation must terminate without retry.

        AuthHeaderCache.resolve_and_cache returns {} (empty dict, not None) when
        no credentials are available from any source. Treat this as terminal --
        the retry probe must NOT be attempted.
        """

        mock_auth.return_value = {}  # No credentials available from any source.
        mock_head.return_value = (False, 404)
        mock_range.return_value = (False, 404)

        cache = AuthHeaderCache(auth_param=None)
        validator = FileValidator(auth_cache=cache)
        result = validator.validate_remote_url('https://github.com/org/repo/file.md')

        assert result == (False, 'None')
        # Initial unauth probes: HEAD + Range (2 probes total, no retry).
        assert mock_head.call_count == 1
        assert mock_range.call_count == 1
        mock_auth.assert_called_once()

    @patch('setup_environment._github_repo_is_public', return_value=True)
    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_404_on_public_github_repo_does_not_prompt(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
        mock_repo_public: MagicMock,
    ) -> None:
        """404 on a confirmed-public GitHub repo must skip the auth prompt.

        When the repo is verified public via api.github.com/repos/{owner}/{repo},
        the original 404 indicates a genuine missing file and validation must
        return (False, 'None') without invoking get_auth_headers.
        """
        mock_head.return_value = (False, 404)
        mock_range.return_value = (False, 404)

        validator = FileValidator(auth_param='token')
        result = validator.validate_remote_url(
            'https://raw.githubusercontent.com/owner/repo/main/missing.md',
        )

        assert result == (False, 'None')
        mock_repo_public.assert_called_once_with('owner', 'repo')
        mock_auth.assert_not_called()

    @patch('setup_environment._github_repo_is_public', return_value=False)
    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_404_on_private_github_repo_prompts_as_normal(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
        mock_repo_public: MagicMock,
    ) -> None:
        """404 on a private/nonexistent GitHub repo must escalate to auth prompt.

        When _github_repo_is_public returns False (ambiguous: private or
        nonexistent), the validator must fall through to the normal auth
        escalation path (legitimate for the private case).
        """
        resolved = {'Authorization': 'Bearer t'}
        mock_auth.return_value = resolved
        mock_head.side_effect = [(False, 404), (True, 200)]
        mock_range.return_value = (False, 404)

        validator = FileValidator(auth_param='token')
        result = validator.validate_remote_url(
            'https://github.com/owner/repo/blob/main/private.md',
        )

        assert result == (True, 'HEAD')
        mock_repo_public.assert_called_once_with('owner', 'repo')
        mock_auth.assert_called_once()

    @patch('setup_environment._github_repo_is_public', return_value=None)
    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_404_on_unknown_repo_visibility_prompts_conservative(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_auth: MagicMock,
        mock_repo_public: MagicMock,
    ) -> None:
        """404 with rate-limited / network-failed visibility probe escalates.

        When _github_repo_is_public returns None (rate-limit, timeout, network
        error), the validator must conservatively escalate to the auth prompt
        (fail-safe behavior: auth prompt is legitimate when uncertain).
        """
        resolved = {'Authorization': 'Bearer t'}
        mock_auth.return_value = resolved
        mock_head.side_effect = [(False, 404), (True, 200)]
        mock_range.return_value = (False, 404)

        validator = FileValidator(auth_param='token')
        result = validator.validate_remote_url(
            'https://raw.githubusercontent.com/owner/repo/main/file.md',
        )

        assert result == (True, 'HEAD')
        mock_repo_public.assert_called_once_with('owner', 'repo')
        mock_auth.assert_called_once()


class TestLocalConfigWithRemoteFiles:
    """Tests for the specific bug: local config with remote files requiring auth.

    This is the core bug being fixed. These tests MUST pass after refactoring.
    """

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_local_config_with_github_files_uses_file_url_for_auth(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test that auth is generated for the FILE URL, not config source.

        BUG SCENARIO:
        - Config loaded from: C:/local/config.yaml
        - File to validate: https://raw.githubusercontent.com/user/repo/main/agent.md
        - Expected: get_auth_headers called with GitHub URL
        - Bug behavior: get_auth_headers not called (config_source is local)

        Auth escalation is triggered by the lazy-auth contract: unauth probe
        returns 404, which causes resolve_and_cache -> get_auth_headers to be
        invoked for the FILE URL.
        """
        mock_auth.return_value = {'Authorization': 'Bearer github_token'}
        mock_resolve.return_value = (
            'https://raw.githubusercontent.com/user/repo/main/agent.md',
            True,  # is_remote
        )
        # Force escalation: initial HEAD=404, then HEAD=200 after auth.
        mock_head.side_effect = [(False, 404), (True, 200)]
        mock_range.return_value = (False, 404)

        config = {'agents': ['agent.md']}

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            'C:/local/config.yaml',  # LOCAL config source
            auth_param='github_token',
        )

        assert all_valid is True
        # CRITICAL: Auth must be generated for the FILE URL
        mock_auth.assert_called()
        call_url = mock_auth.call_args[0][0]
        assert 'githubusercontent.com' in call_url
        assert 'C:' not in call_url  # Not the config source!

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_local_config_with_gitlab_files_uses_file_url_for_auth(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test GitLab files with local config source."""
        mock_auth.return_value = {'PRIVATE-TOKEN': 'gitlab_token'}
        mock_resolve.return_value = (
            'https://gitlab.com/user/repo/-/raw/main/agent.md',
            True,
        )
        # Force escalation: initial HEAD=404, then HEAD=200 after auth.
        mock_head.side_effect = [(False, 404), (True, 200)]
        mock_range.return_value = (False, 404)

        config = {'agents': ['agent.md']}

        with patch('setup_environment.detect_repo_type', return_value=None):
            all_valid, results = setup_environment.validate_all_config_files(
                config,
                '/local/config.yaml',  # LOCAL config source
                auth_param='gitlab_token',
            )

        assert all_valid is True
        mock_auth.assert_called()
        call_url = mock_auth.call_args[0][0]
        assert 'gitlab.com' in call_url


class TestMixedAuthScenarios:
    """Tests for files requiring different authentication (GitHub + GitLab)."""

    @patch('setup_environment.detect_repo_type')
    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_mixed_github_and_gitlab_files(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test that different files get appropriate auth headers.

        Two URLs from different origins both return 404 unauth, triggering
        escalation to get_auth_headers for each origin. The lazy-auth
        contract ensures per-URL auth resolution.
        """

        # Simulate different repo types
        def detect_side_effect(url: str) -> str | None:
            if 'github' in url:
                return 'github'
            if 'gitlab' in url:
                return 'gitlab'
            return None

        mock_detect.side_effect = detect_side_effect

        # Different auth headers per repo type
        def auth_side_effect(url: str, _param: str | None) -> dict[str, str]:
            if 'github' in url:
                return {'Authorization': 'Bearer github_token'}
            if 'gitlab' in url:
                return {'PRIVATE-TOKEN': 'gitlab_token'}
            return {}

        mock_auth.side_effect = auth_side_effect

        # Force escalation per URL: unauth 404, retry with auth succeeds.
        def head_side_effect(_url: str, headers: dict[str, str] | None) -> tuple[bool, int | None]:
            return (True, 200) if headers else (False, 404)

        def range_side_effect(_url: str, headers: dict[str, str] | None) -> tuple[bool, int | None]:
            return (True, 206) if headers else (False, 404)

        mock_head.side_effect = head_side_effect
        mock_range.side_effect = range_side_effect

        mock_resolve.side_effect = [
            ('https://raw.githubusercontent.com/user/repo/main/agent1.md', True),
            ('https://gitlab.com/user/repo/-/raw/main/agent2.md', True),
        ]

        config = {'agents': ['agent1.md', 'agent2.md']}

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            '/local/config.yaml',
            auth_param='token',
        )

        assert all_valid is True
        assert len(results) == 2
        # Verify get_auth_headers was called for each distinct origin.
        assert mock_auth.call_count == 2


class TestAuthEdgeCases:
    """Edge case tests for authentication scenarios."""

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_head')
    def test_public_file_with_auth_token_provided(
        self,
        mock_head: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test that public files work even when auth token is provided.

        With the lazy-auth contract, public URLs return 200 from the initial
        unauthenticated probe and never escalate to get_auth_headers, even
        when a token is provided by the user.
        """
        mock_auth.return_value = {'Authorization': 'Bearer token'}
        mock_resolve.return_value = ('https://example.com/public.md', True)
        mock_head.return_value = (True, 200)

        config = {'agents': ['public.md']}

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            '/local/config.yaml',
            auth_param='token',
        )

        assert all_valid is True

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_range')
    @patch.object(FileValidator, '_check_with_head')
    def test_private_file_without_auth_token(
        self,
        mock_head: MagicMock,
        mock_range: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test that private files fail gracefully without auth.

        Unauth probe returns 404; escalation attempts get_auth_headers which
        returns {} (no credentials available). Validation terminates with
        (False, 'None').
        """
        mock_auth.return_value = {}  # No auth headers available
        mock_resolve.return_value = ('https://example.com/private.md', True)
        mock_head.return_value = (False, 404)
        mock_range.return_value = (False, 404)

        config = {'agents': ['private.md']}

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            '/local/config.yaml',
            auth_param=None,
        )

        assert all_valid is False
        assert results[0][2] is False  # is_valid

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.urlopen')
    def test_network_failure_during_validation(
        self,
        mock_urlopen: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test handling of network failures."""
        mock_auth.return_value = {}
        mock_resolve.return_value = ('https://example.com/file.md', True)
        # urlopen raises exception, which is caught internally by _check_with_head
        mock_urlopen.side_effect = Exception('Connection refused')

        config = {'agents': ['file.md']}

        # Should not raise exception - network failures are handled gracefully
        all_valid, results = setup_environment.validate_all_config_files(
            config,
            '/local/config.yaml',
            auth_param=None,
        )

        assert all_valid is False


class TestValidateAllConfigFiles:
    """Test full configuration validation."""

    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_empty_config(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with empty configuration."""
        del mock_resolve  # Unused but required by decorator
        config: dict[str, list[str]] = {}

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert results == []
        mock_validate.assert_not_called()

    @patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE': '1'})
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_with_agents(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with agents."""
        config = {
            'agents': ['agent1.md', 'agent2.md'],
        }
        mock_resolve.side_effect = [
            ('https://example.com/agent1.md', True),  # Remote
            ('https://example.com/agent2.md', True),  # Remote
        ]
        mock_validate.side_effect = [
            (True, 'HEAD'),
            (True, 'Range'),
        ]

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is True
        assert len(results) == 2
        assert results[0] == ('agent', 'agent1.md', True, 'HEAD')
        assert results[1] == ('agent', 'agent2.md', True, 'Range')

    @patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE': '1'})
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_with_mixed_resources(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with multiple resource types (remote and local)."""
        config = {
            'agents': ['agent.md'],
            'slash-commands': ['cmd1.py', 'cmd2.py'],
            'command-defaults': {
                'system-prompt': 'prompt.md',
            },
            'hooks': {
                'files': ['hook1.py', 'hook2.py'],
            },
        }

        # Mock some as remote, some as local
        mock_resolve.side_effect = [
            ('https://example.com/agent.md', True),  # Remote
            ('/local/path/cmd1.py', False),  # Local
            ('https://example.com/cmd2.py', True),  # Remote
            ('https://example.com/prompt.md', True),  # Remote
            ('/local/path/hook1.py', False),  # Local
            ('https://example.com/hook2.py', True),  # Remote
        ]

        # Mock validation responses
        mock_validate.side_effect = [
            (True, 'HEAD'),  # agent.md (remote)
            (True, 'Local'),  # cmd1.py (local)
            (True, 'Range'),  # cmd2.py (remote)
            (True, 'HEAD'),  # prompt.md (remote)
            (True, 'Local'),  # hook1.py (local)
            (True, 'HEAD'),  # hook2.py (remote)
        ]

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            'https://example.com',
            'token',
        )

        assert all_valid is True
        assert len(results) == 6
        assert results[0] == ('agent', 'agent.md', True, 'HEAD')
        assert results[1] == ('slash_command', 'cmd1.py', True, 'Local')
        assert results[2] == ('slash_command', 'cmd2.py', True, 'Range')
        assert results[3] == ('system_prompt', 'prompt.md', True, 'HEAD')
        assert results[4] == ('hook', 'hook1.py', True, 'Local')
        assert results[5] == ('hook', 'hook2.py', True, 'HEAD')

    @patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE': '1'})
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_with_failures(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with some failures."""
        config = {
            'agents': ['good.md', 'bad.md'],
            'slash-commands': ['cmd.py'],
        }
        mock_resolve.side_effect = [
            ('https://example.com/good.md', True),  # Remote
            ('/local/bad.md', False),  # Local
            ('https://example.com/cmd.py', True),  # Remote
        ]

        mock_validate.side_effect = [
            (True, 'HEAD'),  # good.md
            (False, 'Local'),  # bad.md
            (True, 'Range'),  # cmd.py
        ]

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is False
        assert len(results) == 3
        assert results[0] == ('agent', 'good.md', True, 'HEAD')
        assert results[1] == ('agent', 'bad.md', False, 'Local')  # Local file not found
        assert results[2] == ('slash_command', 'cmd.py', True, 'Range')

    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_with_base_url(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with base URL configured."""
        config = {
            'base-url': 'https://cdn.example.com/files',
            'agents': ['agent.md'],
        }
        mock_resolve.return_value = ('https://cdn.example.com/files/agent.md', True)  # Remote
        mock_validate.return_value = (True, 'HEAD')

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert len(results) == 1
        # Verify base_url was passed to resolve_resource_path
        mock_resolve.assert_called_once_with('agent.md', 'local', 'https://cdn.example.com/files')

    @patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE': '1'})
    @patch('setup_environment.info')
    @patch('setup_environment.error')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_output_messages(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
        mock_error: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test validation output messages."""
        config = {
            'agents': ['good.md', 'bad.md'],
        }
        mock_resolve.side_effect = [
            ('https://example.com/good.md', True),  # Remote
            ('https://example.com/bad.md', True),  # Remote
        ]
        mock_validate.side_effect = [
            (True, 'HEAD'),
            (False, 'None'),
        ]

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is False
        # Check info messages
        mock_info.assert_any_call('Validating 2 files...')
        mock_info.assert_any_call('  [OK] agent: good.md (remote, validated via HEAD)')
        # Check error message
        mock_error.assert_called_once_with('  [FAIL] agent: bad.md (remote, not accessible)')

    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_empty_lists(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with empty lists in config."""
        del mock_resolve  # Unused but required by decorator
        config: dict[str, object] = {
            'agents': [],
            'slash-commands': None,
            'hooks': {
                'files': None,
            },
        }

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert results == []
        mock_validate.assert_not_called()


class TestMainFlowWithValidation:
    """Test the main flow with validation integrated."""

    @patch('setup_environment.sys.exit')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.load_config_from_source')
    @patch('argparse.ArgumentParser.parse_args')
    @patch('pathlib.Path.mkdir')
    @patch('setup_environment.write_manifest')
    @patch('setup_environment.cleanup_stale_marker')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_profile_config')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    def test_main_validation_failure_exits(
        self,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_profile: MagicMock,
        mock_mcp: MagicMock,
        mock_cleanup_stale: MagicMock,
        mock_write_manifest: MagicMock,
        mock_mkdir: MagicMock,
        mock_args: MagicMock,
        mock_load: MagicMock,
        mock_validate: MagicMock,
        mock_exit: MagicMock,
    ) -> None:
        """Test that main exits on validation failure."""
        # Prevent real filesystem writes (mocked sys.exit does not halt execution)
        del mock_mkdir, mock_write_manifest, mock_cleanup_stale
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_profile.return_value = True
        mock_launcher.return_value = (Path('/tmp/launcher.sh'), Path('/tmp/launcher.sh'))
        mock_register.return_value = True
        # Setup mocks
        mock_args.return_value = MagicMock(
            config='test',
            skip_install=True,
            auth=None,
            yes=True,
            dry_run=False,
            no_admin=False,
        )
        mock_load.return_value = (
            {
                'name': 'Test',
                'command-names': ['test-cmd'],
                'agents': ['bad.md'],
            },
            'https://example.com',
        )
        mock_validate.return_value = (
            False,
            [('agent', 'bad.md', False, 'None')],
        )

        # Run main
        with (
            patch('setup_environment.find_command', return_value='claude'),
            patch('setup_environment.error') as mock_error,
            patch('setup_environment.is_admin', return_value=True),
        ):
            setup_environment.main()

        # Verify exit was called with code 1 (may be called multiple times
        # since mocked sys.exit doesn't actually halt execution)
        mock_exit.assert_any_call(1)
        # Verify error messages
        mock_error.assert_any_call('Configuration validation failed!')
        mock_error.assert_any_call('The following files are not accessible:')
        mock_error.assert_any_call('  - agent: bad.md')

    @patch('setup_environment.process_resources')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.success')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.load_config_from_source')
    @patch('argparse.ArgumentParser.parse_args')
    @patch('setup_environment.write_manifest')
    @patch('setup_environment.cleanup_stale_marker')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_profile_config')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('pathlib.Path.mkdir')
    def test_main_validation_success_continues(
        self,
        mock_mkdir: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_profile: MagicMock,
        mock_mcp: MagicMock,
        mock_cleanup_stale: MagicMock,
        mock_write_manifest: MagicMock,
        mock_args: MagicMock,
        mock_load: MagicMock,
        mock_validate: MagicMock,
        mock_success: MagicMock,
        mock_install: MagicMock,
        mock_download: MagicMock,
    ) -> None:
        """Test that main continues when validation succeeds."""
        del mock_mkdir, mock_write_manifest, mock_cleanup_stale  # Prevent real filesystem writes
        # Setup mocks
        mock_args.return_value = MagicMock(
            config='test',
            skip_install=True,
            auth=None,
            yes=True,
            dry_run=False,
            no_admin=False,
        )
        mock_load.return_value = (
            {
                'name': 'Test',
                'command-names': ['test-cmd'],
                'agents': ['good.md'],
                'dependencies': [],
            },
            'https://example.com',
        )
        mock_validate.return_value = (
            True,
            [('agent', 'good.md', True, 'HEAD')],
        )
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_profile.return_value = True
        mock_launcher.return_value = (Path('/tmp/launcher.sh'), Path('/tmp/launcher.sh'))
        mock_register.return_value = True
        mock_download.return_value = True

        # Run main
        with (
            patch('setup_environment.find_command', return_value='claude'),
            patch('setup_environment.is_admin', return_value=True),
        ):
            setup_environment.main()

        # Verify validation success message
        mock_success.assert_any_call('All configuration files validated successfully!')
        # Verify we didn't exit early
        mock_install.assert_called()


class TestLocalPathValidation:
    """Test local path validation with real files."""

    @patch('setup_environment.info')
    @patch('setup_environment.error')
    def test_validate_local_files_with_real_paths(
        self,
        mock_error: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test validation with actual temporary files."""
        del mock_error, mock_info  # Unused but needed to suppress output
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir_path = Path(tmpdir_str)

            # Create some test files
            (tmpdir_path / 'exists.md').write_text('content')
            (tmpdir_path / 'subdir').mkdir()
            (tmpdir_path / 'subdir' / 'nested.md').write_text('nested')

            # Create config with various local paths
            config = {
                'agents': [
                    str(tmpdir_path / 'exists.md'),  # Absolute path that exists
                    str(tmpdir_path / 'missing.md'),  # Absolute path that doesn't exist
                ],
                'slash-commands': [
                    './subdir/nested.md',  # Relative path (will be resolved)
                ],
            }

            # Create a config file in tmpdir for relative path resolution
            config_file = tmpdir_path / 'config.yaml'
            config_file.write_text('dummy')

            # Run validation
            all_valid, results = setup_environment.validate_all_config_files(
                config,
                str(config_file),
            )

            # Verify results
            assert all_valid is False  # One file missing
            assert len(results) == 3

            # Check first agent (exists)
            assert results[0][0] == 'agent'
            assert results[0][1] == str(tmpdir_path / 'exists.md')
            assert results[0][2] is True
            assert results[0][3] == 'Local'

            # Check second agent (missing)
            assert results[1][0] == 'agent'
            assert results[1][1] == str(tmpdir_path / 'missing.md')
            assert results[1][2] is False
            assert results[1][3] == 'Local'

            # Check slash command (nested, exists)
            assert results[2][0] == 'slash_command'
            assert results[2][1] == './subdir/nested.md'
            assert results[2][2] is True
            assert results[2][3] == 'Local'

    def test_resolve_resource_path_local_variations(self) -> None:
        """Test resolve_resource_path with various local path types."""
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir_path = Path(tmpdir_str)
            config_file = tmpdir_path / 'config.yaml'
            config_file.write_text('dummy')

            # Test absolute path
            abs_path = str(tmpdir_path / 'file.md')
            resolved, is_remote = setup_environment.resolve_resource_path(
                abs_path,
                str(config_file),
            )
            assert resolved == str(Path(abs_path).resolve())
            assert is_remote is False

            # Test relative path with ./
            resolved, is_remote = setup_environment.resolve_resource_path(
                './file.md',
                str(config_file),
            )
            assert resolved == str((tmpdir_path / 'file.md').resolve())
            assert is_remote is False

            # Test parent relative path
            resolved, is_remote = setup_environment.resolve_resource_path(
                '../file.md',
                str(config_file),
            )
            assert resolved == str((tmpdir_path.parent / 'file.md').resolve())
            assert is_remote is False

            # Test simple relative path
            resolved, is_remote = setup_environment.resolve_resource_path(
                'file.md',
                str(config_file),
            )
            assert resolved == str((tmpdir_path / 'file.md').resolve())
            assert is_remote is False

            # Test home directory expansion
            with patch.dict(os.environ, {'HOME': str(tmpdir_path), 'USERPROFILE': str(tmpdir_path)}):
                resolved, is_remote = setup_environment.resolve_resource_path(
                    '~/file.md',
                    str(config_file),
                )
                assert resolved == str((tmpdir_path / 'file.md').resolve())
                assert is_remote is False

            # Test environment variable expansion (platform-specific)
            import platform

            if platform.system() == 'Windows':
                # Test Windows environment variable expansion
                with patch.dict(os.environ, {'USERPROFILE': str(tmpdir_path)}):
                    resolved, is_remote = setup_environment.resolve_resource_path(
                        '%USERPROFILE%\\file.md',
                        str(config_file),
                    )
                    assert resolved == str((tmpdir_path / 'file.md').resolve())
                    assert is_remote is False
            else:
                # Test Unix environment variable expansion
                with patch.dict(os.environ, {'HOME': str(tmpdir_path)}):
                    resolved, is_remote = setup_environment.resolve_resource_path(
                        '$HOME/file.md',
                        str(config_file),
                    )
                    assert resolved == str((tmpdir_path / 'file.md').resolve())
                    assert is_remote is False


class TestExtractGithubOwnerRepo:
    """Tests for the _extract_github_owner_repo URL parsing helper."""

    def test_extract_from_raw_url(self) -> None:
        """raw.githubusercontent.com URL: extract from path[0:2]."""
        result = setup_environment._extract_github_owner_repo(
            'https://raw.githubusercontent.com/owner/repo/main/file.md',
        )
        assert result == ('owner', 'repo')

    def test_extract_from_api_url(self) -> None:
        """api.github.com Contents API URL: extract path[1:3] after 'repos'."""
        result = setup_environment._extract_github_owner_repo(
            'https://api.github.com/repos/owner/repo/contents/file.md?ref=main',
        )
        assert result == ('owner', 'repo')

    def test_extract_from_web_url(self) -> None:
        """github.com web URL (with tree/blob subpath): extract path[0:2]."""
        result = setup_environment._extract_github_owner_repo(
            'https://github.com/owner/repo/tree/main',
        )
        assert result == ('owner', 'repo')


class TestGithubRepoIsPublic:
    """Tests for the _github_repo_is_public visibility probe."""

    @patch('setup_environment.urlopen')
    def test_returns_true_on_200(self, mock_urlopen: MagicMock) -> None:
        """HTTP 200 means repo is confirmed public."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        assert setup_environment._github_repo_is_public('owner', 'repo') is True
        request = mock_urlopen.call_args[0][0]
        assert request.full_url == 'https://api.github.com/repos/owner/repo'

    @patch('setup_environment.urlopen')
    def test_returns_false_on_404(self, mock_urlopen: MagicMock) -> None:
        """HTTP 404 means repo is private or does not exist (ambiguous)."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://api.github.com/repos/owner/repo',
            404,
            'Not Found',
            {},
            None,
        )

        assert setup_environment._github_repo_is_public('owner', 'repo') is False

    @patch('setup_environment.urlopen')
    def test_returns_none_on_rate_limit(self, mock_urlopen: MagicMock) -> None:
        """HTTP 403 (rate-limit) returns None for conservative escalation."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://api.github.com/repos/owner/repo',
            403,
            'rate limit exceeded',
            {},
            None,
        )

        assert setup_environment._github_repo_is_public('owner', 'repo') is None

    @patch('setup_environment.urlopen')
    def test_returns_none_on_network_error(self, mock_urlopen: MagicMock) -> None:
        """URLError / TimeoutError / OSError return None for conservative escalation."""
        mock_urlopen.side_effect = urllib.error.URLError('connection refused')

        assert setup_environment._github_repo_is_public('owner', 'repo') is None
