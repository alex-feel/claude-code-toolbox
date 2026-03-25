# Installing Claude Code

This guide covers installing Claude Code using the Claude Code Toolbox installer. The installer uses the official native Anthropic installer by default and automatically falls back to npm if needed. All dependencies (uv, Python, Node.js) are handled automatically -- you do not need to install anything beforehand.

## Quick Install

### Windows

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
```

### macOS

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh | bash
```

### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

The installer automatically handles all dependencies (uv, Python, Node.js if needed) and installs Claude Code using the native Anthropic installer with npm fallback.

## Installation Methods

### Native Installation (Default)

The native method uses official Anthropic installers (`https://claude.ai/install.ps1` on Windows, `https://claude.ai/install.sh` on macOS and Linux). This is the default and recommended approach because it does not require Node.js, provides more reliable auto-updates via the official update mechanism, and supports specific version installation via direct binary download from Google Cloud Storage.

### npm Installation (Fallback)

The npm method installs via the `@anthropic-ai/claude-code` npm package. It requires Node.js 18+ (auto-installed if needed) and is used automatically if native installation fails in `auto` mode. You can force npm installation by setting `CLAUDE_CODE_TOOLBOX_INSTALL_METHOD=npm`.

### Auto Mode (Default Behavior)

In `auto` mode (the default), the installer tries native first. If native fails, it automatically falls back to npm. This is the recommended approach for most users and requires no additional configuration.

## Environment Variables

### `CLAUDE_CODE_TOOLBOX_INSTALL_METHOD`

Controls which installation method the installer uses.

| Value            | Behavior                                                  |
|------------------|-----------------------------------------------------------|
| `auto` (default) | Try native installation first, fall back to npm if needed |
| `native`         | Use only native installer, no npm fallback                |
| `npm`            | Use only npm installer, requires Node.js 18+              |

Invalid values default to `auto` with a warning.

**Linux/macOS example:**

```bash
CLAUDE_CODE_TOOLBOX_INSTALL_METHOD=native curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

**Windows example:**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:CLAUDE_CODE_TOOLBOX_INSTALL_METHOD='npm'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
```

### `CLAUDE_CODE_TOOLBOX_VERSION`

Specify a particular version to install (e.g., `2.0.76`). Works with both native (via direct binary download from Google Cloud Storage) and npm installation methods. When a specific version is set, `DISABLE_AUTOUPDATER` is automatically configured to prevent auto-updates from overwriting the pinned version. When the version pin is removed (running without `CLAUDE_CODE_TOOLBOX_VERSION`), `DISABLE_AUTOUPDATER` is automatically removed from all shell profiles and the Windows registry, re-enabling auto-updates. If the requested version is not found via GCS download, the installer falls back to the native installer with the latest version.

**Linux/macOS example:**

```bash
CLAUDE_CODE_TOOLBOX_VERSION=2.0.76 curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

**Windows example:**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:CLAUDE_CODE_TOOLBOX_VERSION='2.0.76'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
```

### `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT`

Set to exactly `1` to allow running as root on Linux/macOS. Only the exact string `1` is accepted -- `true`, `yes`, and empty strings do NOT work. By default, the installer refuses to run as root because running as root creates configuration under `/root/` instead of the regular user's home directory. Use this for Docker containers, CI/CD pipelines, or other legitimate root execution environments.

