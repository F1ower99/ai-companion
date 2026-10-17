[CmdletBinding()]
param(
    [string]$VenvPath = (Join-Path $PSScriptRoot '..\.venv'),
    [switch]$PreflightOnly,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$pythonExe = Join-Path $VenvPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw "Missing virtual environment Python: $pythonExe. Create .venv and install .[dev,deploy], or pass -VenvPath."
}
$buildArgs = @((Join-Path $PSScriptRoot 'windows_build.py'), '--venv-path', $VenvPath)
if ($PreflightOnly) { $buildArgs += '--preflight-only' }
if ($DryRun) { $buildArgs += '--dry-run' }
& $pythonExe @buildArgs
if ($LASTEXITCODE -ne 0) { throw "Windows build stopped with exit code $LASTEXITCODE." }
