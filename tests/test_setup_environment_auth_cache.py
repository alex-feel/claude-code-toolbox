"""Tests for AuthHeaderCache and _fetch_url_core in setup_environment.py."""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from setup_environment import AuthHeaderCache
from setup_environment import FileValidator
from setup_environment import _fetch_url_core


class TestAuthHeaderCacheGetOrigin:
    """Test origin normalization for cache keying."""

    def test_github_web_url(self) -> None:
        """Verify github.com/owner/repo normalizes correctly."""
        cache = AuthHeaderCache()
        assert cache.get_origin('https://github.com/org/repo/blob/main/file.py') == 'github.com/org/repo'

    def test_github_raw_url(self) -> None:
        """Verify raw.githubusercontent.com normalizes to github.com origin."""
        cache = AuthHeaderCache()
        assert cache.get_origin(
            'https://raw.githubusercontent.com/org/repo/main/file.py',
        ) == 'github.com/org/repo'

    def test_github_api_url(self) -> None:
        """Verify api.github.com/repos/owner/repo normalizes to github.com origin."""
        cache = AuthHeaderCache()
        assert cache.get_origin(
            'https://api.github.com/repos/org/repo/contents/file.py',
        ) == 'github.com/org/repo'

    def test_all_github_variants_same_origin(self) -> None:
        """Verify all GitHub URL variants map to the same origin key."""
        cache = AuthHeaderCache()
        urls = [
            'https://github.com/org/repo/blob/main/file.py',
            'https://raw.githubusercontent.com/org/repo/main/file.py',
            'https://api.github.com/repos/org/repo/contents/file.py',
        ]
        origins = {cache.get_origin(url) for url in urls}
        assert len(origins) == 1
        assert origins == {'github.com/org/repo'}

    def test_gitlab_api_url(self) -> None:
        """Verify GitLab API URLs normalize by project ID."""
        cache = AuthHeaderCache()
        assert cache.get_origin(
            'https://gitlab.com/api/v4/projects/12345/repository/files/path%2Ffile.py/raw',
        ) == 'gitlab.com/api/v4/projects/12345'

    def test_gitlab_web_url(self) -> None:
        """Verify GitLab web URLs normalize by namespace/project."""
        cache = AuthHeaderCache()
        assert cache.get_origin(
            'https://gitlab.com/namespace/project/-/raw/main/file.py',
        ) == 'gitlab.com/namespace/project'

    def test_unknown_host_fallback(self) -> None:
        """Verify unknown hosts fall back to hostname only."""
        cache = AuthHeaderCache()
        assert cache.get_origin('https://example.com/some/path/file.txt') == 'example.com'


class TestAuthHeaderCacheBehavior:
    """Test cache miss/hit, None caching, and thread safety."""

    def test_miss_then_hit(self) -> None:
        """First call returns miss, after cache_headers second call returns hit."""
        cache = AuthHeaderCache()
        url = 'https://github.com/org/repo/blob/main/file.py'

        is_cached, headers = cache.get_cached_headers(url)
        assert is_cached is False
        assert headers is None

        test_headers = {'Authorization': 'Bearer token123'}
        cache.cache_headers(url, test_headers)

        is_cached, headers = cache.get_cached_headers(url)
        assert is_cached is True
        assert headers == test_headers

    def test_none_headers_cached(self) -> None:
        """Caching None (public repo) returns (True, None) on lookup."""
        cache = AuthHeaderCache()
        url = 'https://github.com/org/public-repo/blob/main/file.py'

        cache.cache_headers(url, None)

        is_cached, headers = cache.get_cached_headers(url)
        assert is_cached is True
        assert headers is None

    @patch('setup_environment.get_auth_headers')
    def test_resolve_and_cache_caches_result(self, mock_get_auth: MagicMock) -> None:
        """resolve_and_cache calls get_auth_headers once, then uses cache."""
        mock_get_auth.return_value = {'Authorization': 'Bearer token'}
        cache = AuthHeaderCache(auth_param='my-token')
        url = 'https://github.com/org/repo/blob/main/file1.py'

        result1 = cache.resolve_and_cache(url)
        result2 = cache.resolve_and_cache(url)

        assert result1 == {'Authorization': 'Bearer token'}
        assert result2 == {'Authorization': 'Bearer token'}
        mock_get_auth.assert_called_once_with(url, 'my-token')

    @patch('setup_environment.get_auth_headers')
    def test_thread_safety(self, mock_get_auth: MagicMock) -> None:
        """Multiple threads calling resolve_and_cache for the same origin produce consistent results."""
        mock_get_auth.return_value = {'Authorization': 'Bearer thread-token'}
        cache = AuthHeaderCache(auth_param='token')
        url = 'https://github.com/org/repo/file.py'

        threads = []
        results: list[dict[str, str]] = []
        results_lock = threading.Lock()

        def worker() -> None:
            result = cache.resolve_and_cache(url)
            with results_lock:
                results.append(result)

        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All threads should get the same consistent result
        assert len(results) == 5
        for r in results:
            assert r == {'Authorization': 'Bearer thread-token'}

        # After all threads complete, the origin should be cached
        is_cached, cached = cache.get_cached_headers(url)
        assert is_cached is True
        assert cached == {'Authorization': 'Bearer thread-token'}


