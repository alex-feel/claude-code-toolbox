"""
Subcommand dispatcher for the claude-code-toolbox distribution.

Exposes the console-script entry point that routes ``claude-code-toolbox setup``
to setup_environment.main() and ``claude-code-toolbox install`` to
install_claude.main(). This is the ONLY module permitted to import both
standalone scripts; neither standalone script may import this module (see the
Standalone Script Policy in CLAUDE.md). Relative imports let the same file
serve as ``scripts.cli`` in the repository and ``claude_code_toolbox.cli``
inside the built wheel.
"""

import sys

USAGE = '''usage: claude-code-toolbox <command> [args...]

commands:
  setup      Configure a Claude Code environment from a YAML configuration
  install    Install Claude Code only, without environment configuration
'''


def main() -> None:
    """Dispatch the subcommand to the matching standalone script's main().

    Raises:
        SystemExit: With code 0 for help output and code 2 for a missing or
            unknown subcommand.
    """
    argv = sys.argv[1:]
    if not argv:
        print(USAGE, file=sys.stderr)
        raise SystemExit(2)
    command = argv[0]
    if command in ('-h', '--help'):
        print(USAGE)
        raise SystemExit(0)
    if command not in ('setup', 'install'):
        print(f'error: unknown command {command!r}\n\n{USAGE}', file=sys.stderr)
        raise SystemExit(2)
    # Neither delegate accepts an argv parameter; both read sys.argv directly,
    # so the subcommand token must be stripped or setup's argparse would read
    # it as the positional config argument.
    sys.argv = [f'{sys.argv[0]} {command}', *argv[1:]]
    if command == 'setup':
        # Deferred import: the delegate modules are large and only one is needed per run.
        from .setup_environment import main as setup_main

        setup_main()
        return
    if any(arg in ('-h', '--help') for arg in argv[1:]):
        # install_claude.main() builds no ArgumentParser, so a help request
        # must be answered here instead of silently starting an installation.
        print(USAGE)
        raise SystemExit(0)
    from .install_claude import main as install_main

    install_main()


if __name__ == '__main__':
    main()
