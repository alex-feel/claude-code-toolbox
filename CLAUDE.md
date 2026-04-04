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
   - `scripts/setup_environment.py`: Configuration-driven environment setup from YAML (sources: repo name, local file path, or remote URL)

### Native Claude Code Installation Support

The installer uses a native-first approach with automatic npm fallback. Entry point: `ensure_claude()` → `install_claude_native_cross_platform()` → platform-specific `install_claude_native_{windows,macos,linux}()`.

### Standalone Script Policy

`install_claude.py` and `setup_environment.py` MUST be fully standalone -- NEVER import from each other. Users may run either script without the other being present.

**Identical Code** (CI enforced via `tests/test_standalone_policy.py`): `Colors` class, `find_command()`, `get_real_user_home()` (EXACT body match), shell config file list (7 files + conditional filtering), Fish config detection (`'fish' in str()`), marker block constants (`# >>> claude-code-toolbox >>>`).

**Intentionally Different** (MUST NOT synchronize): `info()`/`success()`/`warning()`/`error()` (different formatting), `run_command()` (different encoding/error handling), `find_bash_windows()` (setup_environment.py has debug_log), `is_admin()` (different implementations).

**Native Path Priority:** `find_command()` and `verify_claude_installation()` check the native path (`~/.local/bin/claude[.exe]`) first, before `shutil.which()` PATH search. This ensures native binary is preferred even when PATH would resolve to npm first. Validates file exists with `st_size > 1000` to skip empty/corrupt files.

**Environment Variables:** `CLAUDE_CODE_TOOLBOX_INSTALL_METHOD` (`auto`/`native`/`npm`, default `auto` -- unknown sources → native-first with npm fallback), `CLAUDE_CODE_TOOLBOX_VERSION` (installs a specific Claude Code version; works with both native via GCS download and npm methods), `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT` (`1` only -- see Root Detection Guard).

**Native Path Detection (Non-Windows):** `verify_claude_installation()` classifies the binary location for upgrade strategy:

| Path Pattern                           | Source    | Upgrade Method             |
|----------------------------------------|-----------|----------------------------|
| Contains `npm` or `.npm-global`        | `npm`     | npm directly               |
| Contains `.local/bin` or `.claude/bin` | `native`  | Native installer           |
| Other / `/usr/local/bin`               | `unknown` | Native-first, npm fallback |
| Not found                              | `none`    | Fresh install              |

In `auto` mode, `native` and `unknown` sources attempt native first with npm fallback. Only confirmed `npm`/`winget` sources go directly to npm.

### Node.js Compatibility

`ensure_nodejs(check_claude_compat=True)` checks Node.js v25+ SlowBuffer incompatibility for npm Claude Code; `False` checks only minimum >= 18.0.0. `install_claude.py` uses `True`; `setup_environment.py` uses `False` (needs Node.js for MCP servers/npx, not Claude Code).

