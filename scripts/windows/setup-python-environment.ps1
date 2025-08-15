#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Sets up a complete Python development environment for Claude Code.

.DESCRIPTION
    This script automates the setup of Claude Code with Python-specific configurations:
    - Installs Claude Code and dependencies
    - Downloads necessary subagents
    - Installs custom slash commands
    - Configures MCP servers
    - Sets up system prompts for Python development

.PARAMETER SkipInstall
    Skip the Claude Code installation step if it's already installed.

.PARAMETER Force
    Force overwrite of existing configuration files.

.EXAMPLE
    .\setup-python-environment.ps1

.EXAMPLE
    .\setup-python-environment.ps1 -SkipInstall
#>

param(
    [switch]$SkipInstall,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Configuration
$RepoBaseUrl = "https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main"
$ClaudeUserDir = Join-Path $env:USERPROFILE ".claude"
$AgentsDir = Join-Path $ClaudeUserDir "agents"
$CommandsDir = Join-Path $ClaudeUserDir "commands"
$PromptsDir = Join-Path $ClaudeUserDir "prompts"

# List of subagents mentioned in python-developer.md
$Agents = @(
    "code-reviewer",
    "doc-writer",
    "implementation-guide",
    "performance-optimizer",
    "refactoring-assistant",
    "security-auditor",
    "test-generator"
)

# List of slash commands from slash-commands/examples/
$Commands = @(
    "commit",
    "debug",
    "document",
    "refactor",
    "review",
    "test"
)

# Formatting functions
function Write-Step {
    param([string]$Message)
    Write-Host "`n🔷 $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "  ✅ $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "  ℹ️  $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "  ❌ $Message" -ForegroundColor Red
}

function Write-Header {
    Write-Host "`n" -NoNewline
    Write-Host "╔══════════════════════════════════════════════════════════════════════╗" -ForegroundColor Blue
    Write-Host "║                                                                      ║" -ForegroundColor Blue
    Write-Host "║     Claude Code Python Environment Setup for Windows                ║" -ForegroundColor Blue
    Write-Host "║                                                                      ║" -ForegroundColor Blue
    Write-Host "╚══════════════════════════════════════════════════════════════════════╝" -ForegroundColor Blue
    Write-Host "`n"
}

function Test-CommandExists {
    param([string]$Command)
    try {
        Get-Command $Command -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        Write-Success "Created directory: $Path"
    }
}

function Download-File {
    param(
        [string]$Url,
        [string]$Destination
    )

    try {
        $fileName = Split-Path -Leaf $Destination

        # Check if file exists and handle Force parameter
        if ((Test-Path $Destination) -and -not $Force) {
            Write-Info "File already exists: $fileName (use -Force to overwrite)"
            return
        }

        # Download the file
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
        Write-Success "Downloaded: $fileName"
    } catch {
        Write-Error "Failed to download: $fileName"
        Write-Error $_.Exception.Message
    }
}

# Main script
Write-Header

# Step 1: Install Claude Code if needed
if (-not $SkipInstall) {
    Write-Step "Installing Claude Code and dependencies..."

    try {
        $installCommand = "iex (irm '$RepoBaseUrl/scripts/windows/install-claude-windows.ps1')"
        powershell -NoProfile -ExecutionPolicy Bypass -Command $installCommand
        Write-Success "Claude Code installation complete"
    } catch {
        Write-Error "Failed to install Claude Code"
        Write-Error $_.Exception.Message
        Write-Info "You can retry manually or use -SkipInstall if Claude Code is already installed"
        exit 1
    }
} else {
    Write-Step "Skipping Claude Code installation (already installed)"

    # Verify Claude Code is available
    if (-not (Test-CommandExists "claude")) {
        Write-Error "Claude Code is not available in PATH"
        Write-Info "Please install Claude Code first or remove the -SkipInstall flag"
        exit 1
    }
}

# Step 2: Download subagents
Write-Step "Downloading Python-optimized subagents..."
Ensure-Directory $AgentsDir

foreach ($agent in $Agents) {
    $url = "$RepoBaseUrl/agents/examples/$agent.md"
    $destination = Join-Path $AgentsDir "$agent.md"
    Download-File -Url $url -Destination $destination
}

# Step 3: Download slash commands
Write-Step "Downloading custom slash commands..."
Ensure-Directory $CommandsDir

foreach ($command in $Commands) {
    $url = "$RepoBaseUrl/slash-commands/examples/$command.md"
    $destination = Join-Path $CommandsDir "$command.md"
    Download-File -Url $url -Destination $destination
}

# Step 4: Setup MCP servers (Context7)
Write-Step "Configuring MCP servers..."

# We need to run this in a new shell to ensure Claude Code is available
$mcpCommand = "claude mcp add --transport http context7 https://mcp.context7.com/mcp"

try {
    # Start a new PowerShell process to run the MCP command
    $process = Start-Process powershell -ArgumentList "-NoProfile", "-Command", $mcpCommand -PassThru -Wait -NoNewWindow

    if ($process.ExitCode -eq 0) {
        Write-Success "Context7 MCP server configured successfully"
    } else {
        Write-Info "MCP server may already be configured or requires manual setup"
        Write-Info "You can manually run: $mcpCommand"
    }
} catch {
    Write-Info "Could not configure MCP server automatically"
    Write-Info "Please run the following command manually:"
    Write-Host "    $mcpCommand" -ForegroundColor Cyan
}

# Step 5: Download system prompt
Write-Step "Downloading Python developer system prompt..."
Ensure-Directory $PromptsDir

$promptUrl = "$RepoBaseUrl/system-prompts/examples/python-developer.md"
$promptDestination = Join-Path $PromptsDir "python-developer.md"
Download-File -Url $promptUrl -Destination $promptDestination

# Step 6: Create a convenience script for starting Claude with the Python prompt
Write-Step "Creating convenience launcher and global command..."

$launcherPath = Join-Path $ClaudeUserDir "start-python-claude.ps1"
$launcherContent = @'
#!/usr/bin/env pwsh
# Convenience script to start Claude Code with Python developer prompt

$promptFile = Join-Path $env:USERPROFILE ".claude\prompts\python-developer.md"

if (Test-Path $promptFile) {
    Write-Host "Starting Claude Code with Python Developer configuration..." -ForegroundColor Green
    claude --append-system-prompt "@$promptFile" $args
} else {
    Write-Host "Python developer prompt not found at: $promptFile" -ForegroundColor Red
    Write-Host "Please run setup-python-environment.ps1 first" -ForegroundColor Yellow
    exit 1
}
'@

$launcherContent | Out-File -FilePath $launcherPath -Encoding UTF8
Write-Success "Created launcher script: start-python-claude.ps1"

# Create a global command by adding a batch file to a PATH directory
$localBinPath = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Test-Path $localBinPath)) {
    New-Item -ItemType Directory -Path $localBinPath -Force | Out-Null
}

