# Standard Windows component repair, followed by the authorized WSL retry.
[CmdletBinding()]
param([switch]$RetryWsl)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $repoRoot 'validation-artifacts\setup'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$statusPath = Join-Path $logDirectory 'windows-repair-status.json'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)) {
    throw 'Open PowerShell as administrator and run this script again.'
}

$status = [ordered]@{
    startedAt = [DateTimeOffset]::Now.ToString('o')
    state = 'repairing-component-store'
    dismExitCode = $null
    sfcExitCode = $null
    message = 'No automatic restart.'
}
$status | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
Start-Transcript -Path (Join-Path $logDirectory 'windows-repair.log') -Append | Out-Null
try {
    & DISM.exe /Online /Cleanup-Image /RestoreHealth /NoRestart
    $status.dismExitCode = $LASTEXITCODE
    if ($status.dismExitCode -eq 3010) {
        $status.state = 'restart-required'
        $status.message = 'DISM requests a Windows restart before continuing.'
    }
    elseif ($status.dismExitCode -ne 0) {
        throw "DISM returned $($status.dismExitCode). Review the log before further changes."
    }
    else {
        $status.state = 'checking-system-files'
        $status | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
        & sfc.exe /scannow
        $status.sfcExitCode = $LASTEXITCODE
        if ($status.sfcExitCode -ne 0) {
            throw "SFC returned $($status.sfcExitCode). Review the log before retrying WSL."
        }
        $status.state = 'repair-commands-completed'
        $status.message = 'Review DISM and SFC output for any remaining issues or restart request.'
        if ($RetryWsl) {
            $status.state = 'retrying-wsl'
            $status | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
            & (Join-Path $PSScriptRoot 'install_wsl.ps1')
            $status.state = 'wsl-retry-command-completed'
        }
    }
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
