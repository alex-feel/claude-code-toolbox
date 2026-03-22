#!/usr/bin/env python3
"""
Sync files and directories to target GitHub repositories.

Reads configuration from a YAML file and syncs specified files and directories
to one or more target repositories. Supports dry-run mode for testing.

Requires Python 3.12+
"""

import argparse
import fnmatch
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from pydantic import ValidationError
from sync_config import Repository
from sync_config import SyncConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
)
logger = logging.getLogger(__name__)


def should_exclude_file(relative_path: Path, exclude_patterns: list[str]) -> bool:
    """Check if a file path should be excluded based on glob patterns.

    Args:
        relative_path: File path relative to the sync directory.
        exclude_patterns: List of glob patterns to check against.

    Returns:
        True if the file should be excluded, False otherwise.
    """
    if not exclude_patterns:
        return False

    path_str = str(relative_path).replace('\\', '/')  # Normalize for cross-platform
    return any(fnmatch.fnmatch(path_str, pattern) for pattern in exclude_patterns)


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result.

    Args:
        cmd: Command and arguments to run.
        cwd: Working directory for the command.
        capture_output: Whether to capture stdout/stderr.

    Returns:
        CompletedProcess with the result.
    """
    logger.debug(f'Running: {" ".join(cmd)}')
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture_output,
        text=True,
        check=True,
    )


def clone_repository(repo_name: str, branch: str, target_dir: Path, gh_pat: str) -> None:
    """Clone a repository to a target directory.

    Args:
        repo_name: Repository name in format owner/repo.
        branch: Branch to clone.
        target_dir: Directory to clone into.
        gh_pat: GitHub Personal Access Token for authentication.
    """
    clone_url = f'https://x-access-token:{gh_pat}@github.com/{repo_name}.git'
    logger.info(f'Cloning {repo_name} (branch: {branch}) to {target_dir}')

    run_command(['git', 'clone', '--branch', branch, '--single-branch', clone_url, str(target_dir)])


def sync_file(source: Path, dest: Path, dry_run: bool) -> bool:
    """Sync a single file from source to destination.

    Args:
        source: Source file path.
        dest: Destination file path.
        dry_run: If True, only log actions without executing.

    Returns:
        True if file was synced (or would be synced in dry-run), False otherwise.
    """
    if not source.exists():
        logger.warning(f'Source file does not exist: {source}')
        # If source doesn't exist but dest does, remove dest
        if dest.exists():
            if dry_run:
                logger.info(f'[DRY-RUN] Would delete: {dest}')
            else:
                logger.info(f'Deleting (source removed): {dest}')
                dest.unlink()
            return True
        return False

    # Ensure destination directory exists
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        if dest.exists():
            logger.info(f'[DRY-RUN] Would update: {dest}')
        else:
            logger.info(f'[DRY-RUN] Would create: {dest}')
    else:
        logger.info(f'Syncing: {source} -> {dest}')
        shutil.copy2(source, dest)

    return True


def sync_directory(
    source: Path,
    dest: Path,
    delete_orphaned: bool,
    dry_run: bool,
    exclude_patterns: list[str] | None = None,
) -> int:
    """Sync a directory from source to destination.

    Args:
        source: Source directory path.
        dest: Destination directory path.
        delete_orphaned: If True, delete files in dest that don't exist in source.
        dry_run: If True, only log actions without executing.
        exclude_patterns: Glob patterns for files to exclude from sync.

    Returns:
        Number of files synced.
    """
    synced_count = 0
    exclude = exclude_patterns or []

    if not source.exists():
        logger.warning(f'Source directory does not exist: {source}')
        if dest.exists() and delete_orphaned:
            if dry_run:
                logger.info(f'[DRY-RUN] Would delete directory: {dest}')
            else:
                logger.info(f'Deleting directory (source removed): {dest}')
                shutil.rmtree(dest)
        return synced_count

    # Ensure destination directory exists
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    # Get all files in source
    source_files: set[Path] = set()
    for source_file in source.rglob('*'):
        if source_file.is_file():
            relative_path = source_file.relative_to(source)

            # Skip excluded files
            if should_exclude_file(relative_path, exclude):
                logger.debug(f'Excluding: {relative_path}')
                continue

            source_files.add(relative_path)
            dest_file = dest / relative_path

            if sync_file(source_file, dest_file, dry_run):
                synced_count += 1

    # Delete orphaned files if requested (skip excluded files)
    if delete_orphaned and dest.exists():
        for dest_file in dest.rglob('*'):
            if dest_file.is_file():
                relative_path = dest_file.relative_to(dest)
                # Skip excluded files - they should not be deleted
                if should_exclude_file(relative_path, exclude):
                    continue
                if relative_path not in source_files:
                    if dry_run:
                        logger.info(f'[DRY-RUN] Would delete orphan: {dest_file}')
                    else:
                        logger.info(f'Deleting orphan: {dest_file}')
                        dest_file.unlink()
                    synced_count += 1

        # Clean up empty directories
        if not dry_run:
            for dest_dir in sorted(dest.rglob('*'), reverse=True):
                if dest_dir.is_dir() and not any(dest_dir.iterdir()):
                    dest_dir.rmdir()

    return synced_count


def sync_repository(
    repo: Repository,
    source_root: Path,
    target_dir: Path,
    commit_message_prefix: str,
    source_sha: str,
    dry_run: bool,
) -> bool:
    """Sync files and directories to a target repository.

    Args:
        repo: Repository configuration.
        source_root: Root directory of the source repository.
        target_dir: Directory where target repository is cloned.
        commit_message_prefix: Prefix for commit message.
        source_sha: Short SHA of source commit.
        dry_run: If True, only log actions without executing.

    Returns:
        True if changes were committed and pushed, False otherwise.
    """
    synced_count = 0

    # Sync directories
    for dir_mapping in repo.directories:
        source_dir = source_root / dir_mapping.source.rstrip('/')
        dest_dir = target_dir / dir_mapping.dest.rstrip('/')

        logger.info(f'Syncing directory: {dir_mapping.source} -> {dir_mapping.dest}')
        synced_count += sync_directory(
            source_dir,
            dest_dir,
            dir_mapping.delete_orphaned,
            dry_run,
            dir_mapping.exclude,
        )

    # Sync individual files
    for file_mapping in repo.get_normalized_files():
        source_file = source_root / file_mapping.source
        dest_file = target_dir / file_mapping.dest

        if sync_file(source_file, dest_file, dry_run):
            synced_count += 1

    logger.info(f'Synced {synced_count} items for {repo.name}')

    if dry_run:
        logger.info('[DRY-RUN] Would check for changes and commit')
        return True

    # Check if there are changes
    status_result = run_command(['git', 'status', '--porcelain'], cwd=target_dir)
    if not status_result.stdout.strip():
        logger.info('No changes to commit')
        return False

    # Commit and push changes
    commit_message = f'{commit_message_prefix} {source_sha}'
    logger.info(f'Committing changes: {commit_message}')

    run_command(['git', 'add', '-A'], cwd=target_dir)
    run_command(['git', 'commit', '-m', commit_message], cwd=target_dir)
    run_command(['git', 'push', 'origin', f'HEAD:{repo.branch}'], cwd=target_dir)

    logger.info(f'Successfully pushed changes to {repo.name}')
    return True


def load_config(config_path: Path) -> SyncConfig:
    """Load and validate sync configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Validated SyncConfig object.

    Raises:
        FileNotFoundError: If config file does not exist.
        ValueError: If configuration file is empty.
    """
    if not config_path.exists():
        raise FileNotFoundError(f'Config file not found: {config_path}')

    with open(config_path, encoding='utf-8') as f:
        content = yaml.safe_load(f)

    if content is None:
        raise ValueError('Empty configuration file')

    return SyncConfig(**content)


def get_source_sha(source_root: Path) -> str:
    """Get the short SHA of the current commit in the source repository.

    Args:
        source_root: Root directory of the source repository.

    Returns:
        Short SHA string, or 'unknown' if not a git repository.
    """
    try:
        result = run_command(['git', 'rev-parse', '--short', 'HEAD'], cwd=source_root)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return 'unknown'


def main() -> None:
    """Main entry point for the sync script."""
    parser = argparse.ArgumentParser(
        description='Sync files and directories to target GitHub repositories',
    )
    parser.add_argument(
        'config',
        help='Path to sync configuration YAML file',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes',
    )
    parser.add_argument(
        '--source-root',
        default='.',
        help='Root directory of source repository (default: current directory)',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output',
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get GitHub PAT from environment
    gh_pat = os.environ.get('GH_PAT')
    if not gh_pat and not args.dry_run:
        logger.error('GH_PAT environment variable is required (or use --dry-run)')
        sys.exit(1)

    # Load configuration
    config_path = Path(args.config)
    source_root = Path(args.source_root).resolve()

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f'YAML parsing error: {e}')
        sys.exit(1)
    except ValidationError as e:
        logger.error('Configuration validation failed:')
        for error in e.errors():
            loc = ' -> '.join(str(item) for item in error['loc'])
            logger.error(f'  {loc}: {error["msg"]}')
        sys.exit(1)

    # Configure git author
    if not args.dry_run:
        run_command(['git', 'config', '--global', 'user.name', 'sync-bot'])
        run_command(['git', 'config', '--global', 'user.email', 'sync-bot@users.noreply.github.com'])

    # Get source commit SHA
    source_sha = get_source_sha(source_root)
    logger.info(f'Source commit: {source_sha}')

    if args.dry_run:
        logger.info('=== DRY-RUN MODE ===')

    # Process each repository
    success_count = 0
    for repo in config.repositories:
        logger.info(f'\n{"=" * 60}')
        logger.info(f'Processing repository: {repo.name}')
        logger.info(f'{"=" * 60}')

        if args.dry_run:
            # In dry-run mode, just simulate the sync without cloning
            logger.info(f'[DRY-RUN] Would clone {repo.name} (branch: {repo.branch})')
            sync_repository(
                repo,
                source_root,
                source_root,  # Use source as target for dry-run path display
                config.defaults.commit_message_prefix,
                source_sha,
                dry_run=True,
            )
            success_count += 1
        else:
            # Create temporary directory for clone
            with tempfile.TemporaryDirectory() as temp_dir:
                target_dir = Path(temp_dir) / 'repo'
                try:
                    clone_repository(repo.name, repo.branch, target_dir, gh_pat or '')
                    if sync_repository(
                        repo,
                        source_root,
                        target_dir,
                        config.defaults.commit_message_prefix,
                        source_sha,
                        dry_run=False,
                    ):
                        success_count += 1
                except subprocess.CalledProcessError as e:
                    logger.error(f'Failed to process {repo.name}: {e}')
                    if e.stderr:
                        logger.error(f'stderr: {e.stderr}')
                    continue

    logger.info(f'\n{"=" * 60}')
    logger.info(f'Sync complete. Processed {success_count}/{len(config.repositories)} repositories.')
    logger.info(f'{"=" * 60}')


if __name__ == '__main__':
    main()
