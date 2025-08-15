# PowerShell Script Analyzer wrapper for pre-commit
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification='Pre-commit hook needs console output')]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Files
)

# Check if PSScriptAnalyzer is installed
if (-not (Get-Module -ListAvailable -Name PSScriptAnalyzer)) {
    Write-Warning "PSScriptAnalyzer is not installed."
    Write-Warning "Install it with: Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser"
    exit 0  # Don't fail if not installed, just warn
}

$hasErrors = $false

foreach ($file in $Files) {
    if (Test-Path $file) {
        Write-Host "Checking $file..." -ForegroundColor Cyan

        # Run PSScriptAnalyzer
        $results = Invoke-ScriptAnalyzer -Path $file -Severity Warning,Error

        if ($results) {
            $hasErrors = $true
            Write-Host "Issues found in ${file}:" -ForegroundColor Yellow
            $results | Format-Table -AutoSize
        } else {
            Write-Host "[OK] No issues found in $file" -ForegroundColor Green
        }
    }
}

if ($hasErrors) {
    Write-Host "`nPSScriptAnalyzer found issues. Please fix them before committing." -ForegroundColor Red
    exit 1
}

Write-Host "`nAll PowerShell scripts passed PSScriptAnalyzer checks!" -ForegroundColor Green
exit 0
