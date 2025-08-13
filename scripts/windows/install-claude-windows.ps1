<#
    Install-Claude-Windows.ps1
    Purpose: Install Git Bash, Node.js if missing, then install Claude Code CLI
    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"

    Notes:
      - Installs Git for Windows (Git Bash) if not found
      - Installs Node.js (LTS version) if not found or version is too old
      - Sets CLAUDE_CODE_GIT_BASH_PATH if bash.exe is not on PATH
      - Verifies the installation
#>

#requires -Version 5.1

[CmdletBinding()]
param(
    [version]$MinNodeVersion = '18.0.0'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Global variable to track if winget message was shown
$script:WingetMessageShown = $false

function Write-Info {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '')]
    param([string]$msg)
    Write-Host "[INFO] $msg" -ForegroundColor Cyan
}
function Write-Ok   {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '')]
    param([string]$msg)
    Write-Host "[OK]   $msg" -ForegroundColor Green
}
function Write-Warn {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '')]
    param([string]$msg)
    Write-Host "[WARN] $msg" -ForegroundColor Yellow
}
function Write-Err  {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '')]
    param([string]$msg)
    Write-Host "[FAIL] $msg" -ForegroundColor Red
}

function Test-Admin {
    try {
        return ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator
        )
    } catch {
        return $false
    }
}

function Relaunch-Elevated {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseApprovedVerbs', '')]
    param(
        [string[]]$ExtraArgs = @()
    )
    if (Test-Admin) { return }

    Write-Info 'Re-launching this script elevated. You may get a UAC prompt...'
    $psi = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', "`"$PSCommandPath`""
    ) + $ExtraArgs

    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $psi -Verb RunAs -PassThru
    $p.WaitForExit()
    exit $p.ExitCode
}

function Get-GitBashCandidatePaths {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseSingularNouns', '')]
    param()
    $candidates = @(
        Join-Path $env:ProgramFiles 'Git\bin\bash.exe'
        Join-Path $env:ProgramFiles 'Git\usr\bin\bash.exe'
        Join-Path $env:LOCALAPPDATA 'Programs\Git\bin\bash.exe'
        Join-Path $env:LOCALAPPDATA 'Programs\Git\usr\bin\bash.exe'
    )
    if (${env:ProgramFiles(x86)}) {
        $candidates += @(
            Join-Path ${env:ProgramFiles(x86)} 'Git\bin\bash.exe'
            Join-Path ${env:ProgramFiles(x86)} 'Git\usr\bin\bash.exe'
        )
    }
    return $candidates
}

function Find-Bash {
    # 1) Respect CLAUDE_CODE_GIT_BASH_PATH if it is valid
    if ($env:CLAUDE_CODE_GIT_BASH_PATH -and (Test-Path $env:CLAUDE_CODE_GIT_BASH_PATH)) {
        return (Resolve-Path $env:CLAUDE_CODE_GIT_BASH_PATH).Path
    }

    # 2) If bash.exe is already on PATH, use it
    $cmd = Get-Command bash.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    # 3) Try common install paths
    foreach ($p in Get-GitBashCandidatePaths) {
        if (Test-Path $p) { return (Resolve-Path $p).Path }
    }

    # 4) Try to search under Program Files
    try {
        $gitDir = Join-Path $env:ProgramFiles 'Git'
        if (Test-Path $gitDir) {
            $found = Get-ChildItem -Path $gitDir -Recurse -Filter 'bash.exe' -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty FullName
            if ($found) { return $found }
        }
    } catch {
        # Ignore errors when searching for bash.exe - directory may not exist or have access issues
        Write-Debug "Error searching for bash.exe: $_"
    }

    return $null
}

