# PowerShell Script Analyzer wrapper for pre-commit
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification='Pre-commit hook needs console output')]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Files
)

# Check if PSScriptAnalyzer is installed
if (-not (Get-Module -ListAvailable -Name PSScriptAnalyzer)) {
    Write-Host "PSScriptAnalyzer is not installed." -ForegroundColor Red
    Write-Host "Install it with: Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To install automatically, run:" -ForegroundColor Cyan
    Write-Host "  Set-PSRepository PSGallery -InstallationPolicy Trusted" -ForegroundColor White
    Write-Host "  Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser" -ForegroundColor White
    exit 1  # Fail if not installed
}

$hasErrors = $false

foreach ($file in $Files) {
    if (Test-Path $file) {
        Write-Host "Checking $file..." -ForegroundColor Cyan

        # Run PSScriptAnalyzer with all severity levels like CI does
        $allResults = Invoke-ScriptAnalyzer -Path $file -ReportSummary

        # Filter for only Error and ParseError severities
        $results = $allResults | Where-Object { $_.Severity -in 'Error', 'ParseError' }

        if ($results) {
            $hasErrors = $true
            Write-Host "Critical issues found in ${file}:" -ForegroundColor Red
            $results | Format-Table -AutoSize
        } elseif ($allResults) {
            Write-Host "[OK] No critical issues in $file (warnings exist but are allowed)" -ForegroundColor Green
            # Optionally show warnings for information
            Write-Host "Warnings:" -ForegroundColor Yellow
            $allResults | Where-Object { $_.Severity -eq 'Warning' } | Format-Table -AutoSize
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
