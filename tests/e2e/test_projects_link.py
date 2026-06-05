"""E2E tests for the optional link-projects-dir feature.

Verifies link_projects_directory() correctly links an isolated profile's
projects/ directory to the base ~/.claude/projects/:
- Unix: a symlink (target_is_directory) resolving to the base.
- Windows: a directory junction (reparse point) -- detected via the
  reparse-point attribute bit, NOT Path.is_symlink() (junctions report
  is_symlink() == False while is_dir() == True).

Also covers idempotency, non-clobbering of real (non-link) directories,
empty-directory replacement, and the mklink /J fallback path.
"""

import os
import stat
import sys
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import link_projects_directory

# Windows reparse-point attribute bit. A junction or symlink carries this bit;
# a real directory does not. 0x400 == stat.FILE_ATTRIBUTE_REPARSE_POINT.
REPARSE_POINT_BIT = stat.FILE_ATTRIBUTE_REPARSE_POINT


def _artifact_base(e2e_isolated_home: dict[str, Path]) -> Path:
    """Create and return an isolated profile base dir (~/.claude/{cmd})."""
    claude_dir = e2e_isolated_home['claude_dir']
    artifact_base_dir = claude_dir / 'e2e-cmd'
    artifact_base_dir.mkdir(parents=True, exist_ok=True)
    return artifact_base_dir


