"""
Tests for the PyPI packaging configuration in pyproject.toml.

The wheel maps scripts/ into the claude_code_toolbox package in place, so these
assertions pin the exact file set, the path rewrite, the console entry point,
and the pyyaml-only runtime dependency closure.
"""

import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).parent.parent / 'pyproject.toml'

WHEEL_FILES = [
    'scripts/__init__.py',
    'scripts/cli.py',
    'scripts/setup_environment.py',
    'scripts/install_claude.py',
]


@pytest.fixture(scope='module')
def pyproject() -> dict:
    """Parse pyproject.toml once for all assertions."""
    with PYPROJECT.open('rb') as f:
        return tomllib.load(f)


class TestBuildSystem:
    """Pin the build backend and the wheel remap configuration."""

    def test_build_backend_is_hatchling(self, pyproject: dict) -> None:
        assert pyproject['build-system']['build-backend'] == 'hatchling.build'

    def test_wheel_only_include_is_exactly_the_four_modules(self, pyproject: dict) -> None:
        only_include = pyproject['tool']['hatch']['build']['targets']['wheel']['only-include']
        assert sorted(only_include) == sorted(WHEEL_FILES)

    def test_wheel_excludes_models_package(self, pyproject: dict) -> None:
        only_include = pyproject['tool']['hatch']['build']['targets']['wheel']['only-include']
        assert not any(entry.startswith('scripts/models') for entry in only_include), (
            'scripts/models must stay out of the wheel so pydantic never enters the runtime closure'
        )

    def test_wheel_sources_remap_scripts_to_package_name(self, pyproject: dict) -> None:
        sources = pyproject['tool']['hatch']['build']['targets']['wheel']['sources']
        assert sources == {'scripts': 'claude_code_toolbox'}


class TestProjectMetadata:
    """Pin the entry point and the runtime dependency closure."""

    def test_console_script_points_at_cli_main(self, pyproject: dict) -> None:
        assert pyproject['project']['scripts']['claude-code-toolbox'] == 'claude_code_toolbox.cli:main'

    def test_runtime_dependencies_exclude_pydantic(self, pyproject: dict) -> None:
        dependencies = pyproject['project']['dependencies']
        assert not any('pydantic' in dep for dep in dependencies), (
            'pydantic is a dev-only dependency (scripts/models and its tests); the published wheel needs pyyaml alone'
        )

    def test_requires_python_has_no_upper_bound(self, pyproject: dict) -> None:
        assert pyproject['project']['requires-python'] == '>=3.12'
