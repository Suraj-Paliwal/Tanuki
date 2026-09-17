$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$runtimePath = Join-Path $taskRoot 'runtime'
New-Item -ItemType Directory -Force $runtimePath | Out-Null
python -m pip install -r (Join-Path $taskRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
$enginePath = Join-Path $runtimePath 'Windows-x64/run.exe'
if (-not (Test-Path -LiteralPath $enginePath)) {
    $archive = Join-Path $runtimePath 'engine.7z'
    Invoke-WebRequest 'https://github.com/Aivis-Project/AivisSpeech-Engine/releases/download/1.2.0/AivisSpeech-Engine-Windows-x64-1.2.0.7z.001' -OutFile $archive
    if ((Get-FileHash $archive -Algorithm SHA256).Hash -ne 'BFBCEBA2E14DC7F23C7F3695F9AC0381BAF91B15D6544E98384574EAADD271F3') { throw 'Engine download checksum mismatch.' }
    tar -xf $archive -C $runtimePath
    if ($LASTEXITCODE -ne 0) { throw 'Could not extract the engine. A recent Windows tar with 7z support is required.' }
}
$vendorPath = Join-Path $taskRoot 'vendor'
if (-not (Test-Path -LiteralPath (Join-Path $vendorPath 'package/build/three.module.js'))) {
    New-Item -ItemType Directory -Force $vendorPath | Out-Null
    $archive = Join-Path $runtimePath 'three.tgz'
    Invoke-WebRequest 'https://registry.npmjs.org/three/-/three-0.169.0.tgz' -OutFile $archive
    tar -xf $archive -C $vendorPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not extract Three.js.' }
}
Write-Host 'Setup complete. Run ./start.ps1.'
