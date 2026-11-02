"""
Tests for the PyPI packaging configuration in pyproject.toml.

The wheel maps scripts/ into the cc_toolbox package in place, so these
assertions pin the exact file set, the path rewrite, the console entry point,
and the pyyaml + questionary + truststore runtime dependency closure, which
the PEP 723 block of setup_environment.py and the dev group declare as well.
"""

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPOSITORY_ROOT = Path(__file__).parent.parent
PYPROJECT = REPOSITORY_ROOT / 'pyproject.toml'
SETUP_SCRIPT = REPOSITORY_ROOT / 'scripts' / 'setup_environment.py'

# The metadata block of PEP 723 (inline script metadata), as the
# specification's reference implementation matches it.
INLINE_METADATA_BLOCK = re.compile(
    r'(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$',
)

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


def script_metadata(path: Path) -> dict:
    """Parse the `script` metadata block of a file the way PEP 723 specifies.

    Args:
        path: The script to read.

    Returns:
        The TOML content of the file's single `script` block.
    """
    blocks = [
        match for match in INLINE_METADATA_BLOCK.finditer(path.read_text(encoding='utf-8'))
        if match.group('type') == 'script'
    ]
    assert len(blocks) == 1, f'{path.name} must carry exactly one `# /// script` block'
    content = ''.join(
        line[2:] if line.startswith('# ') else line[1:]
        for line in blocks[0].group('content').splitlines(keepends=True)
    )
    return tomllib.loads(content)


def requirements_by_name(declarations: list[str]) -> dict[str, Requirement]:
    """Map each declared requirement to its normalized project name.

    Args:
        declarations: Requirement strings as a dependency list holds them.

    Returns:
        The parsed requirements keyed by their canonical names.
    """
    parsed = [Requirement(declaration) for declaration in declarations]
    return {canonicalize_name(requirement.name): requirement for requirement in parsed}


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
        assert sources == {'scripts': 'cc_toolbox'}


class TestProjectMetadata:
    """Pin the entry point and the runtime dependency closure."""

    def test_console_script_points_at_cli_main(self, pyproject: dict) -> None:
        assert pyproject['project']['scripts']['cc-toolbox'] == 'cc_toolbox.cli:main'

    def test_runtime_dependencies_exclude_pydantic(self, pyproject: dict) -> None:
        dependencies = pyproject['project']['dependencies']
        assert not any('pydantic' in dep for dep in dependencies), (
            'pydantic is a dev-only dependency (scripts/models and its tests); '
            'the published wheel needs only pyyaml, questionary and truststore'
        )

    def test_runtime_dependency_closure(self, pyproject: dict) -> None:
        names = sorted(requirements_by_name(pyproject['project']['dependencies']))
        assert names == ['pyyaml', 'questionary', 'truststore'], (
            'The runtime closure is exactly pyyaml (config parsing), '
            'questionary (interactive component picker; the numbered fallback '
            'covers environments where it cannot run) and truststore (HTTPS '
            "verification against the operating system's trust store)"
        )

    def test_requires_python_has_no_upper_bound(self, pyproject: dict) -> None:
        assert pyproject['project']['requires-python'] == '>=3.12'


class TestRuntimeDependencyDeclarations:
    """Pin the three declarations of the runtime dependencies to one another.

    The bootstrap wrappers run setup_environment.py with `uv run --no-project`,
    which installs only the dependencies of its PEP 723 block; the wheel
    installs [project].dependencies; `uv run pytest` provisions the dev group.
    A dependency dropped or loosened in one of them goes unnoticed on that
    path alone, so every declaration must name the same requirements.
    """

    def test_script_block_declares_the_wheel_dependencies(self, pyproject: dict) -> None:
        declared = requirements_by_name(script_metadata(SETUP_SCRIPT)['dependencies'])
        assert declared == requirements_by_name(pyproject['project']['dependencies']), (
            'The PEP 723 block of setup_environment.py must declare exactly '
            'the requirements of [project].dependencies'
        )

    def test_dev_group_declares_the_wheel_dependencies(self, pyproject: dict) -> None:
        dev_group = requirements_by_name(pyproject['dependency-groups']['dev'])
        runtime = requirements_by_name(pyproject['project']['dependencies'])
        assert {name: dev_group.get(name) for name in runtime} == runtime, (
            '[dependency-groups].dev must declare every requirement of '
            '[project].dependencies with the same version specifier'
        )

    def test_wheel_dependencies_carry_a_minimum_version(self, pyproject: dict) -> None:
        runtime = requirements_by_name(pyproject['project']['dependencies'])
        unbounded = sorted(
            name for name, requirement in runtime.items()
            if not any(specifier.operator == '>=' for specifier in requirement.specifier)
        )
        assert unbounded == [], f'Runtime dependencies without a minimum version: {unbounded}'
