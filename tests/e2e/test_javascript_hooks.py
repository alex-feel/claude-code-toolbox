"""E2E tests for JavaScript hook command generation.

These tests validate that JavaScript hooks (.js, .mjs, .cjs) are generated
with the correct 'node' prefix for cross-platform execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.setup_environment import create_additional_settings


class TestJavaScriptHooks:
    """Test JavaScript hook command generation in E2E context."""

    def test_js_hook_has_node_prefix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify .js hook commands have 'node' prefix."""
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create hooks directory
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        create_additional_settings(
            hooks=golden_config.get('hooks', {}),
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=None,
            permissions=None,
            env=None,
            include_co_authored_by=None,
            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=None,
        )

        settings_path = claude_dir / f'{cmd}-additional-settings.json'
        data = json.loads(settings_path.read_text())

        # Find .js hook and verify node prefix
        errors: list[str] = []
        hooks = data.get('hooks', {})

        for event_hooks in hooks.values():
            for hook_group in event_hooks:
                for hook in hook_group.get('hooks', []):
                    command = hook.get('command', '')
                    # Match .js but not .mjs or .cjs
                    is_js_file = '.js' in command and not any(
                        ext in command for ext in ['.mjs', '.cjs']
                    )
                    if is_js_file and not command.startswith('node '):
                        errors.append(f'.js hook missing node prefix: {command}')

        assert not errors, 'JavaScript hook validation failed:\n' + '\n'.join(errors)

    def test_mjs_hook_has_node_prefix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify .mjs ES module hook commands have 'node' prefix."""
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        create_additional_settings(
            hooks=golden_config.get('hooks', {}),
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=None,
            permissions=None,
            env=None,
            include_co_authored_by=None,
            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=None,
        )

        settings_path = claude_dir / f'{cmd}-additional-settings.json'
        data = json.loads(settings_path.read_text())

        errors: list[str] = []
        hooks = data.get('hooks', {})

        for event_hooks in hooks.values():
            for hook_group in event_hooks:
                for hook in hook_group.get('hooks', []):
                    command = hook.get('command', '')
                    if '.mjs' in command and not command.startswith('node '):
                        errors.append(f'.mjs hook missing node prefix: {command}')

        assert not errors, 'ES module hook validation failed:\n' + '\n'.join(errors)

    def test_cjs_hook_has_node_prefix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify .cjs CommonJS hook commands have 'node' prefix."""
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        create_additional_settings(
            hooks=golden_config.get('hooks', {}),
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=None,
            permissions=None,
            env=None,
            include_co_authored_by=None,
            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=None,
        )

        settings_path = claude_dir / f'{cmd}-additional-settings.json'
        data = json.loads(settings_path.read_text())

        errors: list[str] = []
        hooks = data.get('hooks', {})

        for event_hooks in hooks.values():
            for hook_group in event_hooks:
                for hook in hook_group.get('hooks', []):
                    command = hook.get('command', '')
                    if '.cjs' in command and not command.startswith('node '):
                        errors.append(f'.cjs hook missing node prefix: {command}')

        assert not errors, 'CommonJS hook validation failed:\n' + '\n'.join(errors)

    def test_js_hook_with_config_has_node_prefix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify JavaScript hooks with config files have correct format."""
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        create_additional_settings(
            hooks=golden_config.get('hooks', {}),
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=None,
            permissions=None,
            env=None,
            include_co_authored_by=None,
            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=None,
        )

        settings_path = claude_dir / f'{cmd}-additional-settings.json'
        data = json.loads(settings_path.read_text())

        errors: list[str] = []
        hooks = data.get('hooks', {})

        for event_hooks in hooks.values():
            for hook_group in event_hooks:
                for hook in hook_group.get('hooks', []):
                    command = hook.get('command', '')
                    # Check .mjs hook with config
                    if '.mjs' in command and 'e2e-js-hook-config.json' in command:
                        if not command.startswith('node '):
                            errors.append(
                                f'JS hook with config missing node prefix: {command}',
                            )
                        # Verify config path is appended after script path
                        parts = command.split()
                        if len(parts) < 3:
                            errors.append(
                                f'JS hook with config missing config argument: {command}',
                            )

        assert not errors, (
            'JavaScript hook with config validation failed:\n' + '\n'.join(errors)
        )

    def test_python_and_js_hooks_coexist(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Python and JavaScript hooks can coexist with correct prefixes."""
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        create_additional_settings(
            hooks=golden_config.get('hooks', {}),
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=None,
            permissions=None,
            env=None,
            include_co_authored_by=None,
            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=None,
        )

        settings_path = claude_dir / f'{cmd}-additional-settings.json'
        data = json.loads(settings_path.read_text())

        python_hooks_found = 0
        js_hooks_found = 0
        errors: list[str] = []
        hooks = data.get('hooks', {})

        for event_hooks in hooks.values():
            for hook_group in event_hooks:
                for hook in hook_group.get('hooks', []):
                    command = hook.get('command', '')

                    if '.py' in command:
                        python_hooks_found += 1
                        if 'uv run' not in command:
                            errors.append(f'Python hook missing uv run: {command}')

                    if any(ext in command for ext in ['.js', '.mjs', '.cjs']):
                        js_hooks_found += 1
                        if not command.startswith('node '):
                            errors.append(f'JS hook missing node prefix: {command}')

        # Verify we actually tested both types
        assert python_hooks_found > 0, 'No Python hooks found in golden config'
        assert js_hooks_found > 0, 'No JavaScript hooks found in golden config'
        assert not errors, 'Mixed hooks validation failed:\n' + '\n'.join(errors)

    def test_no_cmd_wrapper_for_node(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify JavaScript hooks do NOT have cmd /c wrapper (node.exe is binary)."""
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        create_additional_settings(
            hooks=golden_config.get('hooks', {}),
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=None,
            permissions=None,
            env=None,
            include_co_authored_by=None,
            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=None,
        )

        settings_path = claude_dir / f'{cmd}-additional-settings.json'
        data = json.loads(settings_path.read_text())

        errors: list[str] = []
        hooks = data.get('hooks', {})

        for event_hooks in hooks.values():
            for hook_group in event_hooks:
                for hook in hook_group.get('hooks', []):
                    command = hook.get('command', '')
                    if any(ext in command for ext in ['.js', '.mjs', '.cjs']) and 'cmd /c' in command.lower():
                        errors.append(
                            f'JS hook has unnecessary cmd /c wrapper: {command}',
                        )

        assert not errors, 'cmd /c wrapper validation failed:\n' + '\n'.join(errors)