`CLAUDE_NPM_SLOWBUFFER_FIXED_VERSION`: when `None` (default), v25+ always rejected; when set to a version string, v25+ accepted if installed Claude Code npm version meets threshold. Monitor [#9628](https://github.com/anthropics/claude-code/issues/9628).

### Root Detection Guard

All Linux/macOS scripts refuse to run as root/sudo by default (`id -u == 0` in shell, `os.geteuid() == 0` in Python). Applies to all 6 entry points. Override: `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1` (only exact value `1`; `true`/`yes` do NOT work). Rationale: root creates config under `/root/` instead of user's home. Use override for Docker/CI environments.

### Installation Confirmation

The setup script requires explicit user confirmation before installing. CLI flags: `--yes`/`-y` (auto-confirm), `--dry-run` (preview and exit). Env vars: `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL=1` (auto-confirm), `CLAUDE_CODE_TOOLBOX_DRY_RUN=1` (preview). Both accept only exact value `'1'`.

**Default:** Interactive → `[y/N]` prompt (deny default). Piped with `/dev/tty` → prompts via tty. Non-interactive → refuses (exit 1). Exit `0` for success/dry-run/cancellation, `1` for errors. Bootstrap scripts forward `--yes`, `--dry-run`, `--skip-install`, `--no-admin` to Python.

**Known Config Keys:** The setup script validates config keys against `KNOWN_CONFIG_KEYS` constant. Unknown keys are flagged with `[?]` in the installation summary. When adding new config keys to `setup_environment.py`, remember to update `KNOWN_CONFIG_KEYS`.

**Sensitive Path Detection:** Files-to-download destinations are checked against `SENSITIVE_PATH_PREFIXES`. Sensitive paths (e.g., `~/.ssh/`, `~/.bashrc`) are flagged with `[!]` in the installation summary.

### Environment Configuration System

YAML configs define complete environments: dependencies, agents, MCP servers (auto-permission), slash commands, system prompts (append/replace modes), hooks, global config (`~/.claude.json` via deep merge), and selective inheritance via `merge-keys` directive.

**Env Loader Files:** `generate_env_loader_files()` creates Rustup-style shell scripts containing ONLY `os-env-variables` (not `env-variables`). Per-command files: `~/.claude/{cmd}/env.sh`, `env.fish` (if Fish installed), `env.ps1` (Windows), `env.cmd` (Windows). Global files: `~/.claude/toolbox-env.sh`, `toolbox-env.fish`, `toolbox-env.ps1` (Windows), `toolbox-env.cmd` (Windows). `None`-valued (deletion) vars are excluded. `create_launcher_script()` injects guarded source lines in all 6 launcher variants so commands auto-load env vars.

**Fish Dual-Mechanism:** `set_os_env_variable_unix()` writes `set -gx` to `config.fish` (durable persistence) AND calls `set -Ux` via subprocess (instant propagation to all running Fish sessions). For deletions, `set -Ue` removes the universal variable. The `config.fish` write is authoritative; `set -Ux` is complementary.

**WM_SETTINGCHANGE Broadcast:** `_broadcast_wm_settingchange()` in `setup_environment.py` uses the dummy `setx CLAUDE_CODE_TOOLBOX_TEMP temp` + `reg delete` pattern to trigger `WM_SETTINGCHANGE`. Called from `add_directory_to_windows_path()`, `cleanup_temp_paths_from_registry()`, `set_os_env_variable_windows()` (after `reg delete` for deletions), and `set_all_os_env_variables()` (batch broadcast after all operations). `install_claude.py` has its own independent copy at `ensure_local_bin_in_path_windows()` (standalone script policy).

### Global Config (`global-config`)

Writes to `~/.claude.json`. When `command-names` is present, dual-writes to BOTH `~/.claude.json` (machine baseline for bare `claude` sessions) AND `~/.claude/{cmd}/.claude.json` (for isolated sessions, since Claude Code CLI resolves `getGlobalClaudeFile()` via `CLAUDE_CONFIG_DIR` with no fallback). Content is identical in both files. Merge: `deep_merge_settings()` with `array_union_keys=set()` (arrays replaced, not unioned -- differs from `user-settings` which unions `permissions.allow/deny/ask`). Only `oauthAccount` blocked from non-null values (`GLOBAL_CONFIG_EXCLUDED_KEYS`); `null` allowed for clearing OAuth. `install_claude.py`'s `update_install_method_config()` also writes to `~/.claude.json` via the same pattern. Both `write_user_settings()` and `write_global_config()` delegate to `_write_merged_json()`.

**Asymmetric write strategy:** `.claude.json` uses dual-write (global semantics, bare sessions need it). `settings.json` uses single-write with scope-based routing (environment-specific semantics, dual-write would cause cross-environment contamination). Root cause: CLI resolves `.claude.json` via `getGlobalClaudeFile()` using `homedir()` as base, while `settings.json` is resolved via `getClaudeConfigHomeDir()` using `join(homedir(), '.claude')` as base. Neither has fallback or inheritance.

**Null-as-delete (RFC 7396):** `null` values in `user-settings`/`global-config` delete the key from the target JSON. `_merge_recursive()` handles via `target.pop(key, None)`. Null in arrays is NOT deletion. Bare YAML keys (`key:` with no value) also trigger deletion -- use `key: ""` for empty strings. Dry-run shows `[DELETE]` markers in RED.

### Two-File Architecture for Command Environments

When `command-names` is specified, the setup creates an isolated directory `~/.claude/{cmd}/` containing two configuration files loaded by Claude Code at different priority levels:

| File             | Priority         | Content                                                                                        | Write Mechanism                                |
|------------------|------------------|------------------------------------------------------------------------------------------------|------------------------------------------------|
| `settings.json`  | 5 (userSettings) | YAML `user-settings`                                                                           | Deep merge via `write_user_settings()`         |
| `config.json`    | 2 (flagSettings) | Hooks, env vars, permissions, model, MCP permissions, statusLine, attribution, effortLevel     | Atomic write via `create_profile_config()`     |

Scope-based routing: `command-names` presence in the final resolved config determines the SINGLE write target for `write_user_settings()`. Present: `~/.claude/{cmd}/settings.json`. Absent: `~/.claude/settings.json`. Never dual-write.

The launcher (`launch.sh`) passes `config.json` via `--settings` flag and sets `export CLAUDE_CONFIG_DIR` to the isolated directory.

### Platform-Conditional Tilde Expansion in Settings

`_expand_tilde_keys_in_settings()` handles tilde (`~`) paths in settings keys defined in `TILDE_EXPANSION_KEYS` (`apiKeyHelper`, `awsCredentialExport`):

- **Windows:** Tildes expanded to absolute paths (Windows shell doesn't resolve `~`)
- **Linux/macOS/WSL:** Tildes PRESERVED as-is (Claude Code resolves at runtime)

Preserved on non-Windows to avoid WSL HOME contamination (`os.path.expanduser('~')` on WSL can return Windows paths). `normalize_tilde_path()` uses `Path.home()` instead. `is_wsl()` detects WSL via `/proc/version` and warns about expanded Windows paths.

### Cross-Shell Command Registration (Windows)

Global commands (e.g., `claude-python`) work across all Windows shells: shared POSIX launcher (`~/.claude/{command}/launch.sh`) + wrappers for PowerShell (`start.ps1`), CMD (`start.cmd`) in the same directory, and global entry points in `~/.local/bin/`.

### Validation Models

Pydantic schema `EnvironmentConfig` in `scripts/models/environment_config.py` defines the complete structure for environment YAML configurations. This repository is the canonical source; changes are synced to downstream repos.

**KNOWN_CONFIG_KEYS parity rule:** When adding new config keys to `setup_environment.py` (extending `KNOWN_CONFIG_KEYS`), the `EnvironmentConfig` model MUST be updated simultaneously (and vice versa). `tests/scripts/models/test_known_config_keys_parity.py` enforces STRICT BIDIRECTIONAL match with ZERO exceptions. Deprecated keys must be DELETED from both, not kept with backward compatibility shims.

**Tests:** `tests/scripts/models/` -- `test_environment_config.py`, `test_mcp_server_scope.py`, `test_known_config_keys_parity.py`.

**Sync & Runtime:** `.github/workflows/sync-to-repos.yml` syncs model changes to `alex-feel/claude-code-artifacts{,-public}` at `.github/environment_config.py`. The model is NOT imported at runtime -- `KNOWN_CONFIG_KEYS` is the active runtime mechanism.

**UserSettings:** Free-form open model (`extra='allow'`, ZERO hardcoded fields). Only guard: `check_excluded_keys` blocks `hooks`/`statusLine` (profile-specific, must be at environment YAML root level).

## Documentation Maintenance

When changing core functionality, update the corresponding doc before committing:

- **`README.md`** -- Update when adding, changing, or removing user-facing features. The README is the first thing users read; its Features list and example YAML must reflect current capabilities.
- **`docs/environment-configuration-guide.md`** -- Update when changing: `KNOWN_CONFIG_KEYS`/`EnvironmentConfig` model, MCP server transports/scope/permissions, hooks structure/event types/file consistency, `command-defaults`/system prompt modes, environment variable handling
- **`docs/installing-claude-code.md`** -- Update when changing: installation/upgrade methods, `install_claude.py` functions/env vars, Node.js compatibility checks, root guard/sudo handling

## Development Commands

### Testing Commands

**CRITICAL: ALWAYS run the full test suite after making ANY changes. All tests must pass (100% pass rate). Never skip the test suite.**

```bash
uv run pytest                                  # Run all tests
uv run pytest --cov=scripts                    # With coverage report
uv run pytest tests/test_setup_environment.py  # Specific test file
uv run pytest -k "test_colors"                 # Pattern matching
uv run pytest -v                               # Verbose output
```

**Mandatory workflow:** Make changes → `uv run pytest` (all must pass) → `uv run pre-commit run --all-files` → only then commit.

### E2E Testing

E2E tests verify the complete setup workflow on all platforms. **Any new functionality MUST include E2E tests.** Key files: `tests/e2e/conftest.py` (fixtures), `tests/e2e/golden_config.yaml` (ALL supported YAML keys -- single source of truth), `tests/e2e/validators.py` (composable validators), `tests/e2e/expected/` (platform-specific), `tests/e2e/fixtures/mock_repo/` (mock source files).

```bash
uv run pytest tests/e2e/ -v                        # Run all E2E tests
uv run pytest tests/e2e/ -v --tb=long              # With detailed output
uv run pytest tests/e2e/test_output_files.py -v    # Specific module
uv run pytest tests/e2e/ -k "test_launcher" -v     # Pattern matching
```

**Design:** Complete isolation via `tmp_path` + monkeypatched home (function-scoped). Composable validators return ALL errors. Platform-specific expectations in separate modules. CI cleanup verifies no artifacts leak.

**Adding tests for new features** (required for: new config keys, file types, MCP transports, output structures, hooks): (1) Update `golden_config.yaml` (must contain ALL keys), (2) add mock files to `fixtures/mock_repo/`, (3) add validators, (4) update `expected/` for platform-dependent output, (5) create test modules. Validators return `list[str]` of ALL errors with context; assert via `assert not errors, '\n'.join(errors)`.

### Code Quality & Linting

**CRITICAL: Always use pre-commit for code quality checks. DO NOT use `ruff format` directly.**

```bash
uv run pre-commit run --all-files      # Run ALL hooks (the correct way)
uv run pre-commit run ruff-check       # Linting + autofix
uv run pre-commit run ty               # Type checking
uv run pre-commit run shellcheck       # Shell script linting
uv run pre-commit run markdownlint     # Markdown linting
uv run pre-commit run psscriptanalyzer # PowerShell linting (Windows only)
```

Pre-commit also automatically handles: JSON/YAML syntax validation, end-of-file and trailing whitespace fixes, commitizen commit message validation.

## Commit Conventions

Conventional Commits enforced by commitizen: `feat:` (minor bump), `fix:` (patch bump), `chore:`/`docs:`/`ci:`/`test:` (no bump). Breaking changes: add `!` after type or `BREAKING CHANGE:` in body.

## Pull Request Guidelines

**DO NOT use Conventional Commit format in PR titles** (no `feat:`, `fix:`, etc.). PR titles describe the overall change; individual commits follow Conventional Commit format. Release Please uses commit messages, not PR titles, for versioning.

## Critical Implementation Details

### Configuration Loading Priority (setup_environment.py)

`load_config_from_source()` determines source: (1) URL if starts with `http://`/`https://`, (2) local file if contains path separators or starts with `.`, (3) repository config otherwise (`.yaml` added if missing). Private repos: set `GITLAB_TOKEN` or `GITHUB_TOKEN` env var with PAT; script auto-detects and applies auth headers.

### MCP Server Permissions

MCP servers are automatically pre-allowed via `permissions.allow: ["mcp__servername"]` in the profile configuration (`config.json`). When `command-names` creates an isolated environment, `configure_mcp_server()` propagates `CLAUDE_CONFIG_DIR` to the subprocess for `scope: user` servers, ensuring they are written to the isolated `.claude.json`.

### Automatic Auto-Update Management

`setup_environment.py` automatically disables auto-updates when a specific Claude Code version is pinned via `claude-code-version` in YAML, and removes those controls when using latest/absent version. Manages 4 in-memory dict targets (`global-config`, `user-settings.env`, `env-variables`, `os-env-variables`) via `apply_auto_update_settings()`. WARN-but-Respect semantics: if the user explicitly sets a contradicting value in their YAML configuration (e.g., `autoUpdates: true` in `global-config` while pinning a version), the user value is preserved and a warning is emitted. The `[auto]` marker in the installation summary shows auto-injected values. Auto-update management is solely the responsibility of `setup_environment.py`; `install_claude.py` does not participate in auto-update configuration.

**Write-remove symmetry:** Auto-update controls are written to specific targets via scope-based routing, but removal must clean ALL filesystem locations unconditionally. `cleanup_stale_auto_update_controls()` runs as a post-write pass in `main()`, sweeping `~/.claude/settings.json`, all `~/.claude/*/settings.json`, `~/.claude.json`, and all `~/.claude/*/.claude.json`. Removal of `autoUpdates` is value-conditional: only `false` (auto-injected) is removed, `true` (user preference) is preserved.

**Target 2 null-as-delete:** `_remove_auto_update_controls()` Target 2 (`user_settings.env`) uses `env_section[key] = None` (not `del`) because `_write_merged_json()` -> `_merge_recursive()` requires `None` to trigger key deletion from the target file. Target 3 (`env_variables`) correctly uses `del` because `create_profile_config()` uses atomic overwrite, not merge.

### Environment Variables for Debugging

- `CLAUDE_CODE_TOOLBOX_DEBUG`: `1`/`true`/`yes` -- verbose debug logging
- `CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH`: Override Git Bash executable path
- `CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS`: Override concurrent download workers (default: 2)
- `CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE`: `1`/`true`/`yes` -- disable parallel downloads
- `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT`: `1` only -- allow root on Linux/macOS (see Root Detection Guard)
- `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL`: `1` only -- auto-confirm installation
- `CLAUDE_CODE_TOOLBOX_DRY_RUN`: `1` only -- preview installation plan without changes

### npm Sudo Handling (Three-Tier Fallback)

Both `install_claude_npm()` and `remove_npm_claude()` delegate to the shared `_run_with_sudo_fallback()` helper for elevated permissions:

1. **Tier 1 -- Interactive:** `sys.stdin.isatty()` → sudo directly (user enters password via stdin)
2. **Tier 2 -- Cached credentials:** `sudo -n true` probe → sudo without prompting if cached
3. **Tier 3 -- `/dev/tty` fallback:** `_dev_tty_sudo_available()` → sudo with stdin from `/dev/tty` (enables password entry in piped mode like `curl | bash`; uses `tty_timeout=60`)

If all tiers exhausted, returns `None` (caller provides guidance). Catches `FileNotFoundError`/`TimeoutExpired` at each tier. `remove_npm_claude()` captures npm output to suppress noisy stack traces.

### Download Retry Configuration

Retry logic for GitHub API rate limiting: 10 attempts with linear additive backoff (1s, 3s, 5s, 7s, ..., capped at 60s) plus random 0-25% jitter. Concurrent downloads use 0.5s stagger delay between threads. `RateLimitCoordinator` shares rate-limit state across threads. `Retry-After` and `x-ratelimit-reset` headers used as minimum floor.

### Hooks Configuration Structure

Hooks support four types matching the official Claude Code hooks specification:

| Type      | Required Field | Description                                        |
|-----------|----------------|----------------------------------------------------|
| `command` | `command`      | Executes a shell command or script (default)       |
| `http`    | `url`          | Sends an HTTP POST request                         |
| `prompt`  | `prompt`       | Single-turn LLM evaluation (no tool access)        |
| `agent`   | `prompt`       | Spawns a subagent with tool access for evaluation  |

Common fields available on all types: `if`, `status-message`, `once`, `timeout`.

Only `command` hooks reference files from `hooks.files`. Other types are pure pass-through. `_apply_common_hook_fields()` applies shared fields to all types.

```yaml
hooks:
    files: [my-hooks/linter.py]  # For command hooks only
    events:
        - {event: PostToolUse, matcher: "Edit|MultiEdit|Write", type: command, command: linter.py}
        - {event: PostToolUse, matcher: Write, type: http, url: "http://localhost:8080/hooks/write",
           headers: {Authorization: "Bearer $API_TOKEN"}, allowed-env-vars: [API_TOKEN]}
        - {event: PreToolUse, matcher: Bash, type: prompt, prompt: "Check if this bash command is safe"}
        - {event: PreToolUse, matcher: "Bash(rm *)", type: agent,
           prompt: "Verify security implications of: $ARGUMENTS", once: true}
```

Type-specific fields (setting a field on the wrong type produces a validation error):
- **command**: `command` (required), `config`, `async`, `shell`
- **http**: `url` (required), `headers`, `allowed-env-vars`
- **prompt/agent**: `prompt` (required), `model`

### Two-Layer Naming Convention (Sub-Keys)

Sub-keys in structured sections (`hooks.events[]`, `permissions`) use kebab-case in YAML and are translated to camelCase for Claude Code JSON output by the setup script. Sub-keys in free-form sections (`user-settings`, `global-config`) pass through as-is and must match Claude Code's native camelCase.

### System Prompt Configuration

```yaml
command-defaults:
  system-prompt: "prompts/my-prompt.md"
  mode: "replace"  # "replace" (default, --system-prompt) or "append" (--append-system-prompt)
```

### Step Numbering Convention

Step comments/print statements in `main()` MUST use continuous whole integers (no gaps, no fractions like `Step 14.5`). When inserting a new step, renumber all subsequent steps and update ALL references (comments, print statements, test assertions, skip-range messages).

## Testing Workflows

**Modifying setup_environment.py:** Test with local YAML (`./test.yaml`), remote URL (verify warnings), global command registration, settings.json structure, hooks execution.

**Custom configs:** Test installation flow, verify file accessibility, settings.json (`~/.config/claude/settings.json` on Linux/macOS, `%LOCALAPPDATA%\Claude\settings.json` on Windows), hooks.

### Testing Traps

**Mock target alignment:** When refactoring call sites (e.g., `find_command()` → `shutil.which()`), ALL test `@patch` targets MUST be updated. When `shutil.which` replaces `find_command`, also mock `Path.exists()` for common-path checks.

**Windows-style paths:** Tests with Windows paths MUST use `@pytest.mark.skipif(sys.platform != 'win32', ...)`. `Path(r'C:\...')` on Linux becomes a single component -- `Path` uses the running OS's semantics.

**Platform detection mocks:** Mock ALL detection methods (`sys.platform`, `platform.system()`, `os.name`) in the code path. Mocking only one passes on that platform's CI but fails on others. Prefer ONE method per function (`sys.platform` recommended).

| Platform | `sys.platform` | `platform.system()` | `os.name` |
|----------|----------------|---------------------|-----------|
| Windows  | `'win32'`      | `'Windows'`         | `'nt'`    |
| Linux    | `'linux'`      | `'Linux'`           | `'posix'` |
| macOS    | `'darwin'`     | `'Darwin'`          | `'posix'` |

### Agent Development Pitfalls

Recurring patterns that cause CI failures. Every item below has caused at least one real CI failure. Read this section before modifying `setup_environment.py` or its tests.

**Cross-platform test verification:** Local `uv run pytest` skips tests targeting other platforms (`@pytest.mark.skipif`). Developing on Windows means Unix-only tests are SKIPPED locally but WILL RUN in CI on Linux/macOS (and vice versa). A 100% local pass rate does NOT guarantee CI success. Before committing, review skipped tests to verify they would pass on their target platform. NEVER report a clean test run as definitive when platform-skipped tests exist.

**Tests must match implementation:** Every test assertion MUST correspond to actually implemented behavior. Do NOT write tests that assert behavior which has not been coded yet. If a test is for a new feature, implement the feature BEFORE or SIMULTANEOUSLY with the test. Tests that pass only because they are platform-skipped on the development machine will fail in CI on the target platform. This is the single most common cause of CI failures in this project.

**Parallel mock side effects:** Tests calling functions that use `execute_parallel()` (which uses `ThreadPoolExecutor`) MUST NOT use `mock.side_effect = [list]` with distinct values per item. The list is consumed in thread-scheduling order, not submission order. This causes non-deterministic failures depending on OS thread scheduling. Use either:

- `@patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE': '1'})` to force sequential execution in tests that verify logic (not parallelism)
- Function-based `side_effect` that maps inputs to deterministic outputs for tests that must run in parallel

**Shell escape sequence levels:** Modifying shell template strings (especially ANSI escape sequences like `\\\\033`) requires tracking three escaping layers: Python source string, generated shell script file, and final shell execution. A change that appears correct in Python source may produce wrong output in the generated `.sh` file. After modifying escape sequences, always verify the generated file content matches expectations.

**Multi-phase implementation counting:** When implementing multi-phase changes that introduce intermediate test failures, ALL failures MUST be explicitly counted including BOTH unit tests AND E2E tests. Agents have historically undercounted by omitting E2E failures. Each phase validation MUST confirm the exact failure count matches expectations before proceeding.

## Script Dependencies

Python 3.12 required. **uv** installed by bootstrap scripts. Dependencies: PyYAML, Pydantic. Dev: pytest, ruff, pre-commit.

## Version Management

DO NOT manually edit `CHANGELOG.md`, `version.txt`, or `.release-please-manifest.json`. Release Please manages versioning from conventional commits; bumps happen when release PRs are merged.

**SECURITY.md:** When any commit triggers a major version bump (`!` suffix or `BREAKING CHANGE:` in body/footer), update the "Supported Versions" table in the same PR to show only the new major version as supported.

## Security Considerations

**Config trust levels:** Repository configs are trusted (maintainer-reviewed). Local files are under user control (can contain API keys). Remote URLs show warning messages (verify source first). Never commit configs with sensitive data.

### GitHub Actions Security Policy

**NEVER use mutable branch references** (`@main`, `@master`) for third-party actions -- pin to immutable version tags (`@v5`, `@v0.35.0`). First-party actions (`actions/*`, `github/*`) and composite/docker actions may use major version tags. Version tag pinning (not SHA pinning) is the project standard.

**Verify action runtimes** before updating for Node.js 24 compatibility:
```bash
gh api repos/{owner}/{repo}/contents/action.yml?ref={tag} \
  --jq '.content' | base64 -d | grep -A1 "^runs:"
```
`node24` (preferred) | `composite`/`docker` (always compatible) | `node20` (deprecated, stops June 2, 2026). Note: some actions use `action.yaml` instead of `action.yml`.
