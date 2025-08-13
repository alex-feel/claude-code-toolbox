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

## Development Guidelines

### PowerShell Scripts (Windows)

1. **Compatibility**: Target PowerShell 5.1 minimum
2. **Error Handling**: Use proper try-catch blocks
3. **Logging**: Use consistent Write-Info/Ok/Warn/Err functions
4. **Testing**: Test on Windows 10 and 11
5. **Documentation**: Include clear comments and usage examples

### Shell Scripts (Linux/macOS)

1. **Compatibility**: Target bash 4.0+
2. **Portability**: Test on multiple distributions/versions
3. **Error Handling**: Use `set -euo pipefail`
4. **Style**: Follow Google Shell Style Guide
5. **Cross-platform**: Consider differences between Linux and macOS

### Sub-agents

1. **Format**: Markdown files with YAML frontmatter
2. **Required Fields**: name, description
3. **Optional Fields**: tools, model, color
4. **Location**: Store in `agents/examples/` or `agents/templates/`
5. **Testing**: Verify in Claude Code before submitting

### Slash Commands

1. **Format**: Simple Markdown files without frontmatter
2. **Naming**: Use descriptive filenames (becomes command name)
3. **Arguments**: Use `$ARGUMENTS` for dynamic content
4. **Location**: Store in `slash-commands/examples/` or `slash-commands/templates/`

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

1. **Installation Scripts**
   ```powershell
   # Windows
   .\install-claude-windows.ps1 -Verbose

   # Linux/macOS
   bash install-claude-linux.sh
   ```

2. **Sub-agents**
   - Copy to `.claude/agents/`
   - Test in Claude Code
   - Verify tool permissions work correctly

3. **Slash Commands**
   - Copy to `.claude/commands/`
   - Test with various arguments
   - Ensure `$ARGUMENTS` substitution works

4. **Documentation**
   - Check for broken links
   - Verify code examples work
   - Ensure formatting is correct

## Project Structure

```text
claude-code-toolbox/
├── scripts/
│   ├── windows/          # Windows PowerShell scripts
│   ├── linux/            # Linux shell scripts
│   ├── macos/            # macOS shell scripts
│   └── common/           # Shared utilities
├── agents/
│   ├── examples/         # Example sub-agents
│   └── templates/        # Sub-agent templates
├── slash-commands/
│   ├── examples/         # Example commands
│   └── templates/        # Command templates
├── docs/                 # All documentation
└── .github/              # GitHub workflows and templates
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

1. Ensure all tests pass
2. Update documentation as needed
3. Use conventional commits for automatic changelog generation
4. Request review from maintainers
5. Address review feedback
6. Squash commits if requested
7. Merge after approval

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

1. Automated checks must pass
2. Code review by maintainers
3. Testing in relevant environments
4. Documentation review
5. Final approval and merge

## Questions?

- Open a discussion for general questions
- Check existing issues and discussions
- Refer to documentation first
- Contact maintainers if needed

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

Thank you for contributing to Claude Code Toolbox!
