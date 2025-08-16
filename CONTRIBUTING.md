# Contributing to Claude Code Toolbox

Thank you for your interest in contributing to the Claude Code Toolbox! We appreciate your help in improving our installation scripts, sub-agents, slash commands, and documentation.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for all contributors.

## Commit Conventions

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification to maintain a clear and consistent commit history.

### Commit Message Format

```text
type: description

[optional body]

[optional footer]
```

### Commit Types

Below are the conventional commit types we use. These types are used by Release Please to automatically:
- Generate CHANGELOG.md entries
- Create release PRs
- Bump version numbers according to semantic versioning

**Version Bump Rules:**
- `feat`: Triggers a minor version bump (0.x.0)
- `fix`: Triggers a patch version bump (0.0.x)
- `feat!` or `fix!` or `BREAKING CHANGE:`: Triggers a major version bump (x.0.0)
- Other types (`chore`, `docs`, `ci`, `test`): No version bump but may appear in changelog

#### feat
For new features or functionality:
- No scopes needed
- Example: `feat: add automatic Node.js version detection`
- Example: `feat: implement Linux installation script`
- Example: `feat: add performance-optimizer sub-agent`
- Example: `feat: create debug slash command`

#### fix
For bug fixes or reverting previous commits:
- No scopes needed
- Example: `fix: resolve Git Bash detection on Windows 11`
- Example: `fix: handle spaces in installation paths`
- Example: `fix: correct Node.js version comparison logic`
- Example: `fix: restore PowerShell execution policy after install`

#### chore
For maintenance tasks and infrastructure:
- No scopes needed
- Example: `chore: update PowerShell script analyzer rules`
- Example: `chore: reorganize agent templates directory`
- Example: `chore: update release workflow`
- Example: `chore: bump minimum Node.js version to 18`

#### docs
For documentation improvements:
- No scopes needed
- Example: `docs: update installation instructions for Windows`
- Example: `docs: add troubleshooting guide for proxy setups`
- Example: `docs: clarify sub-agent frontmatter fields`
- Example: `docs: add examples for slash commands`

#### ci
For changes to CI/CD configuration files and pipelines:
- No scopes needed
- Example: `ci: add GitHub Actions lint workflow`
- Example: `ci: configure release automation`
- Example: `ci: add PowerShell script validation`
- Example: `ci: update security scanning configuration`

#### test
For test-related changes:
- No scopes needed
- Example: `test: add installation script unit tests`
- Example: `test: implement sub-agent validation tests`
- Example: `test: cover edge cases in path detection`
- Example: `test: add cross-platform compatibility tests`

### Example Commit Messages

```text
feat: add automatic Git Bash installation for Windows

- Detect existing Git installation
- Install via winget or direct download
- Configure CLAUDE_CODE_GIT_BASH_PATH environment variable
- Verify installation with claude doctor
```

```text
fix: handle corporate proxy authentication

Resolve installation failures behind corporate proxies by:
- Supporting authenticated proxy settings
- Using system proxy configuration
- Providing fallback download methods
```

```text
docs: add macOS installation guide

- Document Homebrew installation method
- Include manual installation steps
- Add troubleshooting section for common issues
```

## How to Contribute

### Reporting Issues

1. Check existing issues to avoid duplicates
2. Use issue templates when available
3. Include:
   - Clear description of the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - System information (OS, versions)
   - Error messages and logs

### Submitting Pull Requests

1. **Fork** the repository and create a feature branch from `main`
2. Make your changes following our guidelines
3. Test thoroughly on relevant platforms
4. Commit with clear messages following our conventions
5. Push to your fork
6. Open a Pull Request with a clear description

## Development Setup

### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality. Install them locally:

