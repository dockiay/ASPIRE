param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')]
    [string]$RunName,
    [string]$Distribution = 'Ubuntu-24.04',
    [string]$LinuxRoot = '/home/sergio/src/ASPIRE',
    [string]$ControllerConfig = 'configs/so101/codex-local.json',
    [ValidateSet('sam3', 'color-rgbd')][string]$Segmentation = 'sam3',
    [string]$Sam3Url = 'http://127.0.0.1:8114',
    [ValidateRange(1, 20)][int]$MaxPrograms = 8,
    [ValidateRange(1, 200)][int]$MaxCalls = 96,
    [switch]$Smoke,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$controllerCandidate = if ([System.IO.Path]::IsPathRooted($ControllerConfig)) { $ControllerConfig } else { Join-Path $repoRoot $ControllerConfig }
$controllerPath = (Resolve-Path -LiteralPath $controllerCandidate).Path
$controllerSettings = Get-Content -LiteralPath $controllerPath -Raw | ConvertFrom-Json
$mountedRoot = (& wsl.exe -d $Distribution --exec wslpath -u $repoRoot.Replace('\', '/') | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $mountedRoot.StartsWith('/mnt/')) {
    throw 'No se pudo resolver el proyecto de Windows dentro de WSL.'
}
if (-not $LinuxRoot.StartsWith('/') -or $LinuxRoot.Contains('..')) {
    throw 'LinuxRoot debe indicar la carpeta absoluta del proyecto instalado en Ubuntu.'
}
$mountedController = (& wsl.exe -d $Distribution --exec wslpath -u $controllerPath.Replace('\', '/') | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'No se pudo convertir la ruta de configuración.' }
$linuxOutput = "$LinuxRoot/outputs/runs/$RunName"
$windowsOutput = Join-Path $repoRoot "outputs/runs/$RunName"
$oldBridgeEnvironment = $env:WSLENV

function Invoke-AspireWSL {
    param([string[]]$Arguments)
    if ($DryRun) {
        Write-Host ('WSL: ' + ($Arguments -join ' '))
        return
    }
    & wsl.exe -d $Distribution --exec @Arguments
    if ($LASTEXITCODE -ne 0) { throw "El comando WSL terminó con código $LASTEXITCODE." }
}

try {
    if ($controllerSettings.type -eq 'api') {
        $keyName = if ($controllerSettings.api_key_env) { $controllerSettings.api_key_env } else { 'OPENAI_API_KEY' }
        if ($keyName -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { throw 'Nombre de variable de credencial inválido.' }
        # WSLENV forwards the value through the process environment, never argv.
        # A credential already exported inside Ubuntu also remains supported.
        if (-not $DryRun -and [Environment]::GetEnvironmentVariable($keyName)) {
            $env:WSLENV = (@($oldBridgeEnvironment, "$keyName/u") | Where-Object { $_ }) -join ':'
        }
    }
    Write-Host 'Sincronizando las fuentes del proyecto con Ubuntu...'
    foreach ($relative in @('src', 'configs', 'docs', 'tests', '.claude/skills/iterative-debugging')) {
        Invoke-AspireWSL -Arguments @('rsync', '-rt', '--exclude=__pycache__', "$mountedRoot/$relative/", "$LinuxRoot/$relative/")
    }
    Invoke-AspireWSL -Arguments @('rsync', '-rt', "$mountedRoot/pyproject.toml", "$LinuxRoot/")
    $module = if ($Smoke) { 'cap_harness.so101.debug_agent' } else { 'cap_harness.so101.pipeline' }
    $arguments = @('env', 'MUJOCO_GL=glfw', "CAP_HARNESS_SO101_SEGMENTATION=$Segmentation", "CAP_HARNESS_SAM3_URL=$Sam3Url", "$LinuxRoot/.venv-robosuite/bin/python", '-m', $module,
        '--output', $linuxOutput, '--controller-config', $mountedController,
        '--skills-dir', "$mountedRoot/configs/so101/skills")
    if ($Smoke) {
        $arguments += @('--smoke', '--seeds', '0', '--max-programs', '2', '--max-calls', '24',
            '--max-steps', '24', '--width', '160', '--height', '120', '--agent-timeout-s', '600')
    } else {
        $arguments += @('--max-programs', "$MaxPrograms", '--max-calls', "$MaxCalls")
    }
    Write-Host "Ejecutando ASPIRE: $RunName. La biblioteca compartida permanece en el proyecto de Windows."
    Invoke-AspireWSL -Arguments $arguments
} finally {
    $env:WSLENV = $oldBridgeEnvironment
    if ($DryRun) {
        Write-Host "Los resultados se copiarían a: $windowsOutput"
    } else {
        & wsl.exe -d $Distribution --exec test -d $linuxOutput
        if ($LASTEXITCODE -eq 0) {
            New-Item -ItemType Directory -Force -Path $windowsOutput | Out-Null
            & wsl.exe -d $Distribution --exec rsync -rt "$linuxOutput/" "$mountedRoot/outputs/runs/$RunName/"
            if ($LASTEXITCODE -ne 0) { Write-Warning 'La copia de resultados no terminó; los originales siguen en Ubuntu.' }
        }
    }
}