class TestLinkProjectsDirectory:
    """Test link_projects_directory() across platforms and edge cases."""

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix symlink behavior')
    def test_unix_creates_symlink(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """On Unix, the link is a symlink resolving to the base projects dir."""
        home = e2e_isolated_home['home']
        artifact_base_dir = _artifact_base(e2e_isolated_home)
        base_projects = home / '.claude' / 'projects'
        link_path = artifact_base_dir / 'projects'

        result = link_projects_directory(artifact_base_dir)

        assert result is True
        assert base_projects.is_dir(), 'Base projects dir must be created'
        assert link_path.is_symlink(), 'Link must be a symlink on Unix'
        assert link_path.resolve() == base_projects.resolve(), (
            'Symlink must resolve to the base projects dir'
        )

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows junction behavior')
    def test_windows_creates_junction(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """On Windows, the link is a junction (reparse point), not a symlink."""
        home = e2e_isolated_home['home']
        artifact_base_dir = _artifact_base(e2e_isolated_home)
        base_projects = home / '.claude' / 'projects'
        link_path = artifact_base_dir / 'projects'

        result = link_projects_directory(artifact_base_dir)

        assert result is True
        assert base_projects.is_dir(), 'Base projects dir must be created'
        # Junction is a directory at the link path.
        assert link_path.is_dir(), 'Junction must present as a directory'
        # Regression guard: a junction reports is_symlink() == False.
        assert link_path.is_symlink() is False, (
            'Windows junction must NOT report is_symlink() == True'
        )
        # The reparse-point bit must be set on a junction.
        attrs = os.lstat(link_path).st_file_attributes
        assert attrs & REPARSE_POINT_BIT, (
            'Junction must carry the reparse-point attribute bit (0x400)'
        )
        # The junction must resolve to the base projects dir.
        assert link_path.resolve() == base_projects.resolve(), (
            'Junction must resolve to the base projects dir'
        )

    def test_idempotent_second_call_is_noop(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Calling the helper twice is a no-op the second time and stays correct."""
        home = e2e_isolated_home['home']
        artifact_base_dir = _artifact_base(e2e_isolated_home)
        base_projects = home / '.claude' / 'projects'
        link_path = artifact_base_dir / 'projects'

        first = link_projects_directory(artifact_base_dir)
        second = link_projects_directory(artifact_base_dir)

        assert first is True
        assert second is True
        # The link still resolves to the base projects dir after the second call.
        assert link_path.resolve() == base_projects.resolve()
        if sys.platform == 'win32':
            assert link_path.is_symlink() is False
            attrs = os.lstat(link_path).st_file_attributes
            assert attrs & REPARSE_POINT_BIT
        else:
            assert link_path.is_symlink()

    def test_non_clobber_real_non_empty_dir(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """A real non-empty projects/ dir is preserved (warn + skip), not replaced."""
        artifact_base_dir = _artifact_base(e2e_isolated_home)
        link_path = artifact_base_dir / 'projects'

        # Pre-create a REAL projects directory holding session history.
        link_path.mkdir(parents=True, exist_ok=True)
        sentinel = link_path / 'session-history.json'
        sentinel.write_text('{"existing": "data"}', encoding='utf-8')

        result = link_projects_directory(artifact_base_dir)

        # Benign skip returns True; the real dir and its contents survive.
        assert result is True
        assert link_path.is_dir()
        assert link_path.is_symlink() is False
        assert sentinel.exists(), 'Existing session history must be preserved'
        assert sentinel.read_text(encoding='utf-8') == '{"existing": "data"}'

    def test_empty_real_dir_replaced_with_link(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """A real EMPTY projects/ dir is replaced with the link."""
        home = e2e_isolated_home['home']
        artifact_base_dir = _artifact_base(e2e_isolated_home)
        base_projects = home / '.claude' / 'projects'
        link_path = artifact_base_dir / 'projects'

        # Pre-create an EMPTY real projects directory.
        link_path.mkdir(parents=True, exist_ok=True)

        result = link_projects_directory(artifact_base_dir)

        assert result is True
        assert link_path.resolve() == base_projects.resolve()
        if sys.platform == 'win32':
            assert link_path.is_symlink() is False
            attrs = os.lstat(link_path).st_file_attributes
            assert attrs & REPARSE_POINT_BIT
        else:
            assert link_path.is_symlink()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows mklink /J fallback')
    def test_windows_fallback_to_mklink(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When _winapi.CreateJunction raises, the helper falls back to mklink /J."""
        import _winapi

        home = e2e_isolated_home['home']
        artifact_base_dir = _artifact_base(e2e_isolated_home)
        base_projects = home / '.claude' / 'projects'
        link_path = artifact_base_dir / 'projects'

        def _raise_create_junction(_src: str, _dst: str) -> None:
            raise OSError('simulated CreateJunction failure')

        monkeypatch.setattr(_winapi, 'CreateJunction', _raise_create_junction)

        result = link_projects_directory(artifact_base_dir)

        # The mklink /J fallback must produce a working junction.
        assert result is True
        assert link_path.is_dir()
        assert link_path.is_symlink() is False
        attrs = os.lstat(link_path).st_file_attributes
        assert attrs & REPARSE_POINT_BIT
        assert link_path.resolve() == base_projects.resolve()

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix uses symlink, not junction')
    def test_unix_uses_symlink_not_junction(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """On Unix the helper calls Path.symlink_to and never touches a junction path."""
        artifact_base_dir = _artifact_base(e2e_isolated_home)
        link_path = artifact_base_dir / 'projects'

        calls: list[tuple[Path, Path]] = []
        original_symlink_to = Path.symlink_to

        def _tracking_symlink_to(
            self: Path,
            target: str | Path,
            target_is_directory: bool = False,
        ) -> None:
            calls.append((self, Path(target)))
            original_symlink_to(self, target, target_is_directory=target_is_directory)

        monkeypatch.setattr(Path, 'symlink_to', _tracking_symlink_to)

        result = link_projects_directory(artifact_base_dir)

        assert result is True
        assert calls, 'Path.symlink_to must be used on Unix'
        assert calls[0][0] == link_path

    def test_failure_is_non_fatal(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failure during linking returns False without raising (non-fatal)."""
        artifact_base_dir = _artifact_base(e2e_isolated_home)

        def _raise_get_home() -> Path:
            raise OSError('simulated home resolution failure')

        monkeypatch.setattr(setup_environment, 'get_real_user_home', _raise_get_home)

        result = link_projects_directory(artifact_base_dir)

        assert result is False
