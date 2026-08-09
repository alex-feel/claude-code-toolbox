<#
    Setup-Environment-Windows.ps1
    Purpose: Bootstrap uv and run the cross-platform environment setup
    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"

    To specify configuration:
      # In PowerShell:
      $env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

      # One-liner from CMD or external PowerShell:
      powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
#>

[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification='Installation script needs console output')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingInvokeExpression', '', Justification='Required for web-based installer pattern')]
param()

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Claude Code Environment Setup (Bootstrap)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check if uv is installed
$uvPath = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvPath) {
    Write-Host "[INFO] Installing uv (Python package manager)..." -ForegroundColor Cyan

    try {
        # Install uv using the official installer
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression

        # Update PATH for current session (uv installs to .local\bin)
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

        Write-Host "[OK]   uv installed successfully" -ForegroundColor Green
    } catch {
        Write-Host "[FAIL] Failed to install uv: $_" -ForegroundColor Red
        Write-Host ""
        Write-Host "Please install uv manually from: https://docs.astral.sh/uv/" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "[OK]   uv is already installed" -ForegroundColor Green
}

# Run the Python setup script
Write-Host "[INFO] Running Python environment setup..." -ForegroundColor Cyan
Write-Host ""

$setupScriptUrl = "https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/setup_environment.py"
$installScriptUrl = "https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/install_claude.py"

try {
    # Create stable directory for downloaded scripts
    # This prevents PATH pollution from temporary directory execution contexts
    $toolboxDir = Join-Path $env:USERPROFILE '.claude-toolbox'
    if (-not (Test-Path $toolboxDir)) {
        New-Item -ItemType Directory -Path $toolboxDir -Force | Out-Null
    }

    # Download both Python scripts to stable location
    Write-Host "[INFO] Downloading setup scripts..." -ForegroundColor Cyan
    $setupScript = Join-Path $toolboxDir 'setup_environment.py'
    $installScript = Join-Path $toolboxDir 'install_claude.py'

    Invoke-WebRequest -Uri $setupScriptUrl -OutFile $setupScript -UseBasicParsing
    Invoke-WebRequest -Uri $installScriptUrl -OutFile $installScript -UseBasicParsing

    # Resolve the config with the same precedence as the Python script:
    # a non-flag first argument wins over CLAUDE_CODE_TOOLBOX_ENV_CONFIG
    $forwardArgs = @($args)
    if ($forwardArgs.Count -gt 0 -and -not ([string]$forwardArgs[0]).StartsWith('-')) {
        $config = [string]$forwardArgs[0]
        $forwardArgs = @($forwardArgs | Select-Object -Skip 1)
    } else {
        $config = $env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG
    }

    if (-not $config) {
        Write-Host "[ERROR] No configuration specified!" -ForegroundColor Red
        Write-Host "Usage: setup-environment.ps1 <config_name>" -ForegroundColor Yellow
        Write-Host "   or: Set-Item Env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG 'python'; ./setup-environment.ps1" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Available configurations:" -ForegroundColor Cyan
        Write-Host "  - python    : Python development environment" -ForegroundColor Gray
        Write-Host ""
        exit 1
    }

    Write-Host "[INFO] Using configuration: $config" -ForegroundColor Yellow

    # All remaining user arguments pass through to the Python script
    # verbatim, so the wrapper and the Python interface stay identical.
    # Authentication env vars (GITHUB_TOKEN, GITLAB_TOKEN, REPO_TOKEN,
    # CLAUDE_CODE_TOOLBOX_ENV_AUTH) are read directly by the Python script.

    # Run with uv (it will handle Python 3.12 installation automatically)
    # Script runs from stable location so Python can resolve module imports
    Push-Location $toolboxDir
    try {
        $allArgs = @($config) + $forwardArgs
        & uv run --no-project --python 3.12 setup_environment.py @allArgs
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    # Keep scripts in stable location for future use and debugging
    # No cleanup needed - stable location is intentional

    exit $exitCode
} catch {
    Write-Host "[FAIL] Failed to run setup: $_" -ForegroundColor Red
    exit 1
}
