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

The installer uses a native-first approach with automatic npm fallback. Entry point: `ensure_claude()` → `install_claude_native_cross_platform()` → platform-specific `install_claude_native_{windows,macos,linux}()`. Platform-specific fallback chains: Windows uses Native installer (with HTTP retry) → GCS direct download → npm; macOS/Linux use Native installer → GCS direct download → npm. In `native` mode, npm is excluded from the chain.

**Corrupt-binary detection and quarantine:** `get_claude_version()` delegates to `_probe_claude_version()`, which classifies exec-format launch failures via `_is_exec_format_error()` (Windows `winerror` 193/216, POSIX `errno.ENOEXEC`) as a WARNING ("cannot execute on this machine (corrupt or architecture mismatch)") instead of the generic `[FAIL]`; `FileNotFoundError` is never classified as corruption. `run_command()` is untouched (its contract for other callers is preserved). `ensure_claude()`'s initial probe runs `get_claude_version(quarantine_corrupt=True)`, so a corrupt native binary is moved aside via `_quarantine_corrupt_native_binary()` BEFORE any installation dispatch -- Windows renames to `.exe.old` (swept by `_cleanup_old_claude_files()` on the next run), Unix unlinks -- so it can no longer shadow npm installs through `find_command()`'s native-first priority. Quarantine acts only on the native target `~/.local/bin/claude[.exe]`. Post-install verification executes the installed binary via `_verify_installed_binary_executes()` (probe + quarantine on corruption) on the native-installer and all GCS install paths across Windows, macOS, and Linux; on the Windows native-installer primary path a non-executing binary enters the existing recovery chain.

**GCS download integrity and architecture selection:** `_download_claude_direct_from_gcs()` verifies the downloaded binary against `{gcs_base}/{version}/manifest.json` from the same GCS bucket (`_verify_gcs_download_integrity()`: exact byte size + streamed sha256 via `_sha256_file()`). Fail-closed: a manifest fetch failure or any size/checksum mismatch rejects the download and deletes the temp file. `_get_gcs_platform_path()` returns `tuple | None`: Windows ARM64 (`arm64`/`aarch64`) → `win32-arm64`, Alpine/musl Linux (detected via `/etc/alpine-release`) → `linux-{arch}-musl`, and any unrecognized architecture produces an explicit error and `None` (the caller aborts the GCS download instead of fetching a wrong-architecture binary).

**installMethod values:** `update_install_method_config()` writes `installMethod` to `~/.claude.json` with values `'native'` (native installer or GCS direct download), `'global'` (npm `-g` fallback installs), or `'winget'`. Claude Code itself recognizes `'native'`/`'global'`/`'local'` and reports a missing value as `'unknown'`.

### Standalone Script Policy

`install_claude.py` and `setup_environment.py` MUST be fully standalone -- NEVER import from each other. Users may run either script without the other being present.

**Identical Code** (CI enforced via `tests/test_standalone_policy.py`): `Colors` class, `find_command()`, `_prefer_windows_executable()`, `get_real_user_home()`, `_dev_tty_sudo_available()`, `_run_with_sudo_fallback()`, `needs_sudo_for_npm()` (EXACT body match), shell config file list (7 files + conditional filtering), Fish config detection (`'fish' in str()`), marker block constants (`# >>> claude-code-toolbox >>>`).

**Intentionally Different** (MUST NOT synchronize): `info()`/`success()`/`warning()`/`error()` (different formatting), `run_command()` (different encoding/error handling), `find_bash_windows()` (setup_environment.py has debug_log), `is_admin()` (different implementations).

**Native Path Priority:** `find_command()` and `verify_claude_installation()` check the native path (`~/.local/bin/claude[.exe]`) first, before `shutil.which()` PATH search. This ensures native binary is preferred even when PATH would resolve to npm first. Validates file exists with `st_size > 1000` to skip empty/corrupt files.

