"""Tests enforcing standalone script policy and code identity between scripts.

Verifies that install_claude.py and setup_environment.py are fully standalone
(no cross-imports) and that designated shared code elements remain identical.
"""

import ast
import re
import textwrap
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / 'scripts'
INSTALL_CLAUDE = SCRIPTS_DIR / 'install_claude.py'
SETUP_ENVIRONMENT = SCRIPTS_DIR / 'setup_environment.py'


def _read_source(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _extract_function_source(source: str, func_name: str) -> str:
    """Extract function body source using AST for reliable boundary detection."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            # Top-level function only (not nested)
            lines = source.splitlines()
            func_lines = lines[node.lineno - 1 : node.end_lineno]
            return textwrap.dedent('\n'.join(func_lines))
    msg = f'Function {func_name!r} not found'
    raise ValueError(msg)


def _extract_class_source(source: str, class_name: str) -> str:
    """Extract class body source using AST for reliable boundary detection."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            lines = source.splitlines()
            class_lines = lines[node.lineno - 1 : node.end_lineno]
            return textwrap.dedent('\n'.join(class_lines))
    msg = f'Class {class_name!r} not found'
    raise ValueError(msg)


class TestNoCrossImports:
    """Enforce that scripts never import from each other."""

    def test_install_claude_does_not_import_setup_environment(self) -> None:
        source = _read_source(INSTALL_CLAUDE)
        # Check for any form of import from setup_environment
        assert 'from setup_environment' not in source, (
            'install_claude.py imports from setup_environment -- violates standalone policy'
        )
        assert 'import setup_environment' not in source, (
            'install_claude.py imports setup_environment -- violates standalone policy'
        )

    def test_setup_environment_does_not_import_install_claude(self) -> None:
        source = _read_source(SETUP_ENVIRONMENT)
        # Use regex to find actual import statements (not comments or strings)
        import_pattern = re.compile(
            r'^\s*(?:from\s+install_claude\s+import|import\s+install_claude)',
            re.MULTILINE,
        )
        matches = import_pattern.findall(source)
        assert not matches, (
            f'setup_environment.py imports from install_claude -- violates standalone policy: {matches}'
        )


class TestFindCommandIdentity:
    """Enforce that find_command() is identical in both scripts."""

    def test_find_command_bodies_identical(self) -> None:
        ic_source = _read_source(INSTALL_CLAUDE)
        se_source = _read_source(SETUP_ENVIRONMENT)

        ic_func = _extract_function_source(ic_source, 'find_command')
        se_func = _extract_function_source(se_source, 'find_command')

        # Normalize whitespace for comparison
        ic_normalized = '\n'.join(line.rstrip() for line in ic_func.splitlines())
        se_normalized = '\n'.join(line.rstrip() for line in se_func.splitlines())

        assert ic_normalized == se_normalized, (
            'find_command() has diverged between install_claude.py and setup_environment.py. '
            'Both copies must remain identical.'
        )


class TestColorsClassIdentity:
    """Enforce that Colors class is identical in both scripts."""

    def test_colors_class_bodies_identical(self) -> None:
        ic_source = _read_source(INSTALL_CLAUDE)
        se_source = _read_source(SETUP_ENVIRONMENT)

        ic_class = _extract_class_source(ic_source, 'Colors')
        se_class = _extract_class_source(se_source, 'Colors')

        # Normalize whitespace for comparison
        ic_normalized = '\n'.join(line.rstrip() for line in ic_class.splitlines())
        se_normalized = '\n'.join(line.rstrip() for line in se_class.splitlines())

        assert ic_normalized == se_normalized, (
            'Colors class has diverged between install_claude.py and setup_environment.py. '
            'Both copies must remain identical.'
        )


class TestGetRealUserHomeIdentity:
    """Enforce that get_real_user_home() is identical in both scripts."""

    def test_get_real_user_home_identical(self) -> None:
        """get_real_user_home() must have identical body in both scripts."""
        ic_source = _read_source(INSTALL_CLAUDE)
        se_source = _read_source(SETUP_ENVIRONMENT)

        ic_func = _extract_function_source(ic_source, 'get_real_user_home')
        se_func = _extract_function_source(se_source, 'get_real_user_home')

        # Normalize whitespace for comparison
        ic_normalized = '\n'.join(line.rstrip() for line in ic_func.splitlines())
        se_normalized = '\n'.join(line.rstrip() for line in se_func.splitlines())

        assert ic_normalized == se_normalized, (
            'get_real_user_home() has diverged between install_claude.py '
            'and setup_environment.py. Both copies must remain identical.'
        )


class TestShellConfigFilesIdentity:
    """Enforce that shell config file lists are identical in both scripts."""

    def test_get_shell_config_files_structural_match(self) -> None:
        """Both scripts must produce the same 7 shell config files with
        identical conditional filtering logic."""
        ic_source = _read_source(INSTALL_CLAUDE)
        se_source = _read_source(SETUP_ENVIRONMENT)

        ic_func = _extract_function_source(ic_source, '_get_shell_config_files')
        se_func = _extract_function_source(se_source, 'get_all_shell_config_files')

        # Both must contain the same set of 7 shell config file paths
        shell_files = [
            '.bashrc', '.bash_profile', '.profile',
            '.zshenv', '.zprofile', '.zshrc',
            'config.fish',
        ]
        for filename in shell_files:
            assert filename in ic_func, (
                f'{filename!r} missing from _get_shell_config_files() in install_claude.py'
            )
            assert filename in se_func, (
                f'{filename!r} missing from get_all_shell_config_files() in setup_environment.py'
            )

        # Both must use get_real_user_home() for home directory
        assert 'get_real_user_home()' in ic_func, (
            '_get_shell_config_files() must use get_real_user_home()'
        )
        assert 'get_real_user_home()' in se_func, (
            'get_all_shell_config_files() must use get_real_user_home()'
        )

        # Both must have Linux conditional zsh check
        assert "shutil.which('zsh')" in ic_func, (
            '_get_shell_config_files() missing Linux zsh conditional check'
        )
        assert "shutil.which('zsh')" in se_func, (
            'get_all_shell_config_files() missing Linux zsh conditional check'
        )

        # Both must have fish conditional check (cross-platform)
        assert "shutil.which('fish')" in ic_func, (
            '_get_shell_config_files() missing fish conditional check'
        )
        assert "shutil.which('fish')" in se_func, (
            'get_all_shell_config_files() missing fish conditional check'
        )


class TestFishConfigDetectionIdentity:
    """Enforce that Fish config detection uses the same pattern in both scripts."""

    def test_fish_detection_pattern_identical(self) -> None:
        """Both scripts must detect Fish config files using the same string check."""
        ic_source = _read_source(INSTALL_CLAUDE)
        se_source = _read_source(SETUP_ENVIRONMENT)

        ic_func = _extract_function_source(ic_source, '_is_fish_config')
        se_func_export = _extract_function_source(se_source, '_get_export_line')

        # install_claude.py uses _is_fish_config with 'fish' in str(config_file)
        assert "'fish' in str(" in ic_func, (
            '_is_fish_config() must use "fish" in str() pattern'
        )
        # setup_environment.py uses the same pattern inline
        assert "'fish' in str(" in se_func_export, (
            '_get_export_line() must use "fish" in str() pattern'
        )


class TestMarkerBlockConstantsIdentity:
    """Enforce that marker block constants are identical in both scripts."""

    def test_marker_start_constants_identical(self) -> None:
        """Marker block START string values must be identical across both scripts."""
        ic_source = _read_source(INSTALL_CLAUDE)
        se_source = _read_source(SETUP_ENVIRONMENT)

        ic_start = re.search(
            r"SHELL_CONFIG_MARKER_START\s*=\s*['\"](.+?)['\"]", ic_source,
        )
        se_start = re.search(
            r"ENV_VAR_MARKER_START\s*=\s*['\"](.+?)['\"]", se_source,
        )

        assert ic_start is not None, 'install_claude.py must define SHELL_CONFIG_MARKER_START'
        assert se_start is not None, 'setup_environment.py must define ENV_VAR_MARKER_START'
        assert ic_start.group(1) == se_start.group(1), (
            f'Marker START diverged: install_claude={ic_start.group(1)!r} '
            f'vs setup_environment={se_start.group(1)!r}'
        )

    def test_marker_end_constants_identical(self) -> None:
        """Marker block END string values must be identical across both scripts."""
        ic_source = _read_source(INSTALL_CLAUDE)
        se_source = _read_source(SETUP_ENVIRONMENT)

        ic_end = re.search(
            r"SHELL_CONFIG_MARKER_END\s*=\s*['\"](.+?)['\"]", ic_source,
        )
        se_end = re.search(
            r"ENV_VAR_MARKER_END\s*=\s*['\"](.+?)['\"]", se_source,
        )

        assert ic_end is not None, 'install_claude.py must define SHELL_CONFIG_MARKER_END'
        assert se_end is not None, 'setup_environment.py must define ENV_VAR_MARKER_END'
        assert ic_end.group(1) == se_end.group(1), (
            f'Marker END diverged: install_claude={ic_end.group(1)!r} '
            f'vs setup_environment={se_end.group(1)!r}'
        )