# Create batch file for easy execution
$batchPath = Join-Path $localBinPath "claude-python.cmd"
$batchContent = @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "$launcherPath" %*
"@
$batchContent | Out-File -FilePath $batchPath -Encoding ASCII
Write-Success "Created global command: claude-python"

# Add .local\bin to PATH if not already there
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$localBinPath*") {
    $newPath = "$localBinPath;$currentPath"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$localBinPath;$env:Path"
    Write-Success "Added $localBinPath to PATH"
    Write-Info "You may need to restart your terminal for PATH changes to take effect"
}

# Final message
Write-Host "`n" -NoNewline
Write-Host "╔══════════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                                                                      ║" -ForegroundColor Green
Write-Host "║                    ✨ Setup Complete! ✨                            ║" -ForegroundColor Green
Write-Host "║                                                                      ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host "`n📌 Next Steps:" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray

Write-Host "`n1. Open a " -NoNewline
Write-Host "NEW terminal window" -ForegroundColor Yellow -NoNewline
Write-Host " (to ensure PATH is updated)"

Write-Host "`n2. Start Claude Code with Python configuration:" -ForegroundColor Cyan

Write-Host "`n   " -NoNewline
Write-Host "   claude-python" -ForegroundColor White -BackgroundColor DarkGray
Write-Host "   That's it! The command is now available globally." -ForegroundColor Green

Write-Host "`n   You can also pass additional flags:" -ForegroundColor Cyan
Write-Host "   " -NoNewline
Write-Host "   claude-python --model opus --max-turns 20" -ForegroundColor White -BackgroundColor DarkGray

Write-Host "`n   Alternative methods:" -ForegroundColor DarkCyan
Write-Host "   • Full path: & `"$launcherPath`""
$promptPath = Join-Path $PromptsDir "python-developer.md"
Write-Host "   • Manual: claude --append-system-prompt `"@$promptPath`""

Write-Host "`n3. Available features:" -ForegroundColor Cyan
Write-Host "   • 7 Python-optimized subagents (code review, testing, docs, etc.)"
Write-Host "   • 6 custom slash commands (/commit, /debug, /test, etc.)"
Write-Host "   • Context7 MCP server for up-to-date library documentation"
Write-Host "   • Comprehensive Python development system prompt"

Write-Host "`n4. Test the setup:" -ForegroundColor Cyan
Write-Host "   After starting Claude, try these commands:"
Write-Host "   • " -NoNewline
Write-Host "/help" -ForegroundColor Yellow -NoNewline
Write-Host " - See all available commands"
Write-Host "   • " -NoNewline
Write-Host "/agents" -ForegroundColor Yellow -NoNewline
Write-Host " - List available subagents"
Write-Host "   • " -NoNewline
Write-Host "Task: Review this code for quality" -ForegroundColor Yellow -NoNewline
Write-Host " - Trigger code-reviewer subagent"

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "`n📁 Configuration locations:" -ForegroundColor DarkCyan
Write-Host "   Agents:   $AgentsDir"
Write-Host "   Commands: $CommandsDir"
Write-Host "   Prompts:  $PromptsDir"

Write-Host "`n💡 Tip: Add the launcher to your PATH or create an alias for quick access!" -ForegroundColor Yellow
Write-Host ""
