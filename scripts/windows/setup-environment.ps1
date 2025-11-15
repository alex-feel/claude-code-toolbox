<#
    Setup-Environment-Windows.ps1
    Purpose: Bootstrap uv and run the cross-platform environment setup
    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"

    To specify configuration:
      # In PowerShell:
      $env:CLAUDE_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

      # One-liner from CMD or external PowerShell:
      powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
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

$scriptUrl = "https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/setup_environment.py"

try {
    # Create stable directory for downloaded scripts
    # This prevents PATH pollution from temporary directory execution contexts
    $toolboxDir = Join-Path $env:USERPROFILE '.claude-toolbox'
    if (-not (Test-Path $toolboxDir)) {
        New-Item -ItemType Directory -Path $toolboxDir -Force | Out-Null
    }

    # Download the Python script to stable location
    $stableScript = Join-Path $toolboxDir 'setup_environment.py'
    Invoke-WebRequest -Uri $scriptUrl -OutFile $stableScript -UseBasicParsing

    # Check if configuration is specified
    $config = if ($env:CLAUDE_ENV_CONFIG) { $env:CLAUDE_ENV_CONFIG } elseif ($args.Count -gt 0) { $args[0] } else { $null }

    if (-not $config) {
        Write-Host "[ERROR] No configuration specified!" -ForegroundColor Red
        Write-Host "Usage: setup-environment.ps1 <config_name>" -ForegroundColor Yellow
        Write-Host "   or: Set-Item Env:CLAUDE_ENV_CONFIG 'python'; ./setup-environment.ps1" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Available configurations:" -ForegroundColor Cyan
        Write-Host "  - python    : Python development environment" -ForegroundColor Gray
        Write-Host ""
        exit 1
    }

    Write-Host "[INFO] Using configuration: $config" -ForegroundColor Yellow

    # Check for authentication token
    $authArgs = @()
    if ($env:GITLAB_TOKEN) {
        Write-Host "[INFO] GitLab token found, will use for authentication" -ForegroundColor Cyan
        $authArgs = @('--auth', "PRIVATE-TOKEN:$($env:GITLAB_TOKEN)")
    } elseif ($env:GITHUB_TOKEN) {
        Write-Host "[INFO] GitHub token found, will use for authentication" -ForegroundColor Cyan
        $authArgs = @('--auth', "Authorization:Bearer $($env:GITHUB_TOKEN)")
    } elseif ($env:REPO_TOKEN) {
        Write-Host "[INFO] Generic repo token found, will use for authentication" -ForegroundColor Cyan
        $authArgs = @('--auth', $env:REPO_TOKEN)
    } elseif ($env:CLAUDE_ENV_AUTH) {
        Write-Host "[INFO] Using provided authentication" -ForegroundColor Cyan
        $authArgs = @('--auth', $env:CLAUDE_ENV_AUTH)
    }

    # Run with uv (it will handle Python 3.12 installation automatically)
    # Script runs from stable location to prevent PATH pollution
    if ($authArgs.Count -gt 0) {
        & uv run --python 3.12 $stableScript $config @authArgs
    } else {
        & uv run --python 3.12 $stableScript $config
    }
    $exitCode = $LASTEXITCODE

    # Keep the script in stable location for future use and debugging
    # No cleanup needed - stable location is intentional

    exit $exitCode
} catch {
    Write-Host "[FAIL] Failed to run setup: $_" -ForegroundColor Red
    exit 1
}