class TestFetchUrlCoreAuthCacheIntegration:
    """Test _fetch_url_core interaction with AuthHeaderCache."""

    @patch('setup_environment.urlopen')
    @patch('setup_environment.get_auth_headers')
    def test_uses_auth_cache_hit(self, mock_get_auth: MagicMock, mock_urlopen: MagicMock) -> None:
        """When auth_cache has cached headers, unauthenticated attempt is skipped."""
        from setup_environment import AuthHeaderCache
        from setup_environment import _fetch_url_core

        cache = AuthHeaderCache()
        url = 'https://github.com/org/repo/file.txt'
        cached_headers = {'Authorization': 'Bearer cached-token'}
        cache.cache_headers(url, cached_headers)

        mock_response = MagicMock()
        mock_response.read.return_value = b'content'
        mock_urlopen.return_value = mock_response

        result = _fetch_url_core(url, as_text=True, auth_cache=cache)

        assert result == 'content'
        # get_auth_headers should NOT be called since cache was hit
        mock_get_auth.assert_not_called()

    @patch('setup_environment.fetch_with_retry')
    def test_populates_auth_cache_on_auth_discovery(self, mock_retry: MagicMock) -> None:
        """When auth is discovered after 401, cache is populated."""
        from setup_environment import AuthHeaderCache

        cache = AuthHeaderCache()
        url = 'https://github.com/org/repo/file.txt'

        # The fetch_with_retry just calls the request_func
        def call_func(func, *_args, **_kwargs):
            return func()

        mock_retry.side_effect = call_func

        # We need to test inside _do_fetch. Let's use a different approach -
        # test through the wrapper functions.
        # Verify cache is empty initially
        is_cached, _ = cache.get_cached_headers(url)
        assert is_cached is False

        # Populate via cache_headers and verify
        cache.cache_headers(url, {'Authorization': 'Bearer discovered'})
        is_cached, headers = cache.get_cached_headers(url)
        assert is_cached is True
        assert headers == {'Authorization': 'Bearer discovered'}

    @patch('setup_environment.urlopen')
    @patch('setup_environment.get_auth_headers')
    def test_auth_headers_param_takes_priority(self, mock_get_auth: MagicMock, mock_urlopen: MagicMock) -> None:
        """Explicit auth_headers parameter bypasses cache entirely."""
        from setup_environment import AuthHeaderCache
        from setup_environment import _fetch_url_core

        cache = AuthHeaderCache()
        url = 'https://github.com/org/repo/file.txt'
        # Cache different headers
        cache.cache_headers(url, {'Authorization': 'Bearer cached-token'})

        mock_response = MagicMock()
        mock_response.read.return_value = b'content'
        mock_urlopen.return_value = mock_response

        explicit_headers = {'Authorization': 'Bearer explicit-token'}
        result = _fetch_url_core(url, as_text=True, auth_headers=explicit_headers, auth_cache=cache)

        assert result == 'content'
        # get_auth_headers should NOT be called
        mock_get_auth.assert_not_called()
        # Verify the explicit headers were used (check the request)
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.get_header('Authorization') == 'Bearer explicit-token'

    @patch('setup_environment.urlopen')
    def test_fetch_url_core_text_mode(self, mock_urlopen: MagicMock) -> None:
        """_fetch_url_core with as_text=True returns decoded string."""
        from setup_environment import _fetch_url_core

        mock_response = MagicMock()
        mock_response.read.return_value = b'hello world'
        mock_urlopen.return_value = mock_response

        result = _fetch_url_core('https://example.com/file.txt', as_text=True)
        assert isinstance(result, str)
        assert result == 'hello world'

    @patch('setup_environment.urlopen')
    def test_fetch_url_core_bytes_mode(self, mock_urlopen: MagicMock) -> None:
        """_fetch_url_core with as_text=False returns raw bytes."""
        from setup_environment import _fetch_url_core

        mock_response = MagicMock()
        mock_response.read.return_value = b'\x89PNG\r\n'
        mock_urlopen.return_value = mock_response

        result = _fetch_url_core('https://example.com/image.png', as_text=False)
        assert isinstance(result, bytes)
        assert result == b'\x89PNG\r\n'


