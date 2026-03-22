"""
Pydantic models for GitHub repository sync configuration.

Defines the schema for sync-config.yaml files used by .github/sync_to_repos.py.
"""

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator


class FileMapping(BaseModel):
    """File mapping configuration.

    Supports two formats:
    - Simple string: "path/to/file.txt" (source and dest are the same)
    - Full mapping: {source: "path/source.txt", dest: "path/dest.txt"}
    """

    source: str = Field(..., description='Source file path relative to repository root')
    dest: str = Field(..., description='Destination file path relative to target repository root')

    @field_validator('source', 'dest')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate file paths are not empty and do not contain null bytes."""
        if not v or not v.strip():
            raise ValueError('Path cannot be empty')
        if '\x00' in v:
            raise ValueError('Path cannot contain null bytes')
        return v


class DirectoryMapping(BaseModel):
    """Directory mapping configuration."""

    source: str = Field(..., description='Source directory path relative to repository root')
    dest: str = Field(..., description='Destination directory path relative to target repository root')
    delete_orphaned: bool = Field(
        False,
        description='Delete files in destination that do not exist in source',
    )
    exclude: list[str] = Field(
        default_factory=list,
        description='Glob patterns for files to exclude from sync (e.g., "*.pyc", "**/__pycache__/**")',
    )

    @field_validator('source', 'dest')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate directory paths are not empty and do not contain null bytes."""
        if not v or not v.strip():
            raise ValueError('Path cannot be empty')
        if '\x00' in v:
            raise ValueError('Path cannot contain null bytes')
        return v


class Repository(BaseModel):
    """Target repository configuration."""

    name: str = Field(..., description='Repository name in format owner/repo')
    branch: str = Field('main', description='Target branch name')
    directories: list[DirectoryMapping] = Field(
        default_factory=lambda: list[DirectoryMapping](),
        description='Directories to sync',
    )
    files: list[str | FileMapping] = Field(
        default_factory=lambda: list[str | FileMapping](),
        description='Files to sync (simple path or FileMapping)',
    )
    exclude: list[str] = Field(
        default_factory=lambda: list[str](),
        description='Glob patterns for files to exclude',
    )

    @field_validator('name')
    @classmethod
    def validate_repo_name(cls, v: str) -> str:
        """Validate repository name format (owner/repo)."""
        if not v or not v.strip():
            raise ValueError('Repository name cannot be empty')
        if '/' not in v:
            raise ValueError('Repository name must be in format owner/repo')
        parts = v.split('/')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError('Repository name must be in format owner/repo')
        return v

    @field_validator('branch')
    @classmethod
    def validate_branch(cls, v: str) -> str:
        """Validate branch name is not empty."""
        if not v or not v.strip():
            raise ValueError('Branch name cannot be empty')
        return v

    @model_validator(mode='after')
    def validate_has_content(self) -> 'Repository':
        """Validate that repository has at least one directory or file to sync."""
        if not self.directories and not self.files:
            raise ValueError('Repository must have at least one directory or file to sync')
        return self

    def get_normalized_files(self) -> list[FileMapping]:
        """Convert all files to FileMapping objects.

        Returns:
            List of FileMapping objects where simple strings are converted
            to FileMapping with source=dest.
        """
        result: list[FileMapping] = []
        for item in self.files:
            if isinstance(item, str):
                result.append(FileMapping(source=item, dest=item))
            else:
                result.append(item)
        return result


class SyncDefaults(BaseModel):
    """Default settings for sync operations."""

    commit_message_prefix: str = Field(
        default='chore: sync from source',
        description='Prefix for commit messages',
    )
    delete_orphaned: bool = Field(
        default=False,
        description='Default value for delete_orphaned in directory mappings',
    )


class SyncConfig(BaseModel):
    """Complete sync configuration model."""

    model_config = ConfigDict(str_strip_whitespace=True)

    version: str = Field('1', description='Configuration version')
    defaults: SyncDefaults = Field(
        default_factory=lambda: SyncDefaults(),
        description='Default settings',
    )
    repositories: list[Repository] = Field(
        ...,
        min_length=1,
        description='Target repositories to sync to',
    )

    @field_validator('version')
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate version is supported."""
        supported_versions = ['1']
        if v not in supported_versions:
            raise ValueError(f'Unsupported config version: {v}. Supported: {supported_versions}')
        return v
