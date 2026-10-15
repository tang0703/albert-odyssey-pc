param(
    [ValidateSet('top','center','bottom','reenter','wait','hold')][string[]]$Routes=@('top','bottom','reenter','wait','hold'),
    [string]$Root='reports/event/d1-v1'
)
$ErrorActionPreference='Stop'
$Project=Split-Path -Parent $PSScriptRoot
$Python=Join-Path (Split-Path -Parent $Project) 'tools/pc-remake/python/Scripts/python.exe'
foreach ($Route in $Routes) {
    Write-Output "Verifying synchronized replay: $Route"
    & $Python (Join-Path $PSScriptRoot 'verify_character_capture.py') (Join-Path $Root "$Route-a") (Join-Path $Root "$Route-b") (Join-Path $Root "$Route-c") --out (Join-Path $Root "$Route-replay.json")
    if ($LASTEXITCODE -ne 0) { throw "Rejected replay: $Route" }
}
