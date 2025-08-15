<#
    Setup-Python-Environment-Windows.ps1
    Purpose: Bootstrap uv and run the cross-platform Python environment setup
    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-python-environment.ps1')"
#>

[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification='Installation script needs console output')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingInvokeExpression', '', Justification='Required for web-based installer pattern')]
param()

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Python Environment Setup (Bootstrap)" -ForegroundColor Cyan
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

$scriptUrl = "https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/setup-python-environment.py"

try {
    # Download the Python script to a temp file
    $tempScript = [System.IO.Path]::GetTempFileName() + ".py"
    Invoke-WebRequest -Uri $scriptUrl -OutFile $tempScript -UseBasicParsing

    # Run with uv (it will handle Python installation automatically)
    & uv run --python '>=3.12' $tempScript $args
    $exitCode = $LASTEXITCODE

    # Clean up
    Remove-Item $tempScript -Force -ErrorAction SilentlyContinue

    exit $exitCode
} catch {
    Write-Host "[FAIL] Failed to run setup: $_" -ForegroundColor Red
    exit 1
}