function Get-NodeVersion {
    try {
        # First refresh PATH to ensure we see newly installed Node.js
        Update-Path

        # Try to find node.exe in PATH
        $node = Get-Command node.exe -ErrorAction SilentlyContinue

        # If not found in PATH, check common installation locations
        if (-not $node) {
            $commonPaths = @(
                "$env:ProgramFiles\nodejs\node.exe",
                "${env:ProgramFiles(x86)}\nodejs\node.exe",
                "$env:LOCALAPPDATA\Programs\nodejs\node.exe"
            )

            foreach ($path in $commonPaths) {
                if (Test-Path $path) {
                    $node = @{ Source = $path }
                    break
                }
            }
        }

        if (-not $node) { return $null }

        $versionString = & "$($node.Source)" --version 2>$null
        if ($versionString -match 'v?(\d+\.\d+\.\d+)') {
            return [version]$matches[1]
        }
    } catch {
        # Version parsing failed, return null - node may not be properly installed
        Write-Debug "Error parsing Node.js version: $_"
    }
    return $null
}

function Check-Winget {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseApprovedVerbs', '')]
    param()
    # Simple check if winget is available
    $wg = Get-Command winget -ErrorAction SilentlyContinue
    if ($wg) {
        return $true
    }
    return $false
}

function Install-Git-WithWinget {
    param(
        [ValidateSet('user','machine')]
        [string]$Scope = 'user'
    )

    if (-not (Check-Winget)) {
        # Don't print message here, caller will handle it
        return $false
    }

    Write-Info "Installing Git for Windows via winget, scope: $Scope"
    $wingetArgs = @(
        'install',
        '--id','Git.Git',
        '-e',
        '--source','winget',
        '--accept-package-agreements',
        '--accept-source-agreements',
        '--silent',
        '--disable-interactivity',
        '--scope', $Scope
    )

    try {
        $proc = Start-Process -FilePath 'winget' -ArgumentList $wingetArgs -Wait -PassThru -WindowStyle Hidden
        if ($proc.ExitCode -ne 0) {
            Write-Warn "winget exited with code $($proc.ExitCode)"
            return $false
        }
        Write-Ok 'Git for Windows installed via winget'
        return $true
    } catch {
        Write-Warn "winget install threw: $($_.Exception.Message)"
        return $false
    }
}

function Install-Git-ByDownload {
    try {
        Write-Info 'Resolving latest Git for Windows x64 installer URL from git-scm.com...'
        $page = Invoke-WebRequest -UseBasicParsing -Uri 'https://git-scm.com/downloads/win'
        $href = ($page.Links | Where-Object { $_.href -match 'Git-.*-64-bit\.exe$' } | Select-Object -First 1).href

        if (-not $href) {
            throw 'Could not find Git installer link on the downloads page.'
        }

        if ($href -notmatch '^https?://') {
            $uri = [System.Uri]::new('https://git-scm.com')
            $href = [System.Uri]::new($uri, $href).AbsoluteUri
        }

        $temp = Join-Path $env:TEMP (Split-Path $href -Leaf)
        Write-Info "Downloading $href"
        Invoke-WebRequest -Uri $href -OutFile $temp -UseBasicParsing

        Write-Info 'Running Git installer silently...'
        $silent = '/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"'
        $proc = Start-Process -FilePath $temp -ArgumentList $silent -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            throw "Git installer exited with code $($proc.ExitCode)"
        }

        Remove-Item $temp -Force -ErrorAction SilentlyContinue

        # Refresh PATH after Git installation
        Update-Path

        Write-Ok 'Git for Windows installed via direct download'
        return $true
    } catch {
        Write-Err "Failed to install Git by download: $($_.Exception.Message)"
        return $false
    }
}

function Install-NodeJS-WithWinget {
    param(
        [ValidateSet('user','machine')]
        [string]$Scope = 'user'
    )

    if (-not (Check-Winget)) {
        # Don't print message here, caller will handle it
        return $false
    }

    Write-Info "Installing Node.js LTS via winget, scope: $Scope"
    $wingetArgs = @(
        'install',
        '--id','OpenJS.NodeJS.LTS',
        '-e',
        '--source','winget',
        '--accept-package-agreements',
        '--accept-source-agreements',
        '--silent',
        '--disable-interactivity',
        '--scope', $Scope
    )

    try {
        $proc = Start-Process -FilePath 'winget' -ArgumentList $wingetArgs -Wait -PassThru -WindowStyle Hidden
        if ($proc.ExitCode -ne 0) {
            Write-Warn "winget exited with code $($proc.ExitCode)"
            return $false
        }

        # Refresh PATH
        Update-Path

        Write-Ok 'Node.js LTS installed via winget'
        return $true
    } catch {
        Write-Warn "winget install threw: $($_.Exception.Message)"
        return $false
    }
}

