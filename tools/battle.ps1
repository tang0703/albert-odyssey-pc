param([ValidateSet('test','export','run')][string]$Action='run')
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $PcRoot
$Demo=Join-Path $PcRoot 'battle-demo'
$Godot=Join-Path $Workspace 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Reports=Join-Path $PcRoot 'reports'
New-Item -ItemType Directory -Force $Reports | Out-Null
function Checked([string[]]$Arguments,[string]$Name) {
    $Log=Join-Path $Reports ($Name+'.log')
    & $Godot @Arguments *> $Log
    if ($LASTEXITCODE -ne 0 -or (Get-Content -Raw $Log) -match 'SCRIPT ERROR:|Parse Error:|Assertion failed|Failed to load script') {
        Get-Content $Log -Tail 25
        throw "Battle command failed: $Name"
    }
}
if ($Action -eq 'run') { & $Godot --path $Demo; exit $LASTEXITCODE }
Checked @('--headless','--path',$Demo,'--editor','--import','--quit') 'battle-import'
if ($Action -eq 'test') {
    foreach ($Test in @('test_core','test_ui','timing')) {
        Checked @('--headless','--path',$Demo,'--script',("res://tests/"+$Test+'.gd')) ("battle-"+$Test)
    }
    Write-Output 'Battle core, UI and timing checks passed.'
    exit
}
$Output=Join-Path $PcRoot 'build/battle-demo'
New-Item -ItemType Directory -Force $Output | Out-Null
Checked @('--headless','--path',$Demo,'--export-release','Windows Battle Demo') 'battle-export'
Copy-Item -LiteralPath (Join-Path $Demo 'README.md') -Destination (Join-Path $Output 'README.md')
Copy-Item -LiteralPath (Join-Path $PcRoot 'licenses/GODOT-LICENSE.txt') -Destination $Output
Copy-Item -LiteralPath (Join-Path $PcRoot 'licenses/GODOT-COPYRIGHT.txt') -Destination $Output
$Allowed=@('Triad-Trial.exe','Triad-Trial.pck','Triad-Trial.console.exe','README.md','GODOT-LICENSE.txt','GODOT-COPYRIGHT.txt')
$Unexpected=Get-ChildItem -LiteralPath $Output | Where-Object { $_.Name -notin $Allowed }
if ($Unexpected) { throw 'Unexpected files in battle package; review before packaging.' }
$Zip=Join-Path $PcRoot 'build/Triad-Trial-Windows-x64.zip'
Compress-Archive -Path (Join-Path $Output '*') -DestinationPath $Zip -Force
Get-FileHash -Algorithm SHA256 $Zip
