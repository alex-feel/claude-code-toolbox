#!/usr/bin/env python3
"""Count all entities in the repository and generate badge data."""

import json
from pathlib import Path

import yaml


def count_files(directory: Path, pattern: str) -> int:
    """Count files matching a pattern in a directory."""
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def validate_yaml(file_path: Path) -> bool:
    """Check if a YAML file is valid."""
    try:
        with open(file_path, encoding='utf-8') as f:
            yaml.safe_load(f)
        return True
    except (yaml.YAMLError, OSError):
        return False


def count_valid_configs(directory: Path) -> int:
    """Count valid YAML configuration files."""
    if not directory.exists():
        return 0

    count = 0
    for file in directory.glob('*.yaml'):
        if validate_yaml(file):
            count += 1
    for file in directory.glob('*.yml'):
        if validate_yaml(file):
            count += 1
    return count


def main():
    """Count all entities and generate badge data."""
    repo_root = Path(__file__).parent.parent

    # Count all entities
    counts = {
        # Environment configurations
        'environments': count_valid_configs(repo_root / 'environments' / 'library'),
        'env_templates': count_files(repo_root / 'environments' / 'templates', '*.yaml') +
                        count_files(repo_root / 'environments' / 'templates', '*.yml'),

        # Agents (subagents)
        'agents': count_files(repo_root / 'agents' / 'library', '*.md'),
        'agent_templates': count_files(repo_root / 'agents' / 'templates', '*.md'),

        # Slash commands
        'commands': count_files(repo_root / 'slash-commands' / 'library', '*.md'),
        'command_templates': count_files(repo_root / 'slash-commands' / 'templates', '*.md'),

        # System prompts
        'prompts': count_files(repo_root / 'system-prompts' / 'library', '*.md'),
        'prompt_templates': count_files(repo_root / 'system-prompts' / 'templates', '*.md'),

        # Output styles
        'styles': count_files(repo_root / 'output-styles' / 'library', '*.md'),
        'style_templates': count_files(repo_root / 'output-styles' / 'templates', '*.md'),

        # Hooks
        'hooks': count_files(repo_root / 'hooks' / 'library', '*.py') +
                count_files(repo_root / 'hooks' / 'library', '*.sh') +
                count_files(repo_root / 'hooks' / 'library', '*.ps1'),

        # Total ready-to-use components
        'total_components': 0,
    }

    # Calculate total
    counts['total_components'] = (
        counts['environments'] +
        counts['agents'] +
        counts['commands'] +
        counts['prompts'] +
        counts['styles'] +
        counts['hooks']
    )

    # Generate badge data with colors and messages
    badges = {
        'environments': {
            'label': 'Environments',
            'message': str(counts['environments']),
            'color': 'blue',
        },
        'agents': {
            'label': 'Agents',
            'message': str(counts['agents']),
            'color': 'green',
        },
        'commands': {
            'label': 'Commands',
            'message': str(counts['commands']),
            'color': 'yellow',
        },
        'prompts': {
            'label': 'Prompts',
            'message': str(counts['prompts']),
            'color': 'orange',
        },
        'styles': {
            'label': 'Styles',
            'message': str(counts['styles']),
            'color': 'purple',
        },
        'hooks': {
            'label': 'Hooks',
            'message': str(counts['hooks']),
            'color': 'red',
        },
        'total': {
            'label': 'Total Components',
            'message': str(counts['total_components']),
            'color': 'brightgreen',
        },
    }

    # Save as JSON for GitHub Pages or badges branch
    badges_dir = repo_root / '.github' / 'badges'
    badges_dir.mkdir(parents=True, exist_ok=True)

    with open(badges_dir / 'entity-counts.json', 'w') as f:
        json.dump({
            'counts': counts,
            'badges': badges,
        }, f, indent=2)

    # Also save individual badge JSONs for shields.io endpoint badge
    for key, badge_data in badges.items():
        with open(badges_dir / f'{key}.json', 'w') as f:
            json.dump({
                'schemaVersion': 1,
                'label': badge_data['label'],
                'message': badge_data['message'],
                'color': badge_data['color'],
            }, f, indent=2)

    # Print summary
    print('Entity counts:')
    print(f'  Environments: {counts["environments"]}')
    print(f'  Agents: {counts["agents"]}')
    print(f'  Slash Commands: {counts["commands"]}')
    print(f'  System Prompts: {counts["prompts"]}')
    print(f'  Output Styles: {counts["styles"]}')
    print(f'  Hooks: {counts["hooks"]}')
    print(f'  Total Components: {counts["total_components"]}')
    print('\nBadge data saved to .github/badges/')


if __name__ == '__main__':
    main()
