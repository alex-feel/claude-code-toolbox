"""Tests for skills installation functionality in setup_environment.py.

This module tests the skills processing feature (Option F - Base URL + explicit file list)
which allows users to install Claude Code skills with the following YAML format:

skills:
  - name: pdf-skill
    base: https://raw.githubusercontent.com/.../skills/library/pdf-skill
    files:
      - SKILL.md
      - FORMS.md
      - scripts/fill_form.py

  - name: local-skill
    base: ./skills/local-skill
    files:
      - SKILL.md
      - helper.py
"""

import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment


class TestValidateSkillFiles:
    """Test skill file validation."""

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.validate_file_availability')
    def test_validate_skill_files_remote_success(
        self,
        mock_validate: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test validating remote skill files successfully."""
        mock_auth.return_value = {}
        mock_validate.return_value = (True, 'HEAD')

        skill_config: dict[str, Any] = {
            'name': 'test-skill',
            'base': 'https://example.com/skills/test-skill',
            'files': ['SKILL.md', 'helper.py'],
        }

        all_valid, results = setup_environment.validate_skill_files(
            skill_config,
            'https://example.com/config.yaml',
        )

        assert all_valid is True
        assert len(results) == 2
        assert results[0] == ('SKILL.md', True, 'HEAD')
        assert results[1] == ('helper.py', True, 'HEAD')
        assert mock_validate.call_count == 2

    @patch('setup_environment.resolve_resource_path')
    def test_validate_skill_files_local_success(
        self,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validating local skill files successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            skill_base = tmpdir_path / 'test-skill'
            skill_base.mkdir()

            # Create test files
            (skill_base / 'SKILL.md').write_text('# Test Skill')
            (skill_base / 'helper.py').write_text('# Helper')

            mock_resolve.return_value = (str(skill_base), False)

            skill_config: dict[str, Any] = {
                'name': 'test-skill',
                'base': str(skill_base),
                'files': ['SKILL.md', 'helper.py'],
            }

            all_valid, results = setup_environment.validate_skill_files(
                skill_config,
                str(tmpdir_path / 'config.yaml'),
            )

            assert all_valid is True
            assert len(results) == 2
            assert results[0] == ('SKILL.md', True, 'Local')
            assert results[1] == ('helper.py', True, 'Local')

    @patch('setup_environment.error')
    def test_validate_skill_files_missing_skill_md(
        self,
        mock_error: MagicMock,
    ) -> None:
        """Test validation fails when SKILL.md is missing from files list."""
        skill_config: dict[str, Any] = {
            'name': 'test-skill',
            'base': './skills/test-skill',
            'files': ['helper.py', 'utils.py'],  # Missing SKILL.md
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            skill_base = tmpdir_path / 'skills' / 'test-skill'
            skill_base.mkdir(parents=True)
            (skill_base / 'helper.py').write_text('# Helper')
            (skill_base / 'utils.py').write_text('# Utils')

            config_file = tmpdir_path / 'config.yaml'
            config_file.write_text('dummy')

            all_valid, _results = setup_environment.validate_skill_files(
                skill_config,
                str(config_file),
            )

            assert all_valid is False
            mock_error.assert_called_once_with(
                "Skill 'test-skill': SKILL.md is required but not in files list",
            )

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.validate_file_availability')
    def test_validate_skill_files_inaccessible_file(
        self,
        mock_validate: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test validation detects inaccessible files."""
        mock_auth.return_value = {}
        # First file accessible, second not
        mock_validate.side_effect = [(True, 'HEAD'), (False, 'None')]

        skill_config: dict[str, Any] = {
            'name': 'test-skill',
            'base': 'https://example.com/skills/test-skill',
            'files': ['SKILL.md', 'missing.py'],
        }

        all_valid, results = setup_environment.validate_skill_files(
            skill_config,
            'https://example.com/config.yaml',
        )

        assert all_valid is False
        assert len(results) == 2
        assert results[0] == ('SKILL.md', True, 'HEAD')
        assert results[1] == ('missing.py', False, 'None')


class TestProcessSkill:
    """Test single skill processing."""

    @patch('setup_environment.fetch_url_with_auth')
    @patch('setup_environment.info')
    @patch('setup_environment.success')
    def test_process_skill_remote_success(
        self,
        mock_success: MagicMock,
        mock_info: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test downloading remote skill with multiple files."""
        del mock_info, mock_success  # Unused but needed for patching
        mock_fetch.side_effect = ['# Test Skill', '# Helper code']

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skill_config: dict[str, Any] = {
                'name': 'test-skill',
                'base': 'https://example.com/skills/test-skill',
                'files': ['SKILL.md', 'helper.py'],
            }

            result = setup_environment.process_skill(
                skill_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is True
            skill_dir = skills_dir / 'test-skill'
            assert skill_dir.exists()
            assert (skill_dir / 'SKILL.md').exists()
            assert (skill_dir / 'helper.py').exists()
            assert (skill_dir / 'SKILL.md').read_text() == '# Test Skill'
            assert mock_fetch.call_count == 2

    @patch('setup_environment.info')
    @patch('setup_environment.success')
    def test_process_skill_local_success(
        self,
        mock_success: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test copying local skill files."""
        del mock_info, mock_success  # Unused but needed for patching

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create source skill directory
            source_skill = tmpdir_path / 'source' / 'test-skill'
            source_skill.mkdir(parents=True)
            (source_skill / 'SKILL.md').write_text('# Local Skill')
            (source_skill / 'helper.py').write_text('def helper(): pass')

            # Create destination skills directory
            skills_dir = tmpdir_path / 'dest' / 'skills'
            skills_dir.mkdir(parents=True)

            # Create config file for path resolution
            config_file = tmpdir_path / 'config.yaml'
            config_file.write_text('dummy')

            skill_config: dict[str, Any] = {
                'name': 'test-skill',
                'base': str(source_skill),
                'files': ['SKILL.md', 'helper.py'],
            }

            result = setup_environment.process_skill(
                skill_config,
                skills_dir,
                str(config_file),
            )

            assert result is True
            dest_skill = skills_dir / 'test-skill'
            assert dest_skill.exists()
            assert (dest_skill / 'SKILL.md').read_text() == '# Local Skill'
            assert (dest_skill / 'helper.py').read_text() == 'def helper(): pass'

    @patch('setup_environment.error')
    def test_process_skill_missing_name(
        self,
        mock_error: MagicMock,
    ) -> None:
        """Test error handling when skill name is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skill_config: dict[str, Any] = {
                'base': 'https://example.com/skills/test-skill',
                'files': ['SKILL.md'],
            }

            result = setup_environment.process_skill(
                skill_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is False
            mock_error.assert_called_with("Skill configuration missing 'name' field")

    @patch('setup_environment.error')
    def test_process_skill_empty_files(
        self,
        mock_error: MagicMock,
    ) -> None:
        """Test error handling when files list is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skill_config: dict[str, Any] = {
                'name': 'test-skill',
                'base': 'https://example.com/skills/test-skill',
                'files': [],
            }

            result = setup_environment.process_skill(
                skill_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is False
            mock_error.assert_called_with("Skill 'test-skill': No files specified")

    @patch('setup_environment.fetch_url_with_auth')
    @patch('setup_environment.info')
    @patch('setup_environment.success')
    def test_process_skill_preserves_directory_structure(
        self,
        mock_success: MagicMock,
        mock_info: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test that nested paths like scripts/fill_form.py create subdirectories."""
        del mock_info, mock_success  # Unused but needed for patching
        mock_fetch.side_effect = ['# Skill', '# Form filler', '# Helper']

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skill_config: dict[str, Any] = {
                'name': 'pdf-skill',
                'base': 'https://example.com/skills/pdf-skill',
                'files': ['SKILL.md', 'scripts/fill_form.py', 'scripts/utils/helper.py'],
            }

            result = setup_environment.process_skill(
                skill_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is True
            skill_dir = skills_dir / 'pdf-skill'
            assert (skill_dir / 'SKILL.md').exists()
            assert (skill_dir / 'scripts' / 'fill_form.py').exists()
            assert (skill_dir / 'scripts' / 'utils' / 'helper.py').exists()

    @patch('setup_environment.fetch_url_with_auth')
    @patch('setup_environment.info')
    @patch('setup_environment.success')
    @patch('setup_environment.error')
    def test_process_skill_download_failure(
        self,
        mock_error: MagicMock,
        mock_success: MagicMock,
        mock_info: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test handling of download failures."""
        del mock_info, mock_success  # Unused but needed for patching
        mock_fetch.side_effect = Exception('Network error')

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skill_config: dict[str, Any] = {
                'name': 'test-skill',
                'base': 'https://example.com/skills/test-skill',
                'files': ['SKILL.md'],
            }

            result = setup_environment.process_skill(
                skill_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is False
            mock_error.assert_any_call('  Failed to download SKILL.md: Network error')

    @patch('setup_environment.fetch_url_with_auth')
    @patch('setup_environment.info')
    @patch('setup_environment.success')
    @patch('setup_environment.error')
    def test_process_skill_missing_skill_md_after_download(
        self,
        mock_error: MagicMock,
        mock_success: MagicMock,
        mock_info: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test warning when SKILL.md not found after installation."""
        del mock_info, mock_success  # Unused but needed for patching
        # Simulate SKILL.md download failure but helper.py success
        mock_fetch.side_effect = [Exception('Not found'), '# Helper']

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skill_config: dict[str, Any] = {
                'name': 'test-skill',
                'base': 'https://example.com/skills/test-skill',
                'files': ['SKILL.md', 'helper.py'],
            }

            result = setup_environment.process_skill(
                skill_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is False
            mock_error.assert_any_call(
                "Skill 'test-skill': SKILL.md was not installed - skill may be invalid",
            )


class TestProcessSkills:
    """Test multiple skills processing."""

    @patch('setup_environment.info')
    def test_process_skills_empty_config(
        self,
        mock_info: MagicMock,
    ) -> None:
        """Test with no skills configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            result = setup_environment.process_skills(
                [],
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is True
            mock_info.assert_called_with('No skills configured')

    @patch('setup_environment.process_skill')
    @patch('setup_environment.info')
    def test_process_skills_multiple_skills(
        self,
        mock_info: MagicMock,
        mock_process_skill: MagicMock,
    ) -> None:
        """Test installing multiple skills."""
        mock_process_skill.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skills_config: list[dict[str, Any]] = [
                {
                    'name': 'skill1',
                    'base': 'https://example.com/skills/skill1',
                    'files': ['SKILL.md'],
                },
                {
                    'name': 'skill2',
                    'base': 'https://example.com/skills/skill2',
                    'files': ['SKILL.md', 'helper.py'],
                },
            ]

            result = setup_environment.process_skills(
                skills_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is True
            assert mock_process_skill.call_count == 2
            mock_info.assert_any_call('Processing 2 skill(s)...')

    @patch('setup_environment.process_skill')
    @patch('setup_environment.info')
    def test_process_skills_partial_failure(
        self,
        mock_info: MagicMock,
        mock_process_skill: MagicMock,
    ) -> None:
        """Test when some skills fail to install."""
        del mock_info  # Unused but needed for patching
        # First skill succeeds, second fails
        mock_process_skill.side_effect = [True, False]

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skills_config: list[dict[str, Any]] = [
                {
                    'name': 'skill1',
                    'base': 'https://example.com/skills/skill1',
                    'files': ['SKILL.md'],
                },
                {
                    'name': 'skill2',
                    'base': 'https://example.com/skills/skill2',
                    'files': ['SKILL.md'],
                },
            ]

            result = setup_environment.process_skills(
                skills_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is False
            assert mock_process_skill.call_count == 2


class TestSkillsValidationIntegration:
    """Test skills validation in validate_all_config_files."""

    @patch('setup_environment.info')
    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_with_skills(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test that skills are included in comprehensive validation."""
        del mock_info, mock_resolve  # Unused but needed for patching
        mock_auth.return_value = None
        mock_validate.return_value = (True, 'HEAD')

        config: dict[str, Any] = {
            'skills': [
                {
                    'name': 'test-skill',
                    'base': 'https://example.com/skills/test-skill',
                    'files': ['SKILL.md', 'helper.py'],
                },
            ],
        }

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            'https://example.com/config.yaml',
        )

        assert all_valid is True
        # Should have 2 skill files validated
        skill_results = [r for r in results if r[0] == 'skill']
        assert len(skill_results) == 2
        assert skill_results[0][1] == 'test-skill/SKILL.md'
        assert skill_results[1][1] == 'test-skill/helper.py'

    @patch('setup_environment.info')
    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_skills_and_agents(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test validation with both skills and agents."""
        del mock_info  # Unused but needed for patching
        mock_auth.return_value = None
        mock_resolve.return_value = ('https://example.com/agents/agent.md', True)
        mock_validate.return_value = (True, 'HEAD')

        config: dict[str, Any] = {
            'agents': ['agent.md'],
            'skills': [
                {
                    'name': 'test-skill',
                    'base': 'https://example.com/skills/test-skill',
                    'files': ['SKILL.md'],
                },
            ],
        }

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            'https://example.com/config.yaml',
        )

        assert all_valid is True
        # Should have 1 agent + 1 skill file = 2 total
        assert len(results) == 2
        agent_results = [r for r in results if r[0] == 'agent']
        skill_results = [r for r in results if r[0] == 'skill']
        assert len(agent_results) == 1
        assert len(skill_results) == 1

    @patch('setup_environment.info')
    @patch('setup_environment.error')
    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_skill_validation_failure(
        self,
        mock_validate: MagicMock,
        mock_auth: MagicMock,
        mock_error: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test that skill validation failures are properly reported."""
        del mock_info  # Unused but needed for patching
        mock_auth.return_value = None
        mock_validate.return_value = (False, 'None')

        config: dict[str, Any] = {
            'skills': [
                {
                    'name': 'bad-skill',
                    'base': 'https://example.com/skills/bad-skill',
                    'files': ['SKILL.md'],
                },
            ],
        }

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            'https://example.com/config.yaml',
        )

        assert all_valid is False
        skill_results = [r for r in results if r[0] == 'skill']
        assert len(skill_results) == 1
        assert skill_results[0][2] is False  # is_valid
        mock_error.assert_any_call(
            '  [FAIL] skill: bad-skill/SKILL.md (remote, not accessible)',
        )


class TestSkillsLocalPathValidation:
    """Test skills validation with local paths."""

    @patch('setup_environment.info')
    @patch('setup_environment.error')
    @patch('setup_environment.get_auth_headers')
    def test_validate_skills_local_files_exist(
        self,
        mock_auth: MagicMock,
        mock_error: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test validation with local skill files that exist."""
        del mock_error, mock_info  # Unused but needed for patching
        mock_auth.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create skill directory with files
            skill_dir = tmpdir_path / 'skills' / 'local-skill'
            skill_dir.mkdir(parents=True)
            (skill_dir / 'SKILL.md').write_text('# Local Skill')
            (skill_dir / 'helper.py').write_text('# Helper')

            # Create config file
            config_file = tmpdir_path / 'config.yaml'
            config_file.write_text('dummy')

            config: dict[str, Any] = {
                'skills': [
                    {
                        'name': 'local-skill',
                        'base': str(skill_dir),
                        'files': ['SKILL.md', 'helper.py'],
                    },
                ],
            }

            all_valid, results = setup_environment.validate_all_config_files(
                config,
                str(config_file),
            )

            assert all_valid is True
            skill_results = [r for r in results if r[0] == 'skill']
            assert len(skill_results) == 2
            assert all(r[2] is True for r in skill_results)  # All valid
            assert all(r[3] == 'Local' for r in skill_results)  # All local

    @patch('setup_environment.info')
    @patch('setup_environment.error')
    @patch('setup_environment.get_auth_headers')
    def test_validate_skills_local_files_missing(
        self,
        mock_auth: MagicMock,
        mock_error: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test validation with local skill files that don't exist."""
        del mock_info, mock_error  # Unused but needed for patching
        mock_auth.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create skill directory but NOT the files
            skill_dir = tmpdir_path / 'skills' / 'local-skill'
            skill_dir.mkdir(parents=True)

            # Create config file
            config_file = tmpdir_path / 'config.yaml'
            config_file.write_text('dummy')

            config: dict[str, Any] = {
                'skills': [
                    {
                        'name': 'local-skill',
                        'base': str(skill_dir),
                        'files': ['SKILL.md', 'helper.py'],
                    },
                ],
            }

            all_valid, results = setup_environment.validate_all_config_files(
                config,
                str(config_file),
            )

            assert all_valid is False
            skill_results = [r for r in results if r[0] == 'skill']
            assert len(skill_results) == 2
            assert all(r[2] is False for r in skill_results)  # All invalid


class TestSkillsWithAuthentication:
    """Test skills processing with authentication."""

    @patch('setup_environment.fetch_url_with_auth')
    @patch('setup_environment.info')
    @patch('setup_environment.success')
    def test_process_skill_with_auth_param(
        self,
        mock_success: MagicMock,
        mock_info: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test that auth parameter is passed to fetch function."""
        del mock_info, mock_success  # Unused but needed for patching
        mock_fetch.return_value = '# Test Skill'

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skill_config: dict[str, Any] = {
                'name': 'private-skill',
                'base': 'https://gitlab.com/private/skills/private-skill',
                'files': ['SKILL.md'],
            }

            result = setup_environment.process_skill(
                skill_config,
                skills_dir,
                'https://gitlab.com/config.yaml',
                auth_param='PRIVATE-TOKEN:my-token',
            )

            assert result is True
            # Verify auth_param was passed to fetch_url_with_auth
            mock_fetch.assert_called_once()
            call_kwargs = mock_fetch.call_args[1]
            assert call_kwargs.get('auth_param') == 'PRIVATE-TOKEN:my-token'