function Install-NodeJS-ByDownload {
    try {
        Write-Info 'Downloading Node.js LTS installer from nodejs.org...'

        # Get the LTS version info
        $nodeVersions = Invoke-RestMethod -Uri 'https://nodejs.org/dist/index.json' -UseBasicParsing
        $lts = $nodeVersions | Where-Object { $_.lts } | Select-Object -First 1

        if (-not $lts) {
            throw 'Could not determine LTS version from nodejs.org'
        }

        $version = $lts.version
        $msiUrl = "https://nodejs.org/dist/$version/node-$version-x64.msi"
        $temp = Join-Path $env:TEMP "node-$version-x64.msi"

        Write-Info "Downloading $msiUrl"
        Invoke-WebRequest -Uri $msiUrl -OutFile $temp -UseBasicParsing

        Write-Info 'Installing Node.js silently...'
        $proc = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i', $temp, '/quiet', '/norestart') -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            throw "Node.js installer exited with code $($proc.ExitCode)"
        }

        Remove-Item $temp -Force -ErrorAction SilentlyContinue

        # Refresh PATH
        Update-Path

        Write-Ok 'Node.js installed via direct download'
        return $true
    } catch {
        Write-Err "Failed to install Node.js by download: $($_.Exception.Message)"
        return $false
    }
}

function Ensure-NodeJS {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseApprovedVerbs', '')]
    param(
        [version]$MinVersion
    )

    Write-Info 'Checking Node.js installation...'
    $currentVersion = Get-NodeVersion

    if ($currentVersion) {
        Write-Info "Node.js version $currentVersion found"
        if ($currentVersion -ge $MinVersion) {
            Write-Ok "Node.js version meets minimum requirement (>= $MinVersion)"
            return $true
        }
        Write-Warn "Node.js version $currentVersion is below minimum required version $MinVersion"
    } else {
        Write-Info 'Node.js not found'
    }

    # Check winget availability once
    $wingetAvailable = Check-Winget
    if (-not $wingetAvailable -and -not $script:WingetMessageShown) {
        Write-Info 'winget is not available, using direct download method.'
        $script:WingetMessageShown = $true
    }

    # Try per-user winget install first if available
    if ($wingetAvailable -and (Install-NodeJS-WithWinget -Scope 'user')) {
        Start-Sleep -Seconds 2
        $newVersion = Get-NodeVersion
        if ($newVersion -and $newVersion -ge $MinVersion) {
            Write-Ok "Node.js $newVersion installed for current user"
            return $true
        }
    }

    # Try machine scope if not admin
    if (-not (Test-Admin)) {
        Write-Info 'Attempting machine-wide Node.js installation (elevation required)...'
        Relaunch-Elevated
        return $false
    }

    if ($wingetAvailable -and (Install-NodeJS-WithWinget -Scope 'machine')) {
        Start-Sleep -Seconds 2
        $newVersion = Get-NodeVersion
        if ($newVersion -and $newVersion -ge $MinVersion) {
            Write-Ok "Node.js $newVersion installed machine-wide"
            return $true
        }
    }

    # Last resort: direct download
    if (Install-NodeJS-ByDownload) {
        Start-Sleep -Seconds 2
        $newVersion = Get-NodeVersion
        if ($newVersion -and $newVersion -ge $MinVersion) {
            Write-Ok "Node.js $newVersion installed via direct download"
            return $true
        }
    }

    throw "Could not install Node.js >= $MinVersion"
}

