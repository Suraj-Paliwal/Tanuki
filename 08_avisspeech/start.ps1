param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$runtimePath = Join-Path $taskRoot 'runtime'
New-Item -ItemType Directory -Force $runtimePath | Out-Null
$pythonPath = (Get-Command python -ErrorAction Stop).Source
& $pythonPath -c 'import numpy'
if ($LASTEXITCODE -ne 0) { throw 'Install the dependency first: python -m pip install -r requirements.txt' }
$enginePath = Join-Path $runtimePath 'Windows-x64/run.exe'
$engineProcess = Get-Process -Name run -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $enginePath } | Select-Object -First 1
$engineReady = $false
try { $null = Invoke-RestMethod 'http://127.0.0.1:10101/version' -TimeoutSec 2; $engineReady = $true } catch {}
if (-not $engineReady -and -not $engineProcess) {
    if (-not (Test-Path -LiteralPath $enginePath)) { throw 'Run setup.ps1 first, or start your installed AivisSpeech app.' }
    $engineProcess = Start-Process -FilePath $enginePath -ArgumentList '--host','127.0.0.1','--port','10101','--output_log_utf8','--disable_sentry' -WorkingDirectory (Split-Path $enginePath) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'engine.stdout.log') -RedirectStandardError (Join-Path $runtimePath 'engine.stderr.log') -PassThru
}
if ($engineProcess) { $engineProcess.Id | Set-Content (Join-Path $runtimePath 'engine.pid') }
$listener = Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    $serverPath = Join-Path $taskRoot 'server.py'
    $serverProcess = Start-Process -FilePath $pythonPath -ArgumentList '-u',('"' + $serverPath + '"') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'server.stdout.log') -RedirectStandardError (Join-Path $runtimePath 'server.stderr.log') -PassThru
    $serverProcess.Id | Set-Content (Join-Path $runtimePath 'server.pid')
    Start-Sleep -Seconds 2
    if ($serverProcess.HasExited) { throw 'The viewer server could not start. See runtime/server.stderr.log.' }
}
Write-Host 'Tanuki + AivisSpeech: http://127.0.0.1:8088'
Write-Host 'The page reconnects automatically while the engine starts. First launch downloads voice assets.'
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8088' }