```bash
CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1 curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

## What the Installer Does

The bootstrap scripts install `uv` (Astral's Python package manager) and Python 3.12 automatically before running the main installer. The main installer then performs the following steps.

**Windows (4 steps):**

1. Checks and installs Git Bash if not present (required for scripts that need `bash.exe`)
2. Checks Node.js availability (only installs Node.js if the npm method will be used)
3. Configures the environment (PowerShell execution policy, PATH updates)
4. Installs Claude Code CLI (native-first, npm fallback)

**macOS and Linux (3 steps):**

1. Checks Node.js availability (only installs Node.js if the npm method will be used)
2. Skips Git Bash and environment configuration (not needed on Unix platforms)
3. Installs Claude Code CLI (native-first, npm fallback)

## Upgrades and Switching Methods

### Automatic Upgrades

When Claude Code is already installed, the installer checks for updates against the npm registry and upgrades using the same method that was originally used (source-matching). Native installations are upgraded via the native installer, npm installations are upgraded via npm, and unknown-source installations try native first with npm fallback.

### Auto-Migration from npm to Native

In `auto` mode, when an npm installation is detected, the installer automatically attempts to migrate to the native installer for better stability. On successful migration, the old npm installation is removed to prevent PATH conflicts. If npm removal fails (due to permission issues in non-interactive mode), the installer displays a prominent warning with manual removal instructions but does not block the native installation.

### Source Detection

The installer classifies the existing installation by examining the binary path.

| Path Pattern                           | Detected Source | Upgrade Method             |
|----------------------------------------|-----------------|----------------------------|
| Contains `npm` or `.npm-global`        | npm             | npm directly               |
| Contains `.local/bin` or `.claude/bin` | native          | Native installer           |
| Contains `/usr/local/bin`              | unknown         | Native-first, npm fallback |
| Windows: contains `Programs\claude`    | winget          | npm                        |
| Any other path                         | unknown         | Native-first, npm fallback |
| Not found                              | none            | Fresh install              |

### Switching from npm to Native

To switch manually, uninstall the npm version with `npm uninstall -g @anthropic-ai/claude-code`, then run the installer again. It will use the native method by default. All Claude Code configurations are preserved since both installation methods use the same configuration directory.

## Troubleshooting

### Native Installation Fails

The installer automatically falls back to npm in `auto` mode, so most users do not need to take any action. To isolate the issue, use `CLAUDE_CODE_TOOLBOX_INSTALL_METHOD=native` to see only native installer output without the npm fallback. You can also try the native installer directly:

- **Windows:** `irm https://claude.ai/install.ps1 | iex`
- **macOS/Linux:** `curl -fsSL https://claude.ai/install.sh | bash`

### Node.js v25+ Compatibility

Node.js v25+ removed the SlowBuffer API that Claude Code's npm package depends on. This does NOT affect native installations, which do not require Node.js. If you must use the npm method, downgrade to Node.js v22 or v20 LTS:

- **macOS:** `brew uninstall node && brew install node@22 && brew link --force --overwrite node@22`
- **Linux:** `nvm install 22 && nvm use 22`
- **Windows:** Download Node.js 22 LTS from <https://nodejs.org/>

### Root Guard

The installer refuses to run as root by default because running as root creates configuration under `/root/` instead of your home directory. Run as your regular user -- the installer requests sudo only when needed (for npm global installs). Override with `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1` for Docker or CI environments.

### npm Version Still Runs After Native Install

If you installed the native version but `claude --version` still shows the old npm version, you may have both installations present and PATH ordering causes the npm binary to take precedence. The installer attempts automatic npm removal during native installation but it can fail silently in non-interactive environments (such as `curl | bash` without cached sudo credentials).

**Symptoms:** A prominent boxed warning during installation stating "npm Claude Code installation was NOT removed", or `which claude` pointing to a path containing `npm` or `/usr/local/bin` instead of `~/.local/bin`.

**Fix:** Remove the npm installation manually and restart your terminal:

```bash
sudo npm uninstall -g @anthropic-ai/claude-code
```

On Windows (run as Administrator):

```powershell
npm uninstall -g @anthropic-ai/claude-code
```

After removal, restart your terminal session so that `claude` resolves to the native binary at `~/.local/bin/claude`.

### Claude Command Not Found After Install

If `claude` is not available after installation, open a new terminal session. The installer updates PATH but the current session may not reflect the change.

### Corporate Proxy or Firewall

The installer includes SSL fallback for corporate environments with custom certificates. If downloads fail, check your firewall rules for access to `claude.ai`, `storage.googleapis.com`, and `registry.npmjs.org`.