function Ensure-GitBash {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseApprovedVerbs', '')]
    param()
    $bash = Find-Bash
    if ($bash) {
        Write-Ok "Git Bash found at: $bash"
        return $bash
    }

    Write-Info 'Git Bash not found, installing...'

    # Check winget availability once
    $wingetAvailable = Check-Winget
    if (-not $wingetAvailable -and -not $script:WingetMessageShown) {
        Write-Info 'winget is not available, using direct download method.'
        $script:WingetMessageShown = $true
    }

    # Try per-user winget install first if available
    if ($wingetAvailable -and (Install-Git-WithWinget -Scope 'user')) {
        Start-Sleep -Seconds 2
        $bash = Find-Bash
        if ($bash) {
            Write-Ok "Git Bash installed for current user: $bash"
            return $bash
        }
        Write-Warn 'Git Bash not detected after per-user install.'
    }

    # Try machine scope. Elevate if needed.
    if (-not (Test-Admin)) {
        Write-Info 'Attempting machine-wide Git installation (elevation required)...'
        Relaunch-Elevated
        return $null
    }

    if ($wingetAvailable -and (Install-Git-WithWinget -Scope 'machine')) {
        Start-Sleep -Seconds 2
        $bash = Find-Bash
        if ($bash) {
            Write-Ok "Git Bash installed machine-wide: $bash"
            return $bash
        }
        Write-Warn 'Git Bash not detected after machine-wide install.'
    }

    # Last resort, direct download
    if (Install-Git-ByDownload) {
        Start-Sleep -Seconds 2
        $bash = Find-Bash
        if ($bash) {
            Write-Ok "Git Bash installed via direct download: $bash"
            return $bash
        }
    }

    throw 'Could not install or detect Git Bash.'
}

function Ensure-EnvForClaude {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseApprovedVerbs', '')]
    param(
        [string]$BashPath
    )

    # Force re-read environment variables from registry
    $machineEnv = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userEnv = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machineEnv;$userEnv"

    $bashOnPath = $null
    try {
        $bashOnPath = Get-Command bash.exe -ErrorAction SilentlyContinue
    } catch {
        # bash.exe not found in PATH - expected when Git is not installed
        Write-Debug "bash.exe not found in PATH: $_"
    }

    if (-not $bashOnPath) {
        Write-Info 'bash.exe is not on PATH, configuring CLAUDE_CODE_GIT_BASH_PATH for current user...'
        Write-Info "CLAUDE_CODE_GIT_BASH_PATH = $BashPath"

        # Set persistent user env var
        [System.Environment]::SetEnvironmentVariable("CLAUDE_CODE_GIT_BASH_PATH", $BashPath, "User")

        # Also set in current process
        $env:CLAUDE_CODE_GIT_BASH_PATH = $BashPath

        Write-Ok 'User environment variable set.'
    } else {
        Write-Info 'bash.exe is already on PATH, no env var needed.'
    }

    # Set PowerShell execution policy for npm scripts
    Write-Info 'Setting PowerShell execution policy for npm scripts...'

    # Check if we're running with a Process-scoped override (e.g., -ExecutionPolicy Bypass)
    $processPolicy = Get-ExecutionPolicy -Scope Process
    $hasProcessOverride = $processPolicy -ne 'Undefined'

    if ($hasProcessOverride) {
        Write-Info "Running with Process-scoped policy: $processPolicy (this is normal for the installer)"
    }

    # If we're admin, set for LocalMachine to work for all users
    if (Test-Admin) {
        $machinePolicy = Get-ExecutionPolicy -Scope LocalMachine
        if ($machinePolicy -eq 'Restricted' -or $machinePolicy -eq 'AllSigned' -or $machinePolicy -eq 'Undefined') {
            Write-Info "Setting execution policy to RemoteSigned for all users (LocalMachine)..."

            # Temporarily disable Stop error action to handle execution policy setting
            $oldErrorActionPref = $ErrorActionPreference
            $ErrorActionPreference = 'SilentlyContinue'

            try {
                Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force -WarningAction SilentlyContinue 2>$null | Out-Null

                # Check if the policy was actually set despite any warnings
                $newPolicy = Get-ExecutionPolicy -Scope LocalMachine
                if ($newPolicy -eq 'RemoteSigned') {
                    Write-Ok 'PowerShell execution policy set to RemoteSigned for all users (will apply to new sessions)'
                } else {
                    Write-Warn "Could not set LocalMachine execution policy"
                }
            } catch {
                # Silently ignore - policy may already be set or restricted by GPO
                Write-Warn "Could not set LocalMachine execution policy (may be restricted by Group Policy)"
            } finally {
                $ErrorActionPreference = $oldErrorActionPref
            }
        } else {
            Write-Info "Machine execution policy is already $machinePolicy (allows scripts)"
        }
    }

    # Also set for current user to be sure
    $currentPolicy = Get-ExecutionPolicy -Scope CurrentUser
    if ($currentPolicy -eq 'Restricted' -or $currentPolicy -eq 'AllSigned' -or $currentPolicy -eq 'Undefined') {
        Write-Info "Setting execution policy to RemoteSigned for current user..."

        # Temporarily disable Stop error action to handle execution policy setting
        $oldErrorActionPref = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'

        try {
            Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -WarningAction SilentlyContinue 2>$null | Out-Null

            # Check if the policy was actually set despite any warnings
            $newPolicy = Get-ExecutionPolicy -Scope CurrentUser
            if ($newPolicy -eq 'RemoteSigned') {
                Write-Ok 'PowerShell execution policy set to RemoteSigned for current user (will apply to new sessions)'
            } else {
                Write-Warn "Could not set CurrentUser execution policy"
            }
        } catch {
            # Silently ignore - policy may already be set or restricted by GPO
            Write-Warn "Could not set CurrentUser execution policy (may be restricted by Group Policy)"
        } finally {
            $ErrorActionPreference = $oldErrorActionPref
        }
    } else {
        Write-Info "Current user execution policy is already $currentPolicy (allows scripts)"
    }

    if ($hasProcessOverride) {
        Write-Info 'Note: Execution policies have been configured for future PowerShell sessions'
        Write-Info 'The current installer session continues with its Process-scoped policy'
    }
}

