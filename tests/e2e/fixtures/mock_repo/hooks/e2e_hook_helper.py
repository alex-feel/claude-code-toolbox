"""Shared helper module imported by the E2E hook scripts.

Declared in ``hooks.helpers``, so it installs into the same directory as the
hook scripts and is reachable as a sibling import without ever being
registered as a command or a status-line file. It carries no shebang because
nothing ever launches it directly.
"""

HELPER_MARKER = 'e2e-hook-helper-loaded'


def describe() -> dict[str, str]:
    """Return the marker payload a hook script embeds in its own output.

    Returns:
        Mapping whose presence in a hook's output proves the sibling import
        resolved at run time.
    """
    return {'helper': HELPER_MARKER}