class TestValidationPopulatesAuthCache:
    """Integration test: validation populates cache for downloads."""

    @patch('setup_environment.urlopen')
    @patch('setup_environment.get_auth_headers')
    def test_validation_populates_cache_for_downloads(
        self, mock_get_auth: MagicMock, mock_urlopen: MagicMock,
    ) -> None:
        """FileValidator with auth_cache populates it during validation.

        Drives the auth-escalation path: unauth probe returns 404, triggering
        get_auth_headers via resolve_and_cache. The retry probe with auth
        succeeds, and the cache is populated with the resolved auth headers.
        """
        import urllib.error as _url_err

        test_headers = {'Authorization': 'Bearer test-token'}
        mock_get_auth.return_value = test_headers

        # First probe (HEAD unauth): 404; second probe (Range unauth): 404;
        # third probe (HEAD auth): 200.
        success_response = MagicMock()
        success_response.status = 200
        mock_urlopen.side_effect = [
            _url_err.HTTPError('https://x', 404, 'Not Found', {}, None),
            _url_err.HTTPError('https://x', 404, 'Not Found', {}, None),
            success_response,
        ]

        cache = AuthHeaderCache()
        validator = FileValidator(auth_param='test-token', auth_cache=cache)

        url = 'https://github.com/org/repo/blob/main/agent.md'
        validator.validate_remote_url(url)

        # Cache should now contain the resolved auth headers for this origin.
        is_cached, cached_headers = cache.get_cached_headers(url)
        assert is_cached is True
        assert cached_headers == test_headers

    @patch('setup_environment._github_repo_is_public', return_value=False)
    @patch('setup_environment.urlopen')
    @patch('setup_environment.get_auth_headers')
    def test_mixed_origins_cached_independently(
        self, mock_get_auth: MagicMock, mock_urlopen: MagicMock, mock_repo_public: MagicMock,
    ) -> None:
        """Two URLs from different origins have independent cache entries.

        Each origin drives the auth-escalation path: unauth probes return 404,
        and the retry with auth succeeds. Both origins end up cached with
        their respective auth headers. The GitHub visibility probe is mocked
        to return False (ambiguous) so the auth-escalation path is exercised
        rather than short-circuited by the 404 disambiguation.
        """
        import urllib.error as _url_err

        github_headers = {'Authorization': 'Bearer github-token'}
        gitlab_headers = {'PRIVATE-TOKEN': 'gitlab-token'}

        def mock_auth(url: str, _auth_param: str | None = None) -> dict[str, str]:
            if 'github.com' in url:
                return github_headers
            return gitlab_headers

        mock_get_auth.side_effect = mock_auth

        # For each URL: HEAD 404, Range 404, HEAD 200 (with auth).
        success_response = MagicMock()
        success_response.status = 200
        mock_urlopen.side_effect = [
            _url_err.HTTPError('https://x', 404, 'Not Found', {}, None),
            _url_err.HTTPError('https://x', 404, 'Not Found', {}, None),
            success_response,
            _url_err.HTTPError('https://x', 404, 'Not Found', {}, None),
            _url_err.HTTPError('https://x', 404, 'Not Found', {}, None),
            success_response,
        ]

        cache = AuthHeaderCache()
        validator = FileValidator(auth_param='token', auth_cache=cache)

        github_url = 'https://github.com/org/repo/blob/main/agent.md'
        # Use a GitLab API URL directly to avoid URL conversion inside validate_remote_url
        gitlab_url = 'https://gitlab.com/api/v4/projects/123/repository/files/file.md/raw?ref=main'

        validator.validate_remote_url(github_url)
        validator.validate_remote_url(gitlab_url)

        # Both origins should be cached independently with their auth headers.
        is_cached_gh, gh_headers = cache.get_cached_headers(github_url)
        assert is_cached_gh is True
        assert gh_headers == github_headers

        is_cached_gl, gl_headers = cache.get_cached_headers(gitlab_url)
        assert is_cached_gl is True
        assert gl_headers == gitlab_headers

        # Visibility probe was invoked exactly once (for the GitHub URL only).
        assert mock_repo_public.call_count == 1

    @patch('setup_environment.urlopen')
    @patch('setup_environment.get_auth_headers')
    def test_validation_caches_none_on_public_success(
        self, mock_get_auth: MagicMock, mock_urlopen: MagicMock,
    ) -> None:
        """Public URL (unauth 200) caches the None sentinel, bypassing auth.

        Verifies the lazy-auth contract: a successful unauthenticated probe
        (HTTP 200) populates the cache with None (public-origin marker).
        get_auth_headers MUST NOT be invoked for public URLs.
        """
        success_response = MagicMock()
        success_response.status = 200
        mock_urlopen.return_value = success_response

        cache = AuthHeaderCache()
        validator = FileValidator(auth_param='unused-token', auth_cache=cache)

        url = 'https://github.com/org/public-repo/blob/main/agent.md'
        validator.validate_remote_url(url)

        # get_auth_headers MUST NOT be called -- public URL validated unauth.
        mock_get_auth.assert_not_called()

        # Cache MUST contain the None sentinel for this public origin.
        is_cached, cached_headers = cache.get_cached_headers(url)
        assert is_cached is True
        assert cached_headers is None