function Update-Path {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '')]
    param()
    # Comprehensive PATH refresh from registry
    $machineEnv = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userEnv = [System.Environment]::GetEnvironmentVariable("Path", "User")

    # Combine paths, remove duplicates
    $allPaths = @()
    if ($machineEnv) { $allPaths += $machineEnv.Split(';') }
    if ($userEnv) { $allPaths += $userEnv.Split(';') }

    # Add npm global path if it exists
    $npmGlobalPath = "$env:APPDATA\npm"
    if (Test-Path $npmGlobalPath) {
        $allPaths += $npmGlobalPath
    }

    # Add Node.js paths if they exist
    $nodePaths = @(
        "$env:ProgramFiles\nodejs",
        "${env:ProgramFiles(x86)}\nodejs",
        "$env:LOCALAPPDATA\Programs\nodejs"
    )
    foreach ($nodePath in $nodePaths) {
        if (Test-Path $nodePath) {
            $allPaths += $nodePath
        }
    }

    # Remove empty entries and duplicates
    $uniquePaths = $allPaths | Where-Object { $_ } | Select-Object -Unique

    # Set the combined PATH
    $env:Path = $uniquePaths -join ';'
}

function Install-ClaudeCode {
    Write-Info 'Installing Claude Code CLI...'

    # First refresh PATH and check if Claude is already installed
    Update-Path

    # Check if Claude is already installed
    $claudeCheck = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $claudeCheck) {
        # Check common locations
        $claudePaths = @(
            "$env:APPDATA\npm\claude.cmd",
            "$env:APPDATA\npm\claude",
            "$env:ProgramFiles\nodejs\claude.cmd",
            "$env:LOCALAPPDATA\Programs\claude\claude.exe"
        )

        foreach ($path in $claudePaths) {
            if (Test-Path $path) {
                Write-Ok "Claude Code already installed at: $path"
                return $true
            }
        }
    } else {
        Write-Ok "Claude Code already installed at: $($claudeCheck.Source)"
        return $true
    }

    # Check if npm is available
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Write-Err 'npm not found. Node.js installation may have failed.'
        return $false
    }

    # Method 1: Try direct npm install (official primary method)
    Write-Info 'Installing Claude Code via npm (official method)...'
    try {
        # Find npm.cmd full path
        $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npmCmd) {
            $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
        }

        if (-not $npmCmd) {
            Write-Err 'npm command not found after Node.js installation'
            return $false
        }

        $npmPath = $npmCmd.Source
        Write-Info "Using npm at: $npmPath"

        # Show npm version for debugging
        $npmVersion = & cmd.exe /c "`"$npmPath`" --version 2>&1"
        Write-Info "npm version: $npmVersion"

        # Use npm to install Claude Code CLI directly via cmd.exe to avoid PowerShell parsing issues
        Write-Info 'Running: npm install -g @anthropic-ai/claude-code'
        $npmOutput = & cmd.exe /c "`"$npmPath`" install -g @anthropic-ai/claude-code 2>&1"
        $npmExitCode = $LASTEXITCODE

        if ($npmExitCode -eq 0) {
            Write-Ok 'Claude Code installed via npm'

            # Refresh PATH
            Update-Path

            # Verify installation
            Update-Path
            $claudeCheck = Get-Command claude -ErrorAction SilentlyContinue
            if ($claudeCheck) {
                return $true
            } else {
                # Check in npm global directory
                $npmPrefix = & cmd.exe /c "`"$npmPath`" config get prefix 2>&1"
                if ($npmPrefix) {
                    $npmPrefix = $npmPrefix.Trim()
                    $claudePath = Join-Path $npmPrefix 'claude.cmd'
                    if (Test-Path $claudePath) {
                        Write-Info "Claude Code found at: $claudePath"
                        return $true
                    }
                    # Also check in the npm directory
                    $claudePath = Join-Path "$env:APPDATA\npm" 'claude.cmd'
                    if (Test-Path $claudePath) {
                        Write-Info "Claude Code found at: $claudePath"
                        return $true
                    }
                }
            }
        } else {
            Write-Err "npm install failed with exit code: $npmExitCode"
            Write-Err "npm output:"
            $npmOutput | ForEach-Object { Write-Err "  $_" }
            if ($npmOutput -match 'EACCES|permission') {
                Write-Warn 'Permission error detected. The native installer may work better.'
            }
            if ($npmOutput -match 'E404|404 Not Found') {
                Write-Err 'Package not found. Check if @anthropic-ai/claude-code is the correct package name.'
            }
        }
    } catch {
        Write-Err "npm install threw error: $_"
    }

    # Method 2: Try official native binary installer (stable version)
    Write-Info 'Trying official native binary installer (stable version)...'
    try {
        # Download the official installer
        Write-Info 'Downloading official installer from claude.ai...'
        $installerUrl = 'https://claude.ai/install.ps1'
        $installerScript = Invoke-RestMethod -Uri $installerUrl -UseBasicParsing

        # Execute installer directly inline
        Write-Info 'Running installer...'
        $scriptBlock = [scriptblock]::Create($installerScript)
        & $scriptBlock

        # Give it time to complete
        Start-Sleep -Seconds 3

        # Check if installation succeeded
        Update-Path
        $claudeCheck = Get-Command claude -ErrorAction SilentlyContinue
        if ($claudeCheck) {
            Write-Ok 'Claude Code installed via native installer (stable)'
            return $true
        } else {
            Write-Warn 'Native installer completed but claude command not found'
            Write-Info 'The installer may have installed to a different location'
        }
    } catch {
        Write-Err "Native installer (stable) error: $_"
    }

    # Method 3: Try official native binary installer (latest version)
    Write-Info 'Trying official native binary installer (latest version)...'
    try {
        # Download the official installer
        Write-Info 'Downloading official installer from claude.ai...'
        $installerUrl = 'https://claude.ai/install.ps1'
        $installerScript = Invoke-RestMethod -Uri $installerUrl -UseBasicParsing

        # Execute installer with 'latest' parameter
        Write-Info 'Running installer for latest version...'
        $scriptBlock = [scriptblock]::Create($installerScript)
        & $scriptBlock latest

        # Give it time to complete
        Start-Sleep -Seconds 3

        # Check if installation succeeded
        Update-Path
        $claudeCheck = Get-Command claude -ErrorAction SilentlyContinue
        if ($claudeCheck) {
            Write-Ok 'Claude Code installed via native installer (latest)'
            return $true
        } else {
            Write-Warn 'Native installer completed but claude command not found'
            Write-Info 'Checking common installation locations...'

            # Check common locations
            $commonPaths = @(
                "$env:LOCALAPPDATA\Claude Code\bin\claude.exe",
                "$env:LOCALAPPDATA\Programs\claude\claude.exe",
                "$env:USERPROFILE\.claude\bin\claude.exe"
            )

            foreach ($path in $commonPaths) {
                if (Test-Path $path) {
                    Write-Info "Found Claude at: $path"
                    Write-Info "You may need to add this to your PATH manually"
                    break
                }
            }
        }
    } catch {
        Write-Err "Native installer (latest) error: $_"
    }

    Write-Err 'Claude Code installation failed with all official methods'
    Write-Info 'Please try manual installation:'
    Write-Info '  npm: npm install -g @anthropic-ai/claude-code'
    Write-Info '  or'
    Write-Info '  PowerShell: irm https://claude.ai/install.ps1 | iex'
    return $false
}


# ------------------ Main ------------------

function Write-Banner {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '')]
    param()
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  Claude Code Windows Installer" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Success {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '')]
    param()
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Installation Complete!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
}

function Write-AdminWarning {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '')]
    param()
    Write-Host ""
    Write-Warn 'IMPORTANT: Not installed as administrator'
    Write-Info 'If you get "cannot be loaded" errors in PowerShell, run:'
    Write-Info '  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser'
}

function Write-FailureMessage {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '')]
    param([string]$errorMessage)
    Write-Host ""
    Write-Err $errorMessage
    Write-Host ""
    Write-Host "Installation failed. Please check the error above." -ForegroundColor Red
    Write-Host "For help, visit: https://github.com/alex-feel/claude-code-toolbox" -ForegroundColor Yellow
    Write-Host ""
}

Write-Banner

try {
    # Check and install Git Bash
    Write-Info 'Step 1/4: Checking Git Bash...'
    $bashPath = Ensure-GitBash
    if (-not $bashPath) {
        throw 'Git Bash unavailable after installation attempts.'
    }

    # Check and install Node.js
    Write-Info "Step 2/4: Checking Node.js (minimum version: $MinNodeVersion)..."
    if (-not (Ensure-NodeJS -MinVersion $MinNodeVersion)) {
        throw "Node.js >= $MinNodeVersion unavailable after installation attempts."
    }

    # Configure environment for Claude
    Write-Info 'Step 3/4: Configuring environment...'
    Ensure-EnvForClaude -BashPath $bashPath

    # Ensure we have admin rights for proper PowerShell setup
    if (-not (Test-Admin)) {
        Write-Warn 'Not running as administrator - Claude may not work properly in PowerShell'
        Write-Info 'For best results, run this installer as administrator'
    }

    # Install Claude Code
    Write-Info 'Step 4/4: Installing Claude Code CLI...'
    $claudeInstalled = Install-ClaudeCode

    if ($claudeInstalled) {
        Write-Success

        Write-Info 'You can now start using Claude by running: claude'
        Write-Info 'If claude command is not found, please open a new terminal.'

        # Additional warning if not admin
        if (-not (Test-Admin)) {
            Write-AdminWarning
        }
    } else {
        throw 'Claude Code installation failed with all methods.'
    }

    Write-Info ""
    exit 0
} catch {
    Write-FailureMessage $_.Exception.Message
    exit 1
}
