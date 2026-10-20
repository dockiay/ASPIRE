# Run from Windows PowerShell as administrator. Does not restart Windows.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $repoRoot 'validation-artifacts\setup'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$logPath = Join-Path $logDirectory 'wsl-install.log'
$statusPath = Join-Path $logDirectory 'wsl-install-status.json'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$administrator = ([Security.Principal.WindowsPrincipal]$identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $administrator) {
    throw 'Open PowerShell as administrator and run this script again.'
}

$status = [ordered]@{
    startedAt = [DateTimeOffset]::Now.ToString('o')
    state = 'installing'
    distribution = 'Ubuntu-24.04'
    exitCode = $null
    message = 'Windows will not be restarted automatically.'
}
$status | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
Start-Transcript -Path $logPath -Append | Out-Null
try {
    # --no-launch keeps account creation interactive and under the user's control.
    & wsl.exe --install --distribution Ubuntu-24.04 --no-launch --web-download
    $installExitCode = $LASTEXITCODE
    $status.exitCode = $installExitCode
    if ($installExitCode -notin @(0, 3010, 1641)) {
        throw "WSL installation returned $installExitCode. See $logPath"
    }
    $status.state = 'installation-command-completed'
    $status.message = 'Check the log for a required restart, then run: wsl -d Ubuntu-24.04'
    Write-Host $status.message
}
catch {
    $status.state = 'failed'
    $status.message = $_.Exception.Message
    throw
}
finally {
    $status.finishedAt = [DateTimeOffset]::Now.ToString('o')
    $status | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Stop-Transcript | Out-Null
}