**Windows Executable Resolution:** On Windows, `shutil.which()` can resolve a command (e.g. `npm`/`npx`) to the extensionless Unix shell shim Node.js ships beside its `.cmd` wrapper; `subprocess.run(shell=False)` launches resolved paths via `CreateProcess`, which cannot execute that shim and raises `WinError 193` (`%1 is not a valid Win32 application`). This bites on Python builds before the gh-109590 fix (Windows `shutil.which` on CPython 3.12.0 and every 3.11-or-earlier release), which probe the bare name ahead of the PATHEXT variants. The shared `_prefer_windows_executable(cmd, resolved)` helper (identical in both scripts) swaps a non-executable resolution for the `.exe`/`.cmd`/`.bat`/`.com` wrapper and is applied in `find_command()`'s primary search and in `setup_environment.py`'s `run_command()` Windows resolution. `setup_environment.py`'s `run_command()` also catches `OSError` (alongside `FileNotFoundError`) so a single non-launchable command is recorded as a failure instead of aborting the whole run.

**Environment Variables:** `CLAUDE_CODE_TOOLBOX_INSTALL_METHOD` (`auto`/`native`/`npm`, default `auto` -- unknown sources → native-first with npm fallback), `CLAUDE_CODE_TOOLBOX_VERSION` (installs a specific Claude Code version; all methods support version pinning -- native via GCS download and npm; winget is used only for specific version requests and the upgrade_source=='winget' branch), `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT` (`1` only -- see Root Detection Guard).

**Native Path Detection:** `verify_claude_installation()` classifies the binary location for upgrade strategy:

| Path Pattern                                      | Source               | Upgrade Method                        |
|---------------------------------------------------|----------------------|---------------------------------------|
| Contains `npm` or `.npm-global`                   | `npm`                | npm directly                          |
| Contains `.local/bin` or `.claude/bin`            | `native`             | Native installer                      |
| Windows: `Programs\claude` (legacy winget/native) | `winget` or `native` | Via `_classify_localappdata_claude()` |
| Windows: `WinGet\Links` or `WinGet\Packages`      | `winget`             | winget upgrade, then npm fallback     |
| Other / `/usr/local/bin`                          | `unknown`            | Native-first, npm fallback            |
| Not found                                         | `none`               | Fresh install                         |

In `auto` mode, `native` and `unknown` sources attempt native first with npm fallback. Confirmed `npm` sources go directly to npm. Confirmed `winget` sources try `winget upgrade` first, falling back to npm on failure.

### Node.js Compatibility

`ensure_nodejs(check_claude_compat=True)` checks Node.js v25+ SlowBuffer incompatibility for npm Claude Code; `False` checks only minimum >= 18.0.0. `install_claude.py` uses `True`; `setup_environment.py` uses `False` (needs Node.js for MCP servers/npx, not Claude Code).

