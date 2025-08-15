# Claude Code Python Environment Setup for Windows
# Downloads and configures Python development tools for Claude Code
# Usage: .\setup-python-environment.ps1 [-SkipInstall] [-Force]

[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification='Installation script needs console output')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingInvokeExpression', '', Justification='Required for remote script execution')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', '', Justification='Force parameter is used conditionally')]
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

# Helper functions
function Write-Success {
    param([string]$Message)
    Write-Host "  OK: $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "  INFO: $Message" -ForegroundColor Yellow
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  WARN: $Message" -ForegroundColor Yellow
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "  ERROR: $Message" -ForegroundColor Red
}

function Write-Header {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Blue
    Write-Host "     Claude Code Python Environment Setup for Windows                  " -ForegroundColor Blue
    Write-Host "========================================================================" -ForegroundColor Blue
    Write-Host ""
}

function Test-CommandExist {
    param([string]$Command)
    try {
        $null = Get-Command $Command -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function New-DirectoryIfNotExist {
    [CmdletBinding(SupportsShouldProcess=$true)]
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        if ($PSCmdlet.ShouldProcess($Path, 'Create Directory')) {
            New-Item -ItemType Directory -Path $Path -Force | Out-Null
            return $true
        }
    }
    return $false
}

function Save-FileFromUrl {
    param(
        [string]$Url,
        [string]$Destination
    )

    $fileName = Split-Path -Leaf $Destination

    # Check if file exists and handle Force parameter
    if ((Test-Path $Destination) -and -not $Force) {
        Write-Info "File already exists: $fileName (use -Force to overwrite)"
        return
    }

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing
        [System.IO.File]::WriteAllText($Destination, $response.Content)
        Write-Success "Downloaded: $fileName"
    } catch {
        Write-ErrorMsg "Failed to download: $fileName"
        Write-ErrorMsg $_.Exception.Message
    }
}

# Main script
Write-Header

# Step 1: Install Claude Code if needed
if (-not $SkipInstall) {
    Write-Host "Step 1: Installing Claude Code..." -ForegroundColor Cyan

    try {
        $installUrl = "$RepoBaseUrl/scripts/windows/install-claude-windows.ps1"
        $installScript = (New-Object Net.WebClient).DownloadString($installUrl)
        Invoke-Expression $installScript
        Write-Success "Claude Code installation complete"
    } catch {
        Write-ErrorMsg "Failed to install Claude Code"
        Write-ErrorMsg $_.Exception.Message
        Write-Info "You can retry manually or use -SkipInstall if Claude Code is already installed"
        exit 1
    }
} else {
    Write-Host "Step 1: Skipping Claude Code installation (already installed)" -ForegroundColor Cyan

    # Verify Claude Code is available
    if (-not (Test-CommandExist "claude")) {
        Write-ErrorMsg "Claude Code is not available in PATH"
        Write-Info "Please install Claude Code first or remove the -SkipInstall flag"
        exit 1
    }
}

# Step 2: Create directories
Write-Host ""
Write-Host "Step 2: Creating configuration directories..." -ForegroundColor Cyan
if (New-DirectoryIfNotExist $ClaudeUserDir) { Write-Success "Created: $ClaudeUserDir" }
if (New-DirectoryIfNotExist $AgentsDir) { Write-Success "Created: $AgentsDir" }
if (New-DirectoryIfNotExist $CommandsDir) { Write-Success "Created: $CommandsDir" }
if (New-DirectoryIfNotExist $PromptsDir) { Write-Success "Created: $PromptsDir" }

# Step 3: Download subagents
Write-Host ""
Write-Host "Step 3: Downloading Python-optimized subagents..." -ForegroundColor Cyan
foreach ($agent in $Agents) {
    $url = "$RepoBaseUrl/agents/examples/$agent.md"
    $destination = Join-Path $AgentsDir "$agent.md"
    Save-FileFromUrl -Url $url -Destination $destination
}

# Step 4: Download slash commands
Write-Host ""
Write-Host "Step 4: Downloading slash commands..." -ForegroundColor Cyan
foreach ($command in $Commands) {
    $url = "$RepoBaseUrl/slash-commands/examples/$command.md"
    $destination = Join-Path $CommandsDir "$command.md"
    Save-FileFromUrl -Url $url -Destination $destination
}

# Step 5: Download Python developer system prompt
Write-Host ""
Write-Host "Step 5: Downloading Python developer system prompt..." -ForegroundColor Cyan
$promptUrl = "$RepoBaseUrl/system-prompts/examples/python-developer.md"
$promptPath = Join-Path $PromptsDir "python-developer.md"
Save-FileFromUrl -Url $promptUrl -Destination $promptPath

# Step 6: Configure Context7 MCP server
Write-Host ""
Write-Host "Step 6: Configuring Context7 MCP server..." -ForegroundColor Cyan
$mcpConfigPath = Join-Path $ClaudeUserDir "mcp.json"
$mcpConfig = @'
{
  "servers": {
    "context7": {
      "transport": "http",
      "url": "https://mcp.context7.com/mcp"
    }
  }
}
'@

