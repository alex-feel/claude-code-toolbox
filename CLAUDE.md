# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is the Claude Code Toolbox - a community project providing automated installers and environment configuration tools for Claude Code across Windows, macOS, and Linux. The toolbox enables users to quickly set up specialized environments with custom agents, MCP servers, slash commands, and hooks.

## Key Architecture

### Two-Tier Installation System

1. **Platform-specific bootstrap scripts** (minimal ~60 lines each)
   - Windows: PowerShell scripts in `scripts/windows/`
   - Linux/macOS: Bash scripts in `scripts/linux/` and `scripts/macos/`
   - These install `uv` (Astral's Python package manager) and run Python scripts

2. **Cross-platform Python scripts** (comprehensive installers)
   - `scripts/install_claude.py`: Installs Git Bash (Windows) and Claude Code via native installers with npm fallback
   - `scripts/setup_environment.py`: Configuration-driven environment setup from YAML
   - Support three configuration sources:
     - Repository configs: `python` → downloads from repo
     - Local files: `./my-config.yaml` → loads from disk
     - Remote URLs: `https://example.com/config.yaml` → downloads from web

### Native Claude Code Installation Support

The installer uses a native-first approach with automatic npm fallback:

**Native Installation Functions:**
- `install_claude_native_windows()` - PowerShell installer for Windows
- `install_claude_native_macos()` - Shell installer for macOS
- `install_claude_native_linux()` - Shell installer for Linux
- `install_claude_native_cross_platform()` - Platform dispatcher
- `ensure_claude()` - Main orchestrator with native-first logic

### Standalone Script Policy

`install_claude.py` and `setup_environment.py` MUST be fully standalone. They MUST NEVER import from each other. No cross-imports of any kind are permitted. Both scripts are downloaded and executed independently -- users may run either script without the other being present.

**Identical Code Parts:** The following code elements MUST be kept identical between both scripts (CI tests in `tests/test_standalone_policy.py` enforce this):
- `Colors` class -- ANSI color codes for terminal output
- `find_command()` function -- comprehensive command discovery with PATHEXT normalization, retry logic, native-path-first, and platform-specific fallback paths
- `get_real_user_home()` function -- sudo-aware home directory resolution (EXACT body match)
- Shell config file list -- the set of 7 shell config files (.bashrc, .bash_profile, .profile, .zshenv, .zprofile, .zshrc, config.fish) and conditional filtering logic
- Fish config detection -- the `'fish' in str()` pattern for identifying Fish shell configs
- Marker block constants -- `# >>> claude-code-toolbox >>>` / `# <<< claude-code-toolbox <<<` strings

**Intentionally Different Code:** The following functions exist in both scripts but are INTENTIONALLY different and MUST NOT be synchronized:
- `info()`, `success()`, `warning()`, `error()` -- different output formatting per script
- `run_command()` -- different encoding/error handling per script needs
- `find_bash_windows()` -- setup_environment.py version has debug_log calls
- `is_admin()` -- different implementations per script context

**Native Path Priority:** Both `find_command()` and `verify_claude_installation()` check the native installer target path (`~/.local/bin/claude` on Unix, `~/.local/bin/claude.exe` on Windows) explicitly first, before falling back to PATH search via `shutil.which()`. This ensures the native binary is preferred over an npm binary even when PATH ordering would resolve to the npm binary first (e.g., `/usr/local/bin` preceding `~/.local/bin` on macOS). The check validates the file exists and has `st_size > 1000` to skip empty or corrupt files.

**Environment Variables:**
- `CLAUDE_CODE_TOOLBOX_INSTALL_METHOD` - Controls installation method: `auto` (default), `native`, or `npm`. In `auto` mode, unknown/unrecognized installation sources are routed to native-first with npm fallback
- `CLAUDE_CODE_TOOLBOX_VERSION` - Forces specific version via npm (native installers don't support version selection)
- `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT` - Allows running as root on Linux/macOS: `1` (only exact value `'1'` is accepted)

**Native Path Detection (Non-Windows):**

The `verify_claude_installation()` function classifies the Claude binary location to determine the upgrade strategy:

| Path Pattern                           | Detected Source | Upgrade Method             |
|----------------------------------------|-----------------|----------------------------|
| Contains `npm` or `.npm-global`        | `npm`           | npm directly               |
| Contains `.local/bin` or `.claude/bin` | `native`        | Native installer           |
| Contains `/usr/local/bin`              | `unknown`       | Native-first, npm fallback |
| Any other path                         | `unknown`       | Native-first, npm fallback |
| Not found                              | `none`          | Fresh install              |

In `auto` mode, both `native` and `unknown` sources attempt the native installer first. If native fails, npm is used as fallback. Only confirmed `npm` or `winget` sources go directly to npm.

**Benefits:**
- Resolves Node.js v25+ compatibility issues (bug #9628)
- Eliminates Node.js dependency for most users
- More reliable auto-updates via official Anthropic installers
- Maintains full backward compatibility with existing npm installations

### Node.js Compatibility Check Parameter

The `ensure_nodejs()` function accepts a `check_claude_compat` parameter:

| Parameter                   | Default | Behavior                                                             |
|-----------------------------|---------|----------------------------------------------------------------------|
| `check_claude_compat=True`  | Yes     | Checks Node.js v25+ SlowBuffer incompatibility (for npm Claude Code) |
| `check_claude_compat=False` | No      | Only checks minimum version >= 18.0.0 (for general-purpose Node.js)  |

**Usage contexts:**
- `install_claude.py` main() calls `ensure_nodejs()` (default `True`) -- Claude Code npm runtime needs compatible Node.js
- `setup_environment.py` `install_nodejs_if_requested()` calls the standalone `_ensure_nodejs()` which checks only minimum version (>= 18.0.0) -- `install-nodejs: true` config needs Node.js for general purposes (MCP servers, npx tools), not for Claude Code itself

### Version-Aware Compatibility

The `check_nodejs_compatibility()` function supports version-aware checking via the `CLAUDE_NPM_SLOWBUFFER_FIXED_VERSION` constant:

| Constant Value | Behavior                                                                           |
|----------------|------------------------------------------------------------------------------------|
| `None`         | Node.js v25+ is always rejected for npm Claude Code (current default)              |
| Version string | Node.js v25+ is accepted if installed Claude Code npm version >= the fixed version |

The check works as follows:
- When Claude Code is installed, `get_claude_version()` detects the installed version
- If `CLAUDE_NPM_SLOWBUFFER_FIXED_VERSION` is set and the installed version meets the threshold, v25+ is accepted
- If the installed version is unknown or below the threshold, v25+ is rejected (conservative default)
- Monitor [GitHub issue #9628](https://github.com/anthropics/claude-code/issues/9628) for when this gets fixed

### Root Detection Guard

All Linux and macOS scripts (both bash bootstrap scripts and Python entry points) refuse to run as root/sudo by default:

- **Detection:** Checks `id -u == 0` (shell scripts) or `os.geteuid() == 0` (Python scripts)
- **Override:** Set `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1` to bypass the guard (only exact value `1` is accepted; `true`, `yes`, or empty strings do NOT work)
- **Scope:** Applies to all 6 entry points: `install-claude-linux.sh`, `setup-environment.sh` (both Linux and macOS), `install_claude.py`, and `setup_environment.py`
- **Rationale:** Running as root creates configuration under `/root/` instead of the regular user's home directory, causing environment setup to target the wrong user
- **When to use override:** Docker containers, CI/CD pipelines, or other legitimate root execution environments

### Installation Confirmation

The setup script requires explicit user confirmation before installing any resources. This prevents unintended installations from untrusted configurations.

**CLI Flags:**

- `--yes` / `-y`: Auto-confirm installation (skip interactive prompt)
- `--dry-run`: Show installation plan and exit without installing

**Environment Variable:**

- `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL=1`: Auto-confirm (only exact value `'1'` accepted)
- `CLAUDE_CODE_TOOLBOX_DRY_RUN=1`: Preview installation plan without changes (only exact value `'1'` accepted)

**Default Behavior:**

- Interactive terminal: Prompts user with `[y/N]` (default deny)
- Piped stdin with `/dev/tty` available: Prompts via `/dev/tty` (best-effort fallback)
- Non-interactive without `/dev/tty`: Refuses with guidance, exits 1

**Exit Codes:**

- `0`: Successful installation, `--dry-run`, or interactive user cancellation
- `1`: Errors or non-interactive refusal

**Bootstrap Scripts:**
All bootstrap scripts (`setup-environment.sh` for Linux/macOS, `setup-environment.ps1` for Windows) forward `--yes`, `--dry-run`, `--skip-install`, and `--no-admin` flags to the Python script. The `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL` environment variable propagates automatically via environment inheritance.

**Known Config Keys:**
The setup script validates config keys against `KNOWN_CONFIG_KEYS` constant. Unknown keys are flagged with `[?]` in the installation summary. When adding new config keys to `setup_environment.py`, remember to update `KNOWN_CONFIG_KEYS`.

**Sensitive Path Detection:**
Files-to-download destinations are checked against `SENSITIVE_PATH_PREFIXES`. Sensitive paths (e.g., `~/.ssh/`, `~/.bashrc`) are flagged with `[!]` in the installation summary.

### Environment Configuration System

YAML configurations define complete development environments including:
- Dependencies to install
- Agents (subagents for Claude Code)
- MCP servers (with automatic permission pre-allowing)
- Slash commands
- System prompts (with configurable mode: append or replace)
- Hooks (event-driven scripts)
- Global config (`~/.claude.json` settings via deep merge)

### Global Config (`global-config`)

The `global-config` YAML key writes settings to `~/.claude.json` (the Claude Code global configuration file at `Path.home() / '.claude.json'`).

**Merge strategy:** Uses `deep_merge_settings()` with `array_union_keys=set()` (no array union -- arrays are replaced, not unioned). This differs from `user-settings` which uses the default `DEFAULT_ARRAY_UNION_KEYS` for `permissions.allow/deny/ask` union behavior.

**Excluded keys:** Only `oauthAccount` is blocked from non-null values (via `GLOBAL_CONFIG_EXCLUDED_KEYS`). Setting `oauthAccount: null` is allowed to support clearing OAuth authentication state. Non-null OAuth credential values must not appear in version-controlled YAML configuration files.

**Relationship with `install_claude.py`:** The `update_install_method_config()` function in `install_claude.py` also writes to `~/.claude.json`. Both functions use a resilient read-merge-write pattern that preserves existing keys, ensuring they coexist without data loss. The `install_claude.py` function does not import from `setup_environment.py` (standalone script with different dependency chain).

**DRY infrastructure:** Both `write_user_settings()` and `write_global_config()` delegate to the shared `_write_merged_json()` helper that implements the READ-MERGE-WRITE pattern. This eliminates the previous code duplication.

**Null-as-delete (RFC 7396):** Setting a key to `null` in either `user-settings` or `global-config` deletes that key from the target JSON file. This applies to both `settings.json` and `~/.claude.json`. `_merge_recursive()` handles deletion during merge via `target.pop(key, None)` -- no post-merge cleanup is needed. Null inside arrays is NOT treated as deletion. Bare YAML keys (e.g., `key:` with no value) also produce Python `None` and trigger deletion -- users must use explicit `key: null` for intentional deletion and `key: ""` for empty strings. The `display_installation_summary()` shows `[DELETE]` markers in RED for null-valued keys in the dry-run summary, providing visibility into which keys will be removed.

### Platform-Conditional Tilde Expansion in Settings

The `_expand_tilde_keys_in_settings()` function handles tilde (`~`) paths differently based on the platform:

- **Windows:** Tildes are expanded to absolute paths (e.g., `~/.claude/scripts/file.py` becomes `C:\Users\user\.claude\scripts\file.py`). Windows shell does not resolve `~` in paths.
- **Linux/macOS/WSL:** Tildes are PRESERVED as-is. Claude Code resolves `~` to the correct home directory at runtime. This keeps paths portable across environments and avoids WSL HOME contamination.

**Affected settings keys** (defined in `TILDE_EXPANSION_KEYS`):

- `apiKeyHelper`
- `awsCredentialExport`

**WSL Detection:**

The `is_wsl()` utility function detects WSL by checking `/proc/version` for Microsoft/WSL indicators. When WSL is detected, the setup emits a warning if settings contain expanded Windows paths.

**Why tildes are preserved on Linux/WSL:**

On WSL, `os.path.expanduser('~')` can return a contaminated Windows home directory (e.g., `C:\Users\user`) instead of the Linux home (e.g., `/home/user`). The `normalize_tilde_path()` function uses `Path.home()` instead of `os.path.expanduser()` to avoid this contamination, but the safest approach on non-Windows platforms is to preserve tildes entirely and let the runtime resolve them.

### Cross-Shell Command Registration (Windows)

The setup creates global commands (e.g., `claude-python`) that work across all Windows shells through:
- Shared POSIX script (`~/.claude/launch-{command}.sh`) executed by Git Bash
- PowerShell wrapper (`~/.local/bin/{command}.ps1`)
- CMD wrapper (`~/.local/bin/{command}.cmd`)
- Git Bash wrapper (`~/.local/bin/{command}`)

### Validation Models

The repository includes a Pydantic validation model for environment YAML configurations.

**Model location:** `scripts/models/environment_config.py`

**Purpose:** Provides a Pydantic schema (`EnvironmentConfig`) that defines the complete structure and types for environment YAML configurations. The model validates field names, types, and constraints for all supported configuration keys.

**Canonical source:** This repository (claude-code-toolbox) is the authoritative home for the model. Changes to the model are made here and synced to downstream repositories via the sync mechanism described below.

**Maintenance rule:** When adding new config keys to `setup_environment.py` (by extending `KNOWN_CONFIG_KEYS`), the `EnvironmentConfig` model in `scripts/models/environment_config.py` MUST be updated simultaneously with the corresponding field definition (and vice versa). The parity test enforces this at CI time.

**KNOWN_CONFIG_KEYS alignment:** The test `tests/scripts/models/test_known_config_keys_parity.py` enforces a STRICT BIDIRECTIONAL match between `KNOWN_CONFIG_KEYS` in `setup_environment.py` and `EnvironmentConfig.model_fields`. There are ZERO exceptions -- every key must exist in both places, and every model field must have a corresponding `KNOWN_CONFIG_KEYS` entry.

**Deprecated keys policy:** Deprecated configuration keys must be DELETED from both `KNOWN_CONFIG_KEYS` and the model, not kept with exceptions or backward compatibility shims. The parity test will fail if a key exists in one place but not the other.

**Test location:** `tests/scripts/models/` contains:

- `test_environment_config.py` -- model field validation, type checking, edge cases
- `test_mcp_server_scope.py` -- MCP server configuration scope validation
- `test_known_config_keys_parity.py` -- strict bidirectional parity enforcement

**Sync mechanism:** The `.github/` directory contains the sync infrastructure:

- `sync_to_repos.py` -- script that pushes model changes to target repositories
- `sync_config.py` -- Pydantic model for sync configuration
- `sync-config.yaml` -- configuration defining target repos and file mappings
- The workflow `.github/workflows/sync-to-repos.yml` triggers on changes to `scripts/models/environment_config.py` and syncs to `alex-feel/claude-code-artifacts` and `alex-feel/claude-code-artifacts-public`, placing the model at `.github/environment_config.py` in each target

**Runtime integration status:** The model is NOT imported or used at runtime in `setup_environment.py`. The `KNOWN_CONFIG_KEYS` frozenset is the active runtime mechanism for unknown-key detection. The model serves as a schema definition for CI validation and documentation, and the parity test ensures the two stay permanently synchronized.

**UserSettings policy:** The `UserSettings` class is a free-form open model (`extra='allow'`) with ZERO hardcoded fields. It passes through all user-provided settings to `settings.json` without field-level validation. The only structural guard is a blocklist validator (`check_excluded_keys`) that prevents `hooks` and `statusLine` keys from appearing in user-settings (these are profile-specific and must be configured at the root level of the environment YAML).

## Documentation Maintenance

When changing validation models or other core functionality, review and update the relevant documentation:

- **`docs/environment-configuration-guide.md`** -- Update when:
  - `KNOWN_CONFIG_KEYS` or `EnvironmentConfig` model changes (new, renamed, or removed config keys)
  - MCP server transport types, scope options, or permission behavior changes
  - Hooks structure, event types, or file consistency rules change
  - `command-defaults` modes or system prompt behavior changes
  - Environment variable handling or authentication flow changes

- **`docs/installing-claude-code.md`** -- Update when:
  - Installation methods or upgrade behavior changes
  - `install_claude.py` functions or environment variables change
  - Node.js compatibility checks or version detection changes
  - Root guard behavior or sudo handling changes

**Trigger review checklist:**
1. Did you add/remove/rename any config keys in `setup_environment.py`?
2. Did you modify `scripts/models/environment_config.py`?
3. Did you change how `install_claude.py` detects installation sources or handles upgrades?
4. Did you add new environment variables or change their behavior?

If any answer is yes, check the corresponding doc file and update it before committing.

## Development Commands

### Testing Commands

**CRITICAL: ALWAYS run the full test suite after making ANY changes. All tests must pass (100% pass rate). Never skip the test suite.**

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=scripts

# Run specific test files
uv run pytest tests/test_setup_environment.py
uv run pytest tests/test_install_claude.py

# Run tests matching a pattern
uv run pytest -k "test_colors"

# Run tests with verbose output
uv run pytest -v
```

**Mandatory workflow after code changes:**
1. Make your code changes
2. Run `uv run pytest` to check all tests pass
3. Fix any failing tests immediately
4. Run `uv run pre-commit run --all-files` for code quality validation
5. Only commit when ALL tests pass and all pre-commit hooks pass

### E2E Testing

The project includes a comprehensive End-to-End (E2E) testing framework that verifies the complete setup workflow on all platforms.

#### Key Files

- `tests/e2e/conftest.py` -- E2E fixtures (`isolated_home`, `golden_config`, `mock_repo_path`)
- `tests/e2e/golden_config.yaml` -- Comprehensive config exercising ALL supported YAML keys
- `tests/e2e/validators.py` -- Composable validation functions
- `tests/e2e/expected/` -- Platform-specific expected outputs (linux, macOS, windows)
- `tests/e2e/fixtures/mock_repo/` -- Mock source files (agents, commands, hooks, prompts, skills)

#### Running E2E Tests

```bash
# Run all E2E tests
uv run pytest tests/e2e/ -v

# Run E2E tests with detailed output
uv run pytest tests/e2e/ -v --tb=long

# Run specific E2E test module
uv run pytest tests/e2e/test_output_files.py -v

# Run E2E tests matching a pattern
uv run pytest tests/e2e/ -k "test_launcher" -v
```

#### Golden Configuration Purpose

The `tests/e2e/golden_config.yaml` is a comprehensive configuration file that includes ALL supported YAML keys. It serves as the single source of truth for testing (exercises every option), regression prevention (all platforms), and documentation by example. Open the file directly to see all supported configuration keys.

#### Key Design Principles

- **Complete isolation**: Tests use `tmp_path` and monkeypatched home directories
- **Function-scoped fixtures**: Each test starts with a clean state
- **Composable validators**: Return all errors, not just the first
- **Platform-specific expectations**: Separate modules for Linux, macOS, Windows
- **CI cleanup verification**: Dedicated step verifies no artifacts leak to real home

### Code Quality & Linting

**CRITICAL: Always use pre-commit for code quality checks. DO NOT use `ruff format` directly.**

```bash
# Run all pre-commit hooks (this is the CORRECT way to validate code)
uv run pre-commit run --all-files

# Run specific pre-commit hooks
uv run pre-commit run ruff-check       # Linting + autofix
uv run pre-commit run mypy             # Type checking
uv run pre-commit run pyright          # Additional type checking
uv run pre-commit run shellcheck       # Shell script linting
uv run pre-commit run markdownlint     # Markdown linting
uv run pre-commit run psscriptanalyzer # PowerShell linting (Windows only)
```

**Pre-commit hooks automatically handle:**
- Ruff linting with `--fix` for auto-correction
- MyPy type checking
- Pyright type checking
- PSScriptAnalyzer for PowerShell scripts (Windows)
- Shellcheck for shell scripts
- JSON/YAML syntax validation
- End-of-file and trailing whitespace fixes
- Markdown linting
- Commitizen for commit message validation

## E2E Testing Requirements for New Features

**Any new functionality MUST include E2E tests.** This is a mandatory requirement.

### When to Add E2E Tests

E2E tests are required when adding:
- New YAML configuration keys to `setup_environment.py`
- New file types or download mechanisms
- New launcher script functionality
- New MCP server transport types
- Changes to output file structures (JSON files, scripts)
- New hooks or event types

### How to Add E2E Tests for New Features

1. **Update `tests/e2e/golden_config.yaml`** - Add the new configuration key with representative test values. This file must contain ALL supported YAML keys.

2. **Update mock repository if needed** - Add mock files to `tests/e2e/fixtures/mock_repo/` for new file types.

3. **Update validators** - Add validation logic to `tests/e2e/validators.py` for new JSON structures or file content.

4. **Update expected outputs** - Modify platform-specific expectations in `tests/e2e/expected/` if the feature generates platform-dependent output.

5. **Add targeted tests** - Create or update test modules in `tests/e2e/` for specific feature validation.

### E2E Test Pattern

```python
def test_new_feature(e2e_isolated_home: dict[str, Path], golden_config: dict[str, Any]) -> None:
    """Test description."""
    # 1. Get relevant paths from fixture
    claude_dir = e2e_isolated_home['claude_dir']

    # 2. Run setup with golden config (or specific test config)
    # 3. Validate outputs using composable validators
    errors = validate_new_feature(output_path, golden_config)

    # 4. Assert no errors (fail with all errors, not just first)
    assert not errors, '\n'.join(errors)
```

### Validator Design Rules

- Return `list[str]` of errors (empty = success)
- Collect ALL errors, not just the first one
- Include context in error messages (file path, field name, expected vs actual)
- Use helper functions for reusable validation patterns

## Commit Conventions

This repository uses Conventional Commits (enforced by commitizen):
- `feat:` - New features (minor version bump)
- `fix:` - Bug fixes (patch version bump)
- `chore:` - Maintenance tasks (no version bump)
- `docs:` - Documentation improvements
- `ci:` - CI/CD changes
- `test:` - Test-related changes

Breaking changes: Add `!` after type or include `BREAKING CHANGE:` in body

## Pull Request Guidelines

### PR Title Format
- **DO NOT use Conventional Commit format in PR titles** (no `feat:`, `fix:`, etc.)
- Use clear, descriptive titles that explain the overall change
- When PR contains multiple unrelated commits, use a comprehensive title like:
  - "Update documentation and fix validation workflow"
  - "Refactor components and add badge system"
  - "Multiple improvements to environment configuration"

### Why No Conventional Commits in PR Titles
- PRs often contain multiple commits with different types
- PR titles should describe the overall change, not individual commits
- Individual commits within the PR should follow Conventional Commit format
- Release Please uses commit messages, not PR titles, for versioning

## Critical Implementation Details

### Configuration Loading Priority (setup_environment.py)

The `load_config_from_source()` function determines source by checking in order:
1. URL detection: Starts with `http://` or `https://`
2. Local file: Contains path separators (`/`, `\`) or starts with `.`
3. Repository config: Everything else (name only, `.yaml` added if missing)

For private repository access:
- GitLab: Set `GITLAB_TOKEN` environment variable with PAT (Personal Access Token)
- GitHub: Set `GITHUB_TOKEN` environment variable with PAT
- Script auto-detects GitLab/GitHub URLs and applies appropriate authentication headers

### MCP Server Permissions

When configuring MCP servers, permissions are automatically added to `settings.json`:
```json
{
  "permissions": {
    "allow": ["mcp__servername"]
  }
}
```

### Environment Variables for Debugging

The setup scripts support these environment variables for debugging and customization:

- `CLAUDE_CODE_TOOLBOX_DEBUG`: Set to `1`, `true`, or `yes` to enable verbose debug logging during MCP server configuration and other operations
- `CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH`: Override the Git Bash executable path (useful for non-standard installations where Git Bash is not in the default location)
- `CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS`: Override the number of concurrent download workers (default: 2)
- `CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE`: Set to `1`, `true`, or `yes` to disable parallel downloads entirely
- `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT`: Set to `1` to allow running as root on Linux/macOS (see Root Detection Guard section)
- `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL`: Set to `1` to auto-confirm installation (see Installation Confirmation section)
- `CLAUDE_CODE_TOOLBOX_DRY_RUN`: Set to `1` to preview installation plan without changes (parity with `--dry-run` CLI flag; exact value `'1'` only)

### npm Sudo Handling (Three-Tier Fallback)

When `install_claude_npm()` or `remove_npm_claude()` needs elevated permissions for global npm operations, both functions delegate to the shared `_run_with_sudo_fallback()` helper which implements a three-tier strategy:

1. **Tier 1 -- Interactive mode** (`sys.stdin.isatty()` is True): Sudo is attempted directly (user can enter password via stdin)
2. **Tier 2 -- Cached credentials** (non-interactive): Runs `sudo -n true` to check for cached sudo credentials. If cached credentials exist, sudo is attempted without prompting
3. **Tier 3 -- `/dev/tty` fallback** (non-interactive with terminal): If Tiers 1 and 2 fail but `/dev/tty` is available (checked via `_dev_tty_sudo_available()`), sudo is invoked with stdin redirected from `/dev/tty`, allowing the user to type their password even in piped mode (`curl | bash`)

If all three tiers are exhausted, `_run_with_sudo_fallback()` returns `None` and the caller provides guidance text. `FileNotFoundError` (missing sudo binary) and `subprocess.TimeoutExpired` are caught gracefully at each tier. The `/dev/tty` tier uses a longer timeout (`tty_timeout=60`) to give the user time to type their password.

This pattern is applied consistently to both `install_claude_npm()` and `remove_npm_claude()` via the shared helper, eliminating the previous code duplication. The `remove_npm_claude()` function also captures npm output to suppress noisy error stack traces from reaching the user's terminal.

### Download Retry Configuration

The setup scripts include robust retry logic for handling GitHub API rate limiting:

- **Retry attempts:** 10 (with linear additive backoff)
- **Base delay:** 1 second for the first retry
- **Additive increment:** +2 seconds per subsequent attempt (sequence: 1s, 3s, 5s, 7s, ...)
- **Maximum delay cap:** 60 seconds per retry (before jitter)
- **Jitter:** Random 0-25% added to all retries to prevent synchronized requests
- **Stagger delay:** 0.5 second delay between launching concurrent download threads
- **Cross-thread coordination:** `RateLimitCoordinator` shares rate-limit state across threads
- **Header respect:** `Retry-After` and `x-ratelimit-reset` headers used as minimum floor

### Hooks Configuration Structure

Hooks use this structure in environment YAML:
```yaml
hooks:
    files:  # Top-level list of files to download
        - my-hooks/linter.py
    events:  # Event configurations
        - event: PostToolUse
          matcher: Edit|MultiEdit|Write
          type: command
          command: linter.py  # References filename from 'files'
```

### System Prompt Configuration

The `command-defaults` section supports system prompt configuration with two modes:

```yaml
command-defaults:
  system-prompt: "prompts/my-prompt.md"  # Path to the system prompt file
  mode: "replace"  # Optional: "append" or "replace" (default: "replace")
```

**Mode Behavior:**
- **mode: "replace"** (default): Completely replaces the default system prompt using `--system-prompt` flag (added in Claude Code v2.0.14)
- **mode: "append"**: Appends to Claude's default development prompt using `--append-system-prompt` flag (added in Claude Code v1.0.55)

**Important:** If `mode` is not specified, it defaults to `"replace"` for a clean slate experience.

### Step Numbering Convention

Step comments and print statements in `main()` (e.g., `# Step N:`, `Step N: ...`) **MUST** use only whole integers. The sequence must be continuous with no gaps: Step 1, Step 2, ..., Step N.

**Rules:**
- Fractional/decimal step numbers (e.g., `Step 14.5`, `Step 3.1`) are **PROHIBITED**
- When inserting a new step between existing steps, **renumber all subsequent steps** to maintain a continuous integer sequence
- Update ALL references to renumbered steps (comments, print statements, test assertions, skip-range messages like `Steps 13-17`)

## Testing Workflows

### When modifying setup_environment.py
1. Test with local file: Create test YAML, run with `./test.yaml`
2. Test with remote URL to verify warning messages appear
3. Verify global command registration works
4. Verify settings.json structure
5. Check that hooks execute properly after setup

### When creating custom environment configs
1. Create your YAML configuration file
2. Test local installation flow with your config
3. Verify all referenced files are accessible
4. Verify settings.json structure is correct:
   - `~/.config/claude/settings.json` on Linux/macOS
   - `%LOCALAPPDATA%\Claude\settings.json` on Windows
5. Ensure hooks trigger correctly

### Mock Target Alignment Rule

When production code is refactored to change which function a call site uses (e.g., replacing `find_command('node')` with `shutil.which('node')`), ALL test mocks that target the old function MUST be updated to target the new function. Stale mock targets cause tests to pass locally but fail on CI.

Key patterns to verify:
- `@patch('module.find_command')` -- confirm the production code still calls `find_command()` at that call site
- `@patch('shutil.which')` -- confirm the production code actually calls `shutil.which()` at the mocked call site
- When `shutil.which` replaces `find_command`, mock `Path.exists()` to return `False` for common-path checks that precede the `shutil.which` fallback

### Platform-Specific Path Behavior in Tests

Tests that create or assert on Windows-style paths (using backslashes) MUST be marked as Windows-only:

```python
@pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific path test')
```

`Path(r'C:\Program Files\nodejs\node.exe')` on Linux becomes `PosixPath('C:\\Program Files\\nodejs\\node.exe')` (a single path component), so `Path(...).parent` returns `PosixPath('.')` instead of the expected Windows parent directory. `Path` uses the running OS's path semantics, not the path's apparent format.

### Platform Detection Mock Completeness Rule

When production code uses platform detection (`sys.platform`, `platform.system()`, or both), tests MUST mock ALL platform detection methods used in the complete code path under test, not just one.

**The trap:** A test mocks `platform.system()` to simulate Windows, but the same function also checks `sys.platform` (or vice versa). The test passes on the simulated platform (e.g., Windows CI where `sys.platform` is already `'win32'`) but fails on other CI platforms where the un-mocked check evaluates differently.

**Rules:**
1. Before writing a platform-simulation test, read the COMPLETE production function and identify ALL platform checks (`sys.platform`, `platform.system()`, `os.name`, etc.)
2. Mock ALL of them consistently for the simulated platform
3. Prefer using ONE platform detection method per function. `sys.platform` is preferred for MyPy compatibility (see "Platform-Specific Code Patterns" section)
4. When refactoring production code to change platform detection method, update ALL test mocks targeting that function

**Quick reference -- equivalent values:**

| Simulated Platform | `sys.platform` | `platform.system()` | `os.name` |
|--------------------|----------------|---------------------|-----------|
| Windows            | `'win32'`      | `'Windows'`         | `'nt'`    |
| Linux              | `'linux'`      | `'Linux'`           | `'posix'` |
| macOS              | `'darwin'`     | `'Darwin'`          | `'posix'` |

## Script Dependencies

- **Python 3.12** required for all Python scripts
- **uv** (Astral's package manager) installed automatically by bootstrap scripts
- **PyYAML** and **Pydantic** installed as project dependencies
- **pytest**, **ruff**, **pre-commit** installed as dev dependencies

## Version Management

- DO NOT manually edit `CHANGELOG.md`, `version.txt`, or `.release-please-manifest.json`
- Release Please automatically manages versioning based on conventional commits
- Version bumps happen when release PRs are merged

### SECURITY.md Maintenance

When creating any commit that triggers a major version bump, SECURITY.md **must** be updated in the same PR:
- Any commit type with `!` suffix: `feat!:`, `fix!:`, `refactor!:`, `chore!:`, etc.
- Any commit with `BREAKING CHANGE:` in the body or footer

Update the "Supported Versions" table to reflect the new major version as the only supported version:

```markdown
| Version | Supported          |
|---------|--------------------|
| X.x     | :white_check_mark: |
| < X.0   | :x:                |
```

## Security Considerations

When loading environment configurations:
- Repository configs are trusted (reviewed by maintainers)
- Local files are under user control (can contain API keys)
- Remote URLs show warning messages (verify source first)
- Never commit configurations with sensitive data to the repo

### GitHub Actions Security Policy

When adding or updating GitHub Actions in workflow files (`.github/workflows/*.yml`):

1. **NEVER use mutable branch references** (`@main`, `@master`, `@develop`) for third-party actions
   - Mutable references allow upstream supply chain attacks (e.g., the [trivy-action incident of March 2026](https://www.wiz.io/blog/trivy-compromised-teampcp-supply-chain-attack))
   - Always pin to immutable version tags: `@v5`, `@v0.35.0`, etc.
   - First-party GitHub actions (`actions/*`, `github/*`) and composite/docker actions may use major version tags (`@v5`)

2. **Version tag pinning** is the project standard (not SHA pinning)
   - Version tags balance security with maintainability
   - SHA pinning is disproportionate overhead for this project's threat model

3. **Verify action runtimes** before updating to ensure Node.js 24 compatibility:
   ```bash
   # Check the runtime of an action at a specific tag
   gh api repos/{owner}/{repo}/contents/action.yml?ref={tag} \
     --jq '.content' | base64 -d | grep -A1 "^runs:"
   ```
   - `node24` -- compatible, preferred
   - `composite` or `docker` -- node-agnostic, always compatible
   - `node20` -- deprecated, will stop working after June 2, 2026
   - Note: some actions use `action.yaml` instead of `action.yml`

## Platform-Specific Code Patterns (MyPy)

**CRITICAL:** MyPy on Linux CI analyzes platform checks differently than on Windows locally. Negative checks with early returns cause "unreachable code" errors in CI even though the code runs fine on Windows. MyPy may pass locally but fail in CI on the same code.

**Always use positive platform checks:**

```python
# CORRECT: Use positive platform check (MyPy-friendly)
def windows_specific_function() -> ReturnType:
    if sys.platform == 'win32':
        # All Windows-specific logic inside this block
        # (e.g., add_directory_to_windows_path(), cleanup_temp_paths_from_registry())
        return windows_result
    # Non-Windows platforms
    return default_value

# INCORRECT: Causes MyPy "unreachable" errors on Linux CI
def windows_specific_function() -> ReturnType:
    if sys.platform != 'win32':
        return default_value  # MyPy on Linux CI considers code after this unreachable
    # ...
```

Test with `uv run mypy scripts/` before pushing. Expect CI to catch issues local testing might miss.
