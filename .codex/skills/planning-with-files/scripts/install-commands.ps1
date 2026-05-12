[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Resolve-Path (Join-Path $ScriptDir "..\..\..\commands")

if ($env:CODEX_HOME) {
    $CodexHome = $env:CODEX_HOME
} else {
    $CodexHome = Join-Path $env:USERPROFILE ".codex"
}

$PromptDir = Join-Path $CodexHome "prompts"
New-Item -ItemType Directory -Force -Path $PromptDir | Out-Null

$Installed = 0
$Skipped = 0

Get-ChildItem -LiteralPath $SourceDir -Filter "plw-*.md" | ForEach-Object {
    $Destination = Join-Path $PromptDir $_.Name

    if ((Test-Path $Destination) -and -not $Force) {
        Write-Output "[plw-install] skip existing $($_.Name) (use -Force to overwrite)"
        $script:Skipped += 1
        return
    }

    Copy-Item -LiteralPath $_.FullName -Destination $Destination -Force:$Force
    Write-Output "[plw-install] installed $($_.Name) -> $Destination"
    $script:Installed += 1
}

Write-Output "[plw-install] complete: installed=$Installed skipped=$Skipped"
Write-Output "[plw-install] restart Codex if slash commands do not appear immediately."
