[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetPath,

    [switch]$DryRun,

    [switch]$ForceOwned,

    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $ScriptRoot "installer\pwf_install.py"

$argsList = @()
if ($Uninstall) {
    $argsList += "uninstall"
} else {
    $argsList += "install"
}
$argsList += "--target"
$argsList += $TargetPath
if ($DryRun) { $argsList += "--dry-run" }
if ($ForceOwned -and -not $Uninstall) { $argsList += "--force-owned" }

python $Installer @argsList
exit $LASTEXITCODE
