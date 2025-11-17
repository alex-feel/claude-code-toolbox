<#
    Install-Claude-Windows.ps1
    Purpose: Bootstrap uv and run the cross-platform Claude installer
    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
#>

[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification='Installation script needs console output')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingInvokeExpression', '', Justification='Required for web-based installer pattern')]
param()

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Claude Code Windows Installer (Bootstrap)" -ForegroundColor Cyan
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

# Run the Python installer script
Write-Host "[INFO] Running Claude Code installer..." -ForegroundColor Cyan
Write-Host ""

$scriptUrl = "https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/install_claude.py"

try {
    # Create stable directory for downloaded scripts
    # This prevents PATH pollution from temporary directory execution contexts
    $toolboxDir = Join-Path $env:USERPROFILE '.claude-toolbox'
    if (-not (Test-Path $toolboxDir)) {
        New-Item -ItemType Directory -Path $toolboxDir -Force | Out-Null
    }

    # Download the Python script to stable location
    $stableScript = Join-Path $toolboxDir 'install_claude.py'
    Invoke-WebRequest -Uri $scriptUrl -OutFile $stableScript -UseBasicParsing

    # Run with uv (it will handle Python 3.12 installation automatically)
    # Script runs from stable location to prevent PATH pollution
    & uv run --no-project --python 3.12 $stableScript
    $exitCode = $LASTEXITCODE

    # Keep the script in stable location for future use and debugging
    # No cleanup needed - stable location is intentional

    exit $exitCode
} catch {
    Write-Host "[FAIL] Failed to run installer: $_" -ForegroundColor Red
    exit 1
}
