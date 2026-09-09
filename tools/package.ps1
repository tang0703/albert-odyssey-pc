$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot 'run.ps1') -Action test
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
& (Join-Path $PSScriptRoot 'run.ps1') -Action export
if ($LASTEXITCODE -ne 0) { throw 'Export failed' }
$Output=Join-Path $PcRoot 'build\windows'
Copy-Item -LiteralPath (Join-Path $PcRoot 'README.md') -Destination $Output -Force
Copy-Item -LiteralPath (Join-Path $PcRoot 'licenses') -Destination $Output -Recurse -Force
$Zip=Join-Path $PcRoot 'build\ao-pc-asset-workbench-local.zip'
Compress-Archive -Path (Join-Path $Output '*') -DestinationPath $Zip -Force
Get-FileHash -LiteralPath $Zip -Algorithm SHA256
Write-Output 'Local development package only; Stage B is not accepted and this is not a playable remake.'
