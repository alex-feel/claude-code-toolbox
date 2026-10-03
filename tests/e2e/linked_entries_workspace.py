"""Profile layouts the real-binary linked-entries tests run the binary against.

A Workspace is an isolated home holding one source profile that carries
every linkable entry for real (its hook script locked with
``uv lock --script`` beside its helper and project-overrides/ file), plus a
running fake API. Each Profile it creates is ``~/.claude/<name>`` with
every entry placed as a copy, a symlink or a junction of the source entry,
a config.json written by the toolbox's own create_profile_config(), and a
child environment confined to the workspace.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts import setup_environment
from tests.e2e import linked_entries_support as support
from tests.e2e.fake_anthropic_api import FakeAnthropicServer


@dataclass
class Profile:
    """One profile directory the binary runs against."""

    name: str
    config_dir: Path
    project_dir: Path
    env: dict[str, str]
    server: FakeAnthropicServer

    def run(self, prompt: str, *extra: str) -> support.ClaudeRun:
        """Run one `claude -p` turn in this profile.

        config.json is passed with ``--settings``, the way the launcher of an
        installed profile delivers it: Claude Code reads settings.json from
        the config dir on its own, but config.json only through that flag.

        Args:
            prompt: The user prompt.
            extra: Further claude arguments placed after the prompt.

        Returns:
            The parsed run.
        """
        assert support.CLAUDE_CMD is not None
        settings = ['--settings', str(self.config_dir / 'config.json')]
        argv = [str(support.CLAUDE_CMD), *support.print_args(prompt, *extra, *settings)]
        return support.run_stream_json(argv, env=self.env, cwd=self.project_dir, server=self.server)

    def run_launcher(self, mode: str, prompt: str) -> support.ClaudeRun:
        """Run one turn through the launcher the toolbox writes for this profile.

        The launcher is created exactly as an install creates it and run with
        bash (Git Bash on Windows), so the system prompt reaches claude the
        way it does for an installed command.

        Args:
            mode: The command-defaults mode, 'replace' or 'append'.
            prompt: The user prompt.

        Returns:
            The parsed run.
        """
        created = setup_environment.create_launcher_script(self.config_dir, self.name, support.PROMPT_FILE, mode)
        assert created is not None
        bash = setup_environment.find_bash_windows() if sys.platform == 'win32' else shutil.which('bash')
        assert bash is not None, 'bash is required to run the toolbox launcher'
        argv = [bash, (self.config_dir / 'launch.sh').as_posix(), *support.print_args(prompt)]
        return support.run_stream_json(argv, env=self.env, cwd=self.project_dir, server=self.server)


@dataclass
class Workspace:
    """An isolated home with a populated source profile and the fake API."""

    home: Path
    source: Path
    project_dir: Path
    hook_marker: Path
    server: FakeAnthropicServer

    def make_profile(
        self,
        name: str,
        kind: str,
        *,
        absent: frozenset[str] = frozenset(),
        hooks_enabled: bool = True,
    ) -> Profile:
        """Create ~/.claude/<name> with every linkable entry placed as ``kind``.

        Entries named in ``absent`` are left out regardless of ``kind``;
        config.json is written by create_profile_config() so it carries the
        hook commands and the output style exactly as an install would.

        Args:
            name: The profile directory name under ~/.claude.
            kind: How each entry is placed: 'real', 'symlink' or 'junction'.
            absent: Entries to leave out.
            hooks_enabled: Whether config.json declares the sentinel hook.

        Returns:
            The profile, with its child environment ready.
        """
        config_dir = self.home / '.claude' / name
        config_dir.mkdir(parents=True)
        for entry in support.LINKABLE_ENTRIES:
            support.place_entry(self.source, config_dir, entry, 'absent' if entry in absent else kind)
        profile_config, user_settings = support.profile_config_sections(hooks_enabled)
        assert setup_environment.create_profile_config(profile_config, config_dir, user_settings=user_settings)
        support.seed_global_config(config_dir, self.project_dir)
        env = support.claude_child_env(
            config_dir=config_dir, home=self.home, api_url=self.server.url, claude_cmd=support.CLAUDE_CMD,
        )
        return Profile(name=name, config_dir=config_dir, project_dir=self.project_dir, env=env, server=self.server)

    def hook_records(self) -> list[dict[str, Any]]:
        """Return the lines the sentinel hook appended, oldest first."""
        if not self.hook_marker.is_file():
            return []
        return [json.loads(line) for line in self.hook_marker.read_text(encoding='utf-8').splitlines() if line]


def open_workspace(tmp_path: Path) -> Iterator[Workspace]:
    """Yield an isolated home with a populated source profile and a running fake API.

    Meant to back a function-scoped fixture (``yield from open_workspace(tmp_path)``);
    the fake API stops when the fixture finalizes.

    Args:
        tmp_path: The test's temporary directory.

    Yields:
        The workspace.
    """
    home = tmp_path / 'home'
    source = home / '.claude' / 'src-profile'
    source.mkdir(parents=True)
    project_dir = tmp_path / 'project'
    project_dir.mkdir()
    hook_marker = tmp_path / 'hook_marker.jsonl'
    support.write_source_entries(source, hook_marker)
    support.lock_hook_script(source, support.isolated_home_env(home))
    server = FakeAnthropicServer().start()
    try:
        yield Workspace(home=home, source=source, project_dir=project_dir, hook_marker=hook_marker, server=server)
    finally:
        server.stop()
