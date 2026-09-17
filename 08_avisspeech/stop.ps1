$ErrorActionPreference = 'Stop'
$runtimePath = Join-Path $PSScriptRoot 'runtime'
foreach ($name in @('server','engine')) {
    $pidFile = Join-Path $runtimePath ($name + '.pid')
    if (-not (Test-Path -LiteralPath $pidFile)) { continue }
    $taskProcessId = [int](Get-Content -LiteralPath $pidFile)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$taskProcessId" -ErrorAction SilentlyContinue
    $owned = if ($name -eq 'engine') {
        $process.ExecutablePath -eq (Join-Path $runtimePath 'Windows-x64\run.exe')
    } else {
        $process.CommandLine -and $process.CommandLine.Contains((Join-Path $PSScriptRoot 'server.py'))
    }
    if ($owned) { Stop-Process -Id $taskProcessId -Force; Write-Host "Stopped Tanuki $name." }
}