`CLAUDE_NPM_SLOWBUFFER_FIXED_VERSION`: when `None` (default), v25+ always rejected; when set to a version string, v25+ accepted if installed Claude Code npm version meets threshold. Monitor [#9628](https://github.com/anthropics/claude-code/issues/9628).

### Root Detection Guard

All Linux/macOS scripts refuse to run as root/sudo by default (`id -u == 0` in shell, `os.geteuid() == 0` in Python). Applies to all 6 entry points. Override: `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1` (only exact value `1`; `true`/`yes` do NOT work). Rationale: root creates config under `/root/` instead of user's home. Use override for Docker/CI environments.

### Installation Confirmation

The setup script requires explicit user confirmation before installing. CLI flags: `--yes`/`-y` (auto-confirm), `--dry-run` (preview and exit), `--skip-install` (skip Claude Code installation), `--no-admin` (skip Windows admin elevation). Env vars: `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL=1` (auto-confirm), `CLAUDE_CODE_TOOLBOX_DRY_RUN=1` (preview), `CLAUDE_CODE_TOOLBOX_SKIP_INSTALL=1` (skip installation), `CLAUDE_CODE_TOOLBOX_NO_ADMIN=1` (skip elevation). All accept only exact value `'1'`. Auth: `CLAUDE_CODE_TOOLBOX_ENV_AUTH` (string, `header:value` format).

**Environment Variable Resolution:** All CLI flags and their env var equivalents are merged in `resolve_args()`, called immediately after `parse_args()`. CLI flags take precedence over env vars. The going-forward naming convention is: `--flag-name` becomes `CLAUDE_CODE_TOOLBOX_FLAG_NAME` (direct mechanical mapping). `CONFIRM_INSTALL` is a preserved historical exception.

**Default:** Interactive → `[y/N]` prompt (deny default). Piped with `/dev/tty` → prompts via tty. Non-interactive → refuses (exit 1). Exit `0` for success/dry-run/cancellation, `1` for errors (including download and dependency-installation failures). Bootstrap scripts forward `--yes`, `--dry-run`, `--skip-install`, `--no-admin` to Python.

**Known Config Keys:** The setup script validates config keys against `KNOWN_CONFIG_KEYS` constant. Unknown keys are flagged with `[?]` in the installation summary. When adding new config keys to `setup_environment.py`, remember to update `KNOWN_CONFIG_KEYS`.

**Sensitive Path Detection:** Files-to-download destinations are checked against `SENSITIVE_PATH_PREFIXES`. Sensitive paths (e.g., `~/.ssh/`, `~/.bashrc`) are flagged with `[!]` in the installation summary.

### Environment Configuration System

YAML configs define complete environments: dependencies, agents, MCP servers (auto-permission), slash commands, system prompts (append/replace modes), hooks, global config (`~/.claude.json` via deep merge), and selective inheritance via `merge-keys` directive.

**List Inherit (`inherit: [list]`):** `inherit` accepts `str | list[str | InheritEntry] | None`. Single-element plain-string lists normalize to string (recursive resolution -- the entry's own `inherit` IS resolved). Single-element structured lists (`[{config: ..., merge-keys: [...]}]`) route to `_resolve_list_inherit()` (composition mode). Multi-element lists use flat left-to-right composition via `_resolve_list_inherit()`. Four mandatory rules:

1. **Own inherit stripped (Rule 1):** Each listed file's own `inherit` key is completely ignored in list composition mode. Users must explicitly include all configs in the desired order.
2. **Separate-file equivalence (Rule 2):** `inherit: [A, B, C]` behaves identically to a virtual chain where C inherits B which inherits A. First entry = base (lowest priority), last entry overrides earlier ones, leaf overrides everything.
3. **Own merge-keys stripped, per-entry from leaf (Rule 3):** Each listed file's own `merge-keys` key is stripped and ignored. Per-entry merge-keys are specified in the leaf config using structured `{config: ..., merge-keys: [...]}` entries. merge-keys are a property of the relationship between the leaf and each listed entry, not an intrinsic property of the listed config.
4. **Leaf merge-keys for final step (Rule 4):** The leaf config's top-level `merge-keys` applies to the final composition step (leaf on top of accumulated base). Orthogonal to per-entry merge-keys.

`_validate_merge_keys()` is a DRY helper extracted from the former inline validation, reused for both leaf and per-entry merge-keys validation. `InheritEntry` is a Pydantic model (`config: str`, `merge_keys: list[str] | None` with alias `merge-keys`, `extra='forbid'`) containing an inline `mergeable` frozenset (DRY violation covered by parity test `test_mergeable_config_keys_parity.py`). `_resolve_list_inherit()` threads `auth_param` through `load_config_from_source()` for each entry, extends the existing `visited` set for circular dependency detection, and builds `InheritanceChainEntry` entries for each loaded config.

**Env Loader Files:** `generate_env_loader_files()` creates Rustup-style shell scripts containing ONLY `os-env-variables` (not `env-variables`). Per-command files: `~/.claude/{cmd}/env.sh`, `env.fish` (if Fish installed), `env.ps1` (Windows), `env.cmd` (Windows). Files are generated only when `command_names` is provided; without `command_names`, the function returns `{}`. Loader files are toolbox-owned and rebuilt on every run: `None`-valued (deletion) vars are excluded from the exports, and when no active variable remains the files are rewritten header-only so stale exports from a prior run stop being re-applied by the launcher. `main()` Step 7 calls `set_all_os_env_variables()` and `generate_env_loader_files()` unconditionally (an empty or absent dict is an internal no-op for the OS writer; the loader rebuild always runs). `create_launcher_script()` injects guarded source lines in all 6 launcher variants so commands auto-load env vars.

**Fish Dual-Mechanism:** `set_os_env_variable_unix()` writes `set -gx` to `config.fish` (durable persistence) AND calls `set -Ux` via subprocess (instant propagation to all running Fish sessions). For deletions, `set -Ue` removes the universal variable. The `config.fish` write is authoritative; `set -Ux` is complementary.

**WM_SETTINGCHANGE Broadcast:** `_broadcast_wm_settingchange()` in `setup_environment.py` uses the dummy `setx CLAUDE_CODE_TOOLBOX_TEMP temp` + `reg delete` pattern to trigger `WM_SETTINGCHANGE`. Called from `add_directory_to_windows_path()`, `cleanup_temp_paths_from_registry()`, `set_os_env_variable_windows()` (after `reg delete` for deletions), and `set_all_os_env_variables()` (batch broadcast after all operations). `install_claude.py` has its own independent copy at `ensure_local_bin_in_path_windows()` (standalone script policy).

### Global Config (`global-config`)

Writes to `~/.claude.json`. When `command-names` is present, dual-writes to BOTH `~/.claude.json` (machine baseline for bare `claude` sessions) AND `~/.claude/{cmd}/.claude.json` (for isolated sessions, since Claude Code CLI resolves `getGlobalClaudeFile()` via `CLAUDE_CONFIG_DIR` with no fallback). Content is identical in both files. Merge: `deep_merge_settings()` with `array_union_keys=set()` (arrays replaced, not unioned -- differs from `user-settings` which unions `permissions.allow/deny/ask`). Only `oauthAccount` blocked from non-null values (`GLOBAL_CONFIG_EXCLUDED_KEYS`); `null` allowed for clearing OAuth. `install_claude.py`'s `update_install_method_config()` also writes to `~/.claude.json` via the same pattern (values `'native'`/`'global'`/`'winget'` -- see Native Claude Code Installation Support). Both `write_user_settings()` and `write_global_config()` delegate to `_write_merged_json()`.

**installMethod propagation:** `_propagate_install_method()` runs at Step 15 just before `write_global_config()`. When `command-names` creates an isolated environment, it reads `installMethod` from the base `~/.claude.json` and injects it into `global-config` (creating the dict when the YAML lacks the section, so the empty-config short-circuit does not skip the Step 15 write), letting the dual-write carry the machine-baseline value to the isolated `.claude.json`. WARN-but-Respect: a user-declared YAML `installMethod` wins with a warning when it differs; when the base file or key is absent (or the base JSON is invalid), nothing is propagated. Because propagation runs at Step 15 -- after the pre-confirmation summary has rendered and after Claude Code is installed (so the base `installMethod` exists) -- the propagated value is announced with an `info()` message at injection time and appended to the run's auto-injected list for the record, rather than shown in the pre-confirmation summary.

**Asymmetric write strategy:** `.claude.json` uses dual-write (global semantics, bare sessions need it). `settings.json` uses single-write with scope-based routing (environment-specific semantics, dual-write would cause cross-environment contamination). Root cause: CLI resolves `.claude.json` via `getGlobalClaudeFile()` using `homedir()` as base, while `settings.json` is resolved via `getClaudeConfigHomeDir()` using `join(homedir(), '.claude')` as base. Neither has fallback or inheritance.

**Null-as-delete (RFC 7396):** `null` values in `user-settings`/`global-config` delete the key from the target JSON. `_merge_recursive()` handles via `target.pop(key, None)`. Null in arrays is NOT deletion. Bare YAML keys (`key:` with no value) also trigger deletion -- use `key: ""` for empty strings. Dry-run shows `[DELETE]` markers in RED. `env-variables` and `os-env-variables` values support the same convention (`dict[str, str | None]`): a null `env-variables` entry deletes the variable -- `_build_profile_settings()` preserves per-key `None` so the base-mode merge writer deletes `env.VAR` from `~/.claude/settings.json`, while `create_profile_config()` strips per-key nulls before the atomic isolated `config.json` write (absence equals deletion; the literal JSON null is never written for env entries, and the `env` key is dropped entirely when every entry is null) -- and a null `os-env-variables` entry deletes the OS-level variable.

### Two-File Architecture for Command Environments

When `command-names` is specified, the setup creates an isolated directory `~/.claude/{cmd}/` containing two configuration files loaded by Claude Code at different priority levels:

| File             | Priority         | Content                                                                                        | Write Mechanism                                |
|------------------|------------------|------------------------------------------------------------------------------------------------|------------------------------------------------|
| `settings.json`  | 5 (userSettings) | YAML `user-settings`                                                                           | Deep merge via `write_user_settings()`         |
| `config.json`    | 2 (flagSettings) | Hooks, env vars, permissions, model, MCP permissions, statusLine, attribution, effortLevel     | Atomic write via `create_profile_config()`     |

Scope-based routing: `command-names` presence in the final resolved config determines the SINGLE write target for `write_user_settings()`. Present: `~/.claude/{cmd}/settings.json`. Absent: `~/.claude/settings.json`. Never dual-write.

The launcher (`launch.sh`) passes `config.json` via `--settings` flag and sets `export CLAUDE_CONFIG_DIR` to the isolated directory.

**Setup-time `CLAUDE_CONFIG_DIR` export (two orthogonal channels):** `main()` exports `os.environ['CLAUDE_CONFIG_DIR'] = str(artifact_base_dir)` (guarded by `if primary_command_name:`) immediately after the `artifact_base_dir` if/else block, before deriving artifact directories. This is process-scoped and transient -- never written to `config.json` -- so setup-time child processes (dependency installers, `npx` tooling, `claude mcp ...`, IDE-extension installer) target the isolated profile. This is distinct from the runtime launcher export above (the authoritative runtime source) and from the six per-call MCP `CLAUDE_CONFIG_DIR` injections in `configure_mcp_server()` (load-bearing on the Windows curated-`extra_env` path, which does not inherit `os.environ`; all six are KEPT).

**`link-projects-dir` (optional, isolated-only):** When `config.get('link-projects-dir')` is truthy, Step 22 (end of the `if primary_command_name:` branch in `main()`) calls `link_projects_directory(artifact_base_dir)`, which links `~/.claude/{cmd}/projects/` to the base `~/.claude/projects/` (Unix `symlink_to(..., target_is_directory=True)`; Windows `_winapi.CreateJunction` primary with `mklink /J` fallback). Reparse-aware detection (`os.lstat().st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT`, NOT `Path.is_symlink()` on Windows), idempotent, non-clobbering (a real non-empty `projects/` is preserved with a warning), non-fatal (returns `False` on failure). Helpers: `_is_windows_reparse_point`, `_link_targets_base`. The `link_projects_dir` model field requires `command-names` (validator above).

### Platform-Conditional Tilde Expansion in Settings

`_expand_tilde_keys_in_settings()` handles tilde (`~`) paths in settings keys defined in `TILDE_EXPANSION_KEYS` (`apiKeyHelper`, `awsCredentialExport`):

- **Windows:** Tildes expanded to absolute paths (Windows shell doesn't resolve `~`)
- **Linux/macOS/WSL:** Tildes PRESERVED as-is (Claude Code resolves at runtime)

Preserved on non-Windows to avoid WSL HOME contamination (`os.path.expanduser('~')` on WSL can return Windows paths). `normalize_tilde_path()` uses `Path.home()` instead. `is_wsl()` detects WSL via `/proc/version` and warns about expanded Windows paths.

### Cross-Shell Command Registration (Windows)

Global commands (e.g., `claude-python`) work across all Windows shells: shared POSIX launcher (`~/.claude/{command}/launch.sh`) + wrappers for PowerShell (`start.ps1`), CMD (`start.cmd`) in the same directory, and global entry points in `~/.local/bin/`.

### Validation Models

Pydantic schema `EnvironmentConfig` in `scripts/models/environment_config.py` defines the complete structure for environment YAML configurations. This repository is the canonical source; changes are synced to downstream repos.

**Cross-field model validators** (`@model_validator(mode='after')`): `validate_command_names_and_defaults` (command-names + command-defaults co-dependency), `validate_effort_level_model_support` (effort-level `xhigh`/`max` require an Opus or Fable model -- `EXTENDED_EFFORT_MODEL_MARKERS` substring match -- or the exact alias `best`), `validate_version_requires_command_names` (version requires non-empty command-names), `validate_link_projects_dir_requires_command_names` (link-projects-dir requires non-empty command-names), `validate_merge_keys_requires_inherit` (non-empty merge-keys requires inherit), `validate_profile_mcp_requires_command_names` (profile-scoped MCP servers require command-names), `validate_hooks_files_consistency` (hooks files/events cross-references).

**Field validators**: `validate_model` accepts any non-empty string (supports Anthropic models, third-party models, and provider-prefixed identifiers). `validate_env_variables` and `validate_os_env_variables` both accept `null` values as deletion requests (`dict[str, str | None]`), enforce key format `^[A-Za-z_][A-Za-z0-9_]*$`, and reject null bytes in non-null values.

**MCPServerStdio fields**: `name`, `scope`, `command`, `args` (`list[str] | None`), `env`. The `args` field provides an optional argument list; when present, the runtime combines `command + args` (via `shlex.quote` in `configure_mcp_server()`) or passes them separately to the MCP config JSON (in `create_mcp_config_file()`).

**KNOWN_CONFIG_KEYS parity rule:** When adding new config keys to `setup_environment.py` (extending `KNOWN_CONFIG_KEYS`), the `EnvironmentConfig` model MUST be updated simultaneously (and vice versa). `tests/scripts/models/test_known_config_keys_parity.py` enforces STRICT BIDIRECTIONAL match with ZERO exceptions. Deprecated keys must be DELETED from both, not kept with backward compatibility shims.

**Tests:** `tests/scripts/models/` -- `test_environment_config.py`, `test_mcp_server_scope.py`, `test_known_config_keys_parity.py`, `test_mergeable_config_keys_parity.py`.

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

`setup_environment.py` automatically disables auto-updates when a specific Claude Code version is pinned via `claude-code-version` in YAML, and cleans up stale controls when using latest/absent version. Manages 4 in-memory dict targets (`global-config`, `user-settings.env`, `env-variables`, `os-env-variables`) via `apply_auto_update_settings()`. WARN-but-Respect semantics: if the user explicitly sets a contradicting value in their YAML configuration (e.g., `autoUpdates: true` in `global-config` while pinning a version), the user value is preserved and a warning is emitted. Injection is membership-gated (`key not in dict`), so an explicit user `null` (a deletion request) also counts as a user declaration and is respected with a warning, never overwritten. After injection, `main()` writes the possibly-injected `env-variables` dict back into the resolved config (`config['env-variables'] = env_variables`) so both Step 18 profile builders emit the injected keys even when the YAML lacks the section (a YAML `env-variables: null` is likewise superseded when pinned). The `[auto]` marker in the installation summary shows auto-injected values. Auto-update management is solely the responsibility of `setup_environment.py`; `install_claude.py` does not participate in auto-update configuration.

**Write-remove symmetry:** Auto-update controls are written to specific targets via scope-based routing, while removal sweeps the filesystem locations that can hold artifacts from prior configurations. `_run_stale_controls_cleanup()` runs as a post-write pass in `main()` (Step 16), passing `is_isolated` (from `primary_command_name`) and the user-declared control keys -- collected by `_collect_user_declared_control_keys()` from `user-settings.env` and `env-variables` BEFORE injection -- to both `cleanup_stale_auto_update_controls()` and `cleanup_stale_ide_extension_controls()`. On unpinned runs they sweep `~/.claude/settings.json`, all `~/.claude/*/settings.json`, `~/.claude.json`, and all `~/.claude/*/.claude.json`, except that the `settings.json` sweep is skipped for a control key the current YAML itself declares (the removal counterpart of WARN-but-Respect). On pinned runs they clean the base `~/.claude/settings.json` only when the run is isolated (bare sessions must not inherit isolated restrictions); a pinned non-isolated run performs no `settings.json` sweep because the base file is the run's own Step 14/18 write target. Removal of `autoUpdates` from `.claude.json` files is value-conditional: only `false` (auto-injected) is removed, `true` (user preference) is preserved.

**Unpinned removal semantics:** On an unpinned run nothing is auto-injected, so `_remove_auto_update_controls()` and its exact twin `_remove_ide_extension_controls()` preserve every user-declared control in the four in-memory dicts (the removal counterpart of WARN-but-Respect). Their only mutation schedules an OS-level deletion entry (`os_env_variables[KEY] = None`, gated on `KEY not in os_env_variables` so it is skipped only when the user declares the variable in `os-env-variables` specifically) because the OS-level variable has no filesystem sweep; stale on-disk artifacts are removed by the Step 16 sweep instead.

### Environment Variables

- `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL`: `1` only -- auto-confirm installation (env var for `--yes`)
- `CLAUDE_CODE_TOOLBOX_DRY_RUN`: `1` only -- preview installation plan without changes (env var for `--dry-run`)
- `CLAUDE_CODE_TOOLBOX_SKIP_INSTALL`: `1` only -- skip Claude Code installation (env var for `--skip-install`)
- `CLAUDE_CODE_TOOLBOX_NO_ADMIN`: `1` only -- skip Windows admin elevation (env var for `--no-admin`)
- `CLAUDE_CODE_TOOLBOX_ENV_AUTH`: string -- authentication for private repos, `header:value` format (env var for `--auth`)
- `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT`: `1` only -- allow root on Linux/macOS (see Root Detection Guard)
- `CLAUDE_CODE_TOOLBOX_DEBUG`: `1`/`true`/`yes` -- verbose debug logging
- `CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH`: Override Git Bash executable path
- `CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS`: Override concurrent download workers (default: 2)
- `CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE`: `1`/`true`/`yes` -- disable parallel downloads

### Sudo Handling (Three-Tier Fallback)

`install_claude.py`'s `install_claude_npm()`/`remove_npm_claude()` AND `setup_environment.py`'s global-npm dependency retries and Node.js installers delegate to the shared `_run_with_sudo_fallback()` helper (intentionally identical copies in both scripts -- see Standalone Script Policy) for elevated permissions:

1. **Tier 1 -- Interactive:** `sys.stdin.isatty()` → sudo directly (user enters password via stdin)
2. **Tier 2 -- Cached credentials:** `sudo -n true` probe → sudo without prompting if cached
3. **Tier 3 -- `/dev/tty` fallback:** `_dev_tty_sudo_available()` → sudo with stdin from `/dev/tty` (enables password entry in piped mode like `curl | bash`; default `tty_timeout=60`)

If all tiers exhausted, returns `None` (caller provides guidance). Catches `FileNotFoundError`/`TimeoutExpired` at each tier. `remove_npm_claude()` captures npm output to suppress noisy stack traces.

**Dependency escalation (setup_environment.py):** In `install_dependencies()`'s non-Windows branch, a failed dependency is retried via `_run_with_sudo_fallback(shlex.split(expanded_dep), capture_output=False, timeout=600)` ONLY when ALL of: `_is_global_npm_install(dep)` (the `'npm install -g' in dep` predicate, also reused by `check_admin_needed()` and the Windows elevation message), the expanded command contains no shell control characters (`_contains_shell_control_chars()`: `;`, `&`, `|`, `<`, `>`, `$`, backquote, newline -- user-authored compound shell strings are never run as root), and `needs_sudo_for_npm()` reports the npm global prefix is not user-writable. An informational "sudo may be requested" note prints before the first attempt; when the fallback returns `None` or fails, actionable guidance prints (manual sudo command, `npm config set prefix ~/.npm-global` + PATH export, node version manager). The macOS pkg installer (`_install_nodejs_direct()` Darwin branch) and the Debian/Ubuntu apt/NodeSource path (`_install_nodejs_apt()`) route their sudo invocations through the same helper (600-second timeouts) and fail cleanly with guidance in piped non-interactive runs instead of hanging.

**Dependency failure surfacing:** `install_dependencies()` returns `list[str]` of failed dependency commands (empty list = success; continue-on-failure preserved; the Windows elevation-denied branch returns all collected deps since none execute). `main()` lists failures in a dedicated "The following dependencies failed to install:" section of the "Setup Completed with Errors" block and exits 1, parallel to `download_failures`.

### Download Retry Configuration

Retry logic for GitHub API rate limiting: 10 attempts with linear additive backoff (1s, 3s, 5s, 7s, ..., capped at 60s) plus random 0-25% jitter. Concurrent downloads use 0.5s stagger delay between threads. `RateLimitCoordinator` shares rate-limit state across threads. `Retry-After` and `x-ratelimit-reset` headers used as minimum floor.

`AuthHeaderCache` provides thread-safe per-origin auth header caching (modeled after `RateLimitCoordinator`). `get_origin()` normalizes URL variants (GitHub web/raw/API, GitLab web/API) to a single cache key. A single instance is created in `main()` and shared across both the validation phase (`FileValidator`) and all download functions, so auth discovered during validation is reused during downloads. The first request per origin probes unauthenticated; on auth resolution, subsequent requests for the same origin skip the probe. `resolve_and_cache()` uses double-checked locking for thread safety. `_fetch_url_core()` (DRY refactor of the former near-duplicate `fetch_url_with_auth`/`fetch_url_bytes_with_auth`) implements auth resolution priority: explicit `auth_headers` param > `auth_cache` hit > unauthenticated probe with cache population. GitHub API transport headers (`Accept: application/vnd.github.raw+json`, `X-GitHub-Api-Version`) are managed independently from cached auth headers via `github_api_headers` dict and `_build_request()` helper in `_fetch_url_core()`, applied to every `Request` construction in `_do_fetch()` when `'api.github.com' in url`.

**Lazy-auth invariant (validation + download parity):** Both `FileValidator.validate_remote_url` and `_fetch_url_core._do_fetch` MUST honor the "try unauthenticated first; escalate to authentication only on HTTP 401, 403, or 404" contract. Non-auth failures (SSL, DNS, 5xx, timeout, 416 Range Not Satisfiable) MUST NOT trigger auth prompts. Successful unauthenticated probes cache a `None` sentinel in `AuthHeaderCache` for downstream consumers. When `auth_cache` is available, route escalation through `AuthHeaderCache.resolve_and_cache(url)` (double-checked locking) to serialize prompts across parallel validation threads. Helper functions `_check_with_head` and `_check_with_range` return `tuple[bool, int | None]` where the second element is the HTTP status code (or `None` for non-HTTP failures) used to gate the escalation decision.

**Authentication SRP:** `get_auth_headers(url, auth_param)` is a thin orchestrator that delegates to `resolve_credentials(url, auth_param)` (pure, non-interactive -- reads CLI param + env vars only) and then escalates to `prompt_for_credentials(url, tokens_checked=[...])` (interactive, guarded by `sys.stdin.isatty()`). The split is transparent to existing callers (`get_auth_headers` preserves its original signature and behavior), but enables non-interactive callers to opt into credential resolution without risking user prompts. The interactive prompt uses the wording `Authentication required for {url}` (both the `warning(...)` on interactive terminals and the `info(...)` fallback on non-interactive terminals emit this URL-qualified message); the earlier `Private {RepoType} repository detected but no authentication found` wording has been removed.

**Repository type classification (`detect_repo_type`):** Uses hostname-based matching via `urllib.parse.urlparse`. GitHub Pages URLs (hostname ending in `.github.io`) are explicitly classified as `None` (not `'github'`) because GitHub Pages sites are static HTTP hosts with no repository auth model. `github.com`, `raw.githubusercontent.com`, and `api.github.com` are classified as `'github'`. GitLab classification uses both hostname substring (`'gitlab' in host`) and the API path marker (`/api/v4/projects/`).

**GitHub 404 disambiguation (UX polish):** When a GitHub URL returns HTTP 404 during validation, before escalating to an auth prompt, the validator probes `GET https://api.github.com/repos/{owner}/{repo}` unauthenticated. If the repo endpoint returns 200, the original 404 is classified as a **genuine missing file** (typo) and the auth prompt is skipped (returns failure directly). If the repo endpoint returns 404 (private-hidden or nonexistent -- GitHub does not distinguish), the validator conservatively escalates to the auth prompt. Rate-limiting or network errors from the repo probe also trigger conservative escalation. The `/contents/{path}` endpoint intentionally cannot distinguish private-hidden from missing, which is why `/repos/{owner}/{repo}` is used instead.

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