try {
    [System.IO.File]::WriteAllText($mcpConfigPath, $mcpConfig)
    Write-Success "Created MCP configuration"
} catch {
    Write-Warn "Failed to create MCP configuration: $_"
}

# Step 7: Create launcher script
Write-Host ""
Write-Host "Step 7: Creating launcher script..." -ForegroundColor Cyan
$launcherPath = Join-Path $ClaudeUserDir "start-python-claude.ps1"
$launcherContent = @'
# Claude Code Python Environment Launcher
# This script starts Claude Code with the Python developer system prompt

$claudeUserDir = Join-Path $env:USERPROFILE ".claude"
$promptPath = Join-Path $claudeUserDir "prompts\python-developer.md"

if (-not (Test-Path $promptPath)) {
    Write-Host "Error: Python developer prompt not found at $promptPath" -ForegroundColor Red
    Write-Host "Please run setup-python-environment.ps1 first" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting Claude Code with Python developer configuration..." -ForegroundColor Green
& claude --append-system-prompt "@$promptPath" $args
'@

try {
    [System.IO.File]::WriteAllText($launcherPath, $launcherContent)
    Write-Success "Created launcher script"
} catch {
    Write-Warn "Failed to create launcher script: $_"
}

# Step 8: Register global command
Write-Host ""
Write-Host "Step 8: Registering global claude-python command..." -ForegroundColor Cyan
$localBinPath = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Test-Path $localBinPath)) {
    New-Item -ItemType Directory -Path $localBinPath -Force | Out-Null
}

# Create batch file for easy execution
$batchPath = Join-Path $localBinPath "claude-python.cmd"
$batchContent = "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$launcherPath`" %*"
[System.IO.File]::WriteAllText($batchPath, $batchContent)
Write-Success "Created global command: claude-python"

# Add .local\bin to PATH if not already there
$userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
if (!$userPath) { $userPath = "" }
if ($userPath -notlike "*$localBinPath*") {
    if ($userPath -eq "") {
        [System.Environment]::SetEnvironmentVariable('Path', $localBinPath, 'User')
    } else {
        [System.Environment]::SetEnvironmentVariable('Path', "$localBinPath;$userPath", 'User')
    }
    # Update current session PATH
    $sessionPath = $env:Path
    if (!$sessionPath) { $sessionPath = "" }
    if ($sessionPath -eq "") {
        $env:Path = $localBinPath
    } else {
        $env:Path = "$localBinPath;$sessionPath"
    }
    Write-Success "Added $localBinPath to PATH"
    Write-Info "You may need to restart your terminal for PATH changes to take effect"
}

# Final message
Write-Host ""
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "                    Setup Complete!                                    " -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Green
Write-Host ""

Write-Host "Summary:" -ForegroundColor Yellow
Write-Host "   * Claude Code installation: $(if ($SkipInstall) { 'Skipped' } else { 'Completed' })"
Write-Host "   * Python subagents: $($Agents.Count) installed"
Write-Host "   * Slash commands: $($Commands.Count) installed"
Write-Host "   * System prompt: Configured"
Write-Host "   * MCP server: Context7 configured"
Write-Host "   * Global command: claude-python registered"

Write-Host ""
Write-Host "Quick Start:" -ForegroundColor Yellow
Write-Host "   * Global command: claude-python"
Write-Host "   * Full path: powershell -File '$launcherPath'"
Write-Host "   * Manual: claude --append-system-prompt '@$promptPath'"

Write-Host ""
Write-Host "What's Installed:" -ForegroundColor Yellow
Write-Host "   * 7 Python-optimized subagents (code review, testing, docs, etc.)"
Write-Host "   * 6 custom slash commands (/commit, /debug, /test, etc.)"
Write-Host "   * Context7 MCP server for up-to-date library documentation"
Write-Host "   * Comprehensive Python development system prompt"

Write-Host ""
Write-Host "Available Commands (after starting Claude):" -ForegroundColor Yellow
Write-Host "   * /help - See all available commands"
Write-Host "   * /agents - List available subagents"
Write-Host "   * /commit - Smart Git commits"

Write-Host ""
Write-Host "Examples:" -ForegroundColor Yellow
Write-Host "   claude-python"
Write-Host "   > Create a FastAPI app with async SQLAlchemy and pytest"
Write-Host ""
Write-Host "   claude-python"
Write-Host "   > /commit fix: resolve database connection pooling issue"

Write-Host ""
Write-Host "Documentation:" -ForegroundColor Yellow
Write-Host "   * Python Setup Guide: https://github.com/alex-feel/claude-code-toolbox/blob/main/docs/python-setup.md"
Write-Host "   * Claude Code Docs: https://docs.anthropic.com/claude-code"
Write-Host ""