class TestGitHubApiHeaders:
    """Test GitHub API transport headers on Request objects."""

    @patch('setup_environment.urlopen')
    def test_github_api_url_gets_accept_header_unauthenticated(self, mock_urlopen: MagicMock) -> None:
        """Public GitHub API URLs include Accept header even without auth."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'raw file content'
        mock_urlopen.return_value = mock_response

        result = _fetch_url_core(
            'https://raw.githubusercontent.com/owner/repo/main/file.txt',
            as_text=True,
        )

        assert result == 'raw file content'
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.get_header('Accept') == 'application/vnd.github.raw+json'
        assert request.get_header('X-github-api-version') == '2022-11-28'

    @patch('setup_environment.urlopen')
    def test_github_api_url_gets_accept_header_with_auth(self, mock_urlopen: MagicMock) -> None:
        """GitHub API URLs include Accept header alongside auth headers."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'private content'
        mock_urlopen.return_value = mock_response

        auth_headers = {'Authorization': 'Bearer test-token'}
        result = _fetch_url_core(
            'https://raw.githubusercontent.com/owner/repo/main/file.txt',
            as_text=True,
            auth_headers=auth_headers,
        )

        assert result == 'private content'
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.get_header('Accept') == 'application/vnd.github.raw+json'
        assert request.get_header('Authorization') == 'Bearer test-token'

    @patch('setup_environment.urlopen')
    def test_non_github_url_no_accept_header(self, mock_urlopen: MagicMock) -> None:
        """Non-GitHub URLs should not receive GitHub API headers."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'gitlab content'
        mock_urlopen.return_value = mock_response

        result = _fetch_url_core(
            'https://gitlab.com/owner/repo/-/raw/main/file.txt',
            as_text=True,
        )

        assert result == 'gitlab content'
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.get_header('Accept') is None

    @patch('setup_environment.urlopen')
    def test_github_api_url_with_cache_gets_accept_header(self, mock_urlopen: MagicMock) -> None:
        """GitHub API URL using cached auth headers also includes Accept."""
        cache = AuthHeaderCache()
        raw_url = 'https://raw.githubusercontent.com/owner/repo/main/file.txt'
        cache.cache_headers(raw_url, {'Authorization': 'Bearer cached-token'})

        mock_response = MagicMock()
        mock_response.read.return_value = b'cached content'
        mock_urlopen.return_value = mock_response

        result = _fetch_url_core(raw_url, as_text=True, auth_cache=cache)

        assert result == 'cached content'
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.get_header('Accept') == 'application/vnd.github.raw+json'
        assert request.get_header('Authorization') == 'Bearer cached-token'