```bash
# Install pre-commit
pip install pre-commit

# Install the git hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

**Configured hooks:**
- **Ruff**: Python linting and auto-formatting (Flake8, isort, quotes)
- **Markdownlint**: Markdown formatting and style checking
- **PSScriptAnalyzer**: PowerShell script analysis (Windows only)
- **Shellcheck**: Shell script linting
- **Commitizen**: Commit message format validation
- **JSON/YAML validators**: Syntax checking
- **File formatting**: End-of-file fixing, trailing whitespace removal

## Development Guidelines

### PowerShell Scripts (Windows)

1. **Compatibility**: Target PowerShell 5.1 minimum
2. **Error Handling**: Use proper try-catch blocks
3. **Logging**: Use consistent Write-Info/Ok/Warn/Err functions
4. **Testing**: Test on Windows 10 and 11
5. **Linting**: Must pass PSScriptAnalyzer checks
6. **Documentation**: Include clear comments and usage examples

### Shell Scripts (Linux/macOS)

1. **Compatibility**: Target bash 4.0+
2. **Portability**: Test on multiple distributions/versions
3. **Error Handling**: Use `set -euo pipefail`
4. **Style**: Follow Google Shell Style Guide
5. **Linting**: Must pass shellcheck with `--severity=warning`
6. **Cross-platform**: Consider differences between Linux and macOS

### Python Scripts

1. **Compatibility**: Python 3.12+ (managed by uv)
2. **Style**: Must pass Ruff linting and formatting
3. **Error Handling**: Comprehensive try-except blocks
4. **Cross-platform**: Test on Windows, Linux, and macOS
5. **Dependencies**: Use uv for package management

### Sub-agents

1. **Format**: Markdown files with YAML frontmatter
2. **Required Fields**: name, description
3. **Optional Fields**: tools, model, color
4. **Description**: Last sentence MUST contain "Use PROACTIVELY" or "MUST BE USED"
5. **Location**: Store in `agents/examples/` or `agents/templates/`
6. **Testing**: Verify in Claude Code before submitting

### Slash Commands

1. **Format**: Markdown files with optional YAML frontmatter
2. **Naming**: Use descriptive filenames (becomes command name)
3. **Arguments**: Use `$ARGUMENTS` for dynamic content
4. **Frontmatter fields**: description, argument-hint, model, allowed-tools
5. **Location**: Store in `slash-commands/examples/` or `slash-commands/templates/`

### System Prompts

1. **Format**: Markdown files for comprehensive role definitions
2. **Structure**: Role definition, core practices, subagent integration
3. **Location**: Store in `system-prompts/examples/` or `system-prompts/templates/`
4. **Testing**: Verify with `--append-system-prompt` flag

### Output Styles

1. **Format**: Markdown transformation rules
2. **Purpose**: Transform Claude's output for different professional domains
3. **Location**: Store in `output-styles/examples/` or `output-styles/templates/`

### General Guidelines

1. **Security First**
   - Never hardcode secrets or API keys
   - Validate all inputs
   - Use HTTPS for downloads
   - Implement proper error handling

2. **User Experience**
   - Clear, informative messages
   - Graceful fallbacks
   - Minimal user interaction required
   - Support common edge cases

3. **Code Quality**
   - Self-documenting code
   - Consistent formatting
   - Modular functions
   - Avoid code duplication

## Testing

### Before Submitting

Test your changes:

1. **Run Pre-commit Hooks**
   ```bash
   # Run all hooks on your changes
   pre-commit run --all-files
   ```

2. **Installation Scripts**
   ```powershell
   # Windows
   .\scripts\windows\install-claude-windows.ps1 -Verbose
   .\scripts\windows\setup-python-environment.ps1

   # Linux/macOS
   bash scripts/linux/install-claude-linux.sh
   bash scripts/linux/setup-python-environment.sh
   ```

3. **Sub-agents**
   - Copy to `.claude/agents/`
   - Test in Claude Code
   - Verify tool permissions work correctly
   - Ensure "Use PROACTIVELY" or "MUST BE USED" triggers are present

4. **Slash Commands**
   - Copy to `.claude/commands/`
   - Test with various arguments
   - Ensure `$ARGUMENTS` substitution works
   - Verify frontmatter fields if present

5. **Documentation**
   - Run markdownlint: `markdownlint-cli2 "**/*.md"`
   - Check for broken links
   - Verify code examples work
   - Ensure formatting is correct

## Project Structure

```text
claude-code-toolbox/
├── scripts/
│   ├── install-claude.py            # Cross-platform Claude installer
│   ├── setup-python-environment.py  # Cross-platform Python setup
│   ├── windows/                     # Windows bootstrap scripts
│   ├── linux/                       # Linux bootstrap scripts
│   ├── macos/                       # macOS bootstrap scripts
│   └── hooks/                       # Git hooks and validators
├── agents/
│   ├── examples/                    # 7 general-purpose sub-agents
│   └── templates/                   # Sub-agent templates
├── slash-commands/
│   ├── examples/                    # 6 ready-to-use commands
│   └── templates/                   # Command templates
├── system-prompts/
│   ├── examples/                    # 3 role-specific prompts
│   └── templates/                   # Prompt templates
├── output-styles/
│   ├── examples/                    # 6 professional styles
│   └── templates/                   # Style templates
├── mcp/                             # Model Context Protocol config
├── docs/                            # All documentation
├── .github/                         # GitHub workflows and templates
│   └── workflows/
│       ├── lint.yml                 # Linting and validation
│       └── release-please.yml       # Automated releases
├── .pre-commit-config.yaml          # Pre-commit hook configuration
├── release-please-config.json       # Release automation config
└── .release-please-manifest.json   # Version tracking
```

## Adding New Features

1. **Discuss First**: Open an issue for significant changes
2. **Design**: Document the approach in the issue
3. **Implement**: Follow coding guidelines
4. **Test**: Include test scenarios
5. **Document**: Update relevant documentation
6. **Submit**: Create a pull request

## Documentation Requirements

- Update README.md for user-facing changes
- Add/update docs/ for detailed documentation
- Include inline comments for complex logic

## Important: Version Management

- **DO NOT manually edit CHANGELOG.md** - automatically generated by Release Please
- **DO NOT manually edit version.txt** - automatically updated by Release Please
- **DO NOT manually edit .release-please-manifest.json** - managed by Release Please
- Use conventional commits to trigger automatic versioning and changelog updates

## Pull Request Process

1. Run pre-commit hooks: `pre-commit run --all-files`
2. Ensure all tests pass
3. Update documentation as needed
4. Use conventional commits for automatic changelog generation
5. Push to your fork and open PR
6. Wait for CI checks to pass:
   - Pre-commit validation (Ubuntu)
   - PSScriptAnalyzer (Windows)
   - Security scanning (Trivy)
7. Request review from maintainers
8. Address review feedback
9. Squash commits if requested
10. Merge after approval

**Release Please Workflow**:

1. After merging PRs to main, Release Please automatically:
   - Creates/updates a release PR with:
     - Generated CHANGELOG.md entries from commit messages
     - Bumped version in version.txt
     - Updated .release-please-manifest.json
   - The release PR title shows the new version number

2. When the release PR is merged:
   - A GitHub release is created with the changelog
   - A git tag is created for the version
   - The main branch contains the updated version files

3. Version bump logic:
   - `feat`: minor bump (0.x.0)
   - `fix`: patch bump (0.0.x)
   - Breaking changes: major bump (x.0.0)
   - Other types: no version change

## Review Process

1. Automated checks must pass:
   - Pre-commit hooks (Ruff, markdownlint, shellcheck, etc.)
   - PSScriptAnalyzer for PowerShell
   - Trivy security scanning
   - Commitizen validation
2. Code review by maintainers
3. Testing in relevant environments
4. Documentation review
5. Final approval and merge

## CI/CD Pipeline

### GitHub Actions Workflows

1. **Lint and Validate** (`lint.yml`):
   - Triggers on pull requests
   - Runs pre-commit hooks on Ubuntu
   - Runs PSScriptAnalyzer on Windows
   - Performs security scanning with Trivy
   - Skips Release Please PRs

2. **Release Please** (`release-please.yml`):
   - Triggers on pushes to main
   - Automatically creates release PRs
   - Generates CHANGELOG.md from commits
   - Bumps version numbers
   - Creates GitHub releases

## Questions?

- Open a discussion for general questions
- Check existing issues and discussions
- Refer to documentation first
- Contact maintainers if needed

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

Thank you for contributing to Claude Code Toolbox!
