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

    def test_install_claude_does_not_import_setup_environment(self):
        source = _read_source(INSTALL_CLAUDE)
        # Check for any form of import from setup_environment
        assert 'from setup_environment' not in source, (
            'install_claude.py imports from setup_environment -- violates standalone policy'
        )
        assert 'import setup_environment' not in source, (
            'install_claude.py imports setup_environment -- violates standalone policy'
        )

    def test_setup_environment_does_not_import_install_claude(self):
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

    def test_find_command_bodies_identical(self):
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

    def test_colors_class_bodies_identical(self):
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
