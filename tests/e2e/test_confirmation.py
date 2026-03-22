"""E2E tests for the installation confirmation mechanism.

Tests verify that the confirmation gate properly blocks, allows,
and reports installation based on CLI flags and environment variables.
Uses isolated home directories and golden config for comprehensive validation.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

from scripts import setup_environment


class TestConfirmationBlocking:
    """Test that confirmation gate blocks or allows installation correctly."""

    def _make_plan_from_golden(
        self, golden_config: dict[str, Any],
    ) -> setup_environment.InstallationPlan:
        """Build an InstallationPlan from the golden config."""
        chain = [setup_environment.InheritanceChainEntry(
            source='golden_config.yaml',
            source_type='local',
            name=golden_config.get('name', 'E2E Test Environment'),
        )]
        args = MagicMock()
        args.skip_install = False
        return setup_environment.collect_installation_plan(
            config=golden_config,
            config_source='golden_config.yaml',
            config_name='golden',
            inheritance_chain=chain,
            args=args,
        )

    def test_no_flag_non_interactive_refuses(
        self, golden_config: dict[str, Any],
    ) -> None:
        """Non-interactive mode without --yes refuses installation (returns False)."""
        plan = self._make_plan_from_golden(golden_config)
        with (
            patch.object(setup_environment, 'display_installation_summary'),
            patch('sys.stdin') as mock_stdin,
            patch.object(setup_environment, '_dev_tty_available', return_value=False),
        ):
            mock_stdin.isatty.return_value = False
            result = setup_environment.confirm_installation(plan)
        assert result is False

    def test_yes_flag_proceeds(
        self, golden_config: dict[str, Any],
    ) -> None:
        """--yes flag auto-confirms (returns True)."""
        plan = self._make_plan_from_golden(golden_config)
        with patch.object(setup_environment, 'display_installation_summary'):
            result = setup_environment.confirm_installation(
                plan, auto_confirm=True, dry_run=False,
            )
        assert result is True

    def test_dry_run_exits_zero(
        self, golden_config: dict[str, Any],
    ) -> None:
        """--dry-run shows plan and returns False (caller exits 0)."""
        plan = self._make_plan_from_golden(golden_config)
        with patch.object(setup_environment, 'display_installation_summary'):
            result = setup_environment.confirm_installation(
                plan, auto_confirm=False, dry_run=True,
            )
        assert result is False

    def test_env_var_auto_confirms(
        self, golden_config: dict[str, Any],
    ) -> None:
        """CLAUDE_CONFIRM_INSTALL=1 auto-confirms via auto_confirm parameter."""
        plan = self._make_plan_from_golden(golden_config)
        # main() resolves env var to auto_confirm=True
        with patch.object(setup_environment, 'display_installation_summary'):
            result = setup_environment.confirm_installation(
                plan, auto_confirm=True, dry_run=False,
            )
        assert result is True

    def test_env_var_wrong_value_does_not_confirm(
        self, golden_config: dict[str, Any],
    ) -> None:
        """CLAUDE_CONFIRM_INSTALL=true does NOT auto-confirm (only '1' works).

        The env var check in main() uses ``os.environ.get('CLAUDE_CONFIRM_INSTALL') == '1'``,
        so values like 'true', 'yes', or empty strings do not trigger auto-confirm.
        When auto_confirm is False and no interactive terminal is available,
        confirm_installation returns False.
        """
        plan = self._make_plan_from_golden(golden_config)
        with (
            patch.object(setup_environment, 'display_installation_summary'),
            patch('sys.stdin') as mock_stdin,
            patch.object(setup_environment, '_dev_tty_available', return_value=False),
        ):
            mock_stdin.isatty.return_value = False
            # auto_confirm=False simulates env var value 'true' (not matching '1')
            result = setup_environment.confirm_installation(
                plan, auto_confirm=False, dry_run=False,
            )
        assert result is False


class TestConfirmationSummaryContent:
    """Test that installation summary displays correct content from golden config."""

    def _make_plan_from_golden(
        self, golden_config: dict[str, Any],
    ) -> setup_environment.InstallationPlan:
        """Build an InstallationPlan from the golden config."""
        chain = [setup_environment.InheritanceChainEntry(
            source='golden_config.yaml',
            source_type='local',
            name=golden_config.get('name', 'E2E Test Environment'),
        )]
        args = MagicMock()
        args.skip_install = False
        return setup_environment.collect_installation_plan(
            config=golden_config,
            config_source='golden_config.yaml',
            config_name='golden',
            inheritance_chain=chain,
            args=args,
        )

    def test_summary_shows_config_name(
        self, golden_config: dict[str, Any],
    ) -> None:
        """Environment name from golden config appears in summary."""
        plan = self._make_plan_from_golden(golden_config)
        buf = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buf)
        output = buf.getvalue()
        assert 'E2E Test Environment' in output

    def test_summary_shows_dependency_commands(
        self, golden_config: dict[str, Any],
    ) -> None:
        """Full dependency commands from golden config are visible."""
        plan = self._make_plan_from_golden(golden_config)
        buf = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buf)
        output = buf.getvalue()
        assert "echo 'common-dependency-installed'" in output

    def test_summary_shows_resource_counts(
        self, golden_config: dict[str, Any],
    ) -> None:
        """Resource counts in summary match golden config."""
        plan = self._make_plan_from_golden(golden_config)
        buf = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buf)
        output = buf.getvalue()
        # Golden config has 1 agent, 1 slash command, 5 MCP servers, etc.
        assert 'Agents: 1' in output
        assert 'Slash commands: 1' in output
        assert 'MCP servers: 5' in output

    def test_summary_flags_unknown_keys(
        self, golden_config: dict[str, Any],
    ) -> None:
        """Unknown keys are flagged with [?] markers in summary."""
        config = dict(golden_config)
        config['my-unknown-key'] = 'value'
        plan = self._make_plan_from_golden(config)
        buf = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buf)
        output = buf.getvalue()
        assert '[?]' in output
        assert 'my-unknown-key' in output

    def test_summary_flags_sensitive_paths(
        self, golden_config: dict[str, Any],
    ) -> None:
        """Sensitive paths are flagged with [!] markers in summary."""
        config = dict(golden_config)
        config['files-to-download'] = [
            {'source': 'key.pub', 'dest': '~/.ssh/authorized_keys'},
        ]
        plan = self._make_plan_from_golden(config)
        buf = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buf)
        output = buf.getvalue()
        assert '[!]' in output
        assert '~/.ssh/authorized_keys' in output
