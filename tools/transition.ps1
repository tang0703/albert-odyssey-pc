param([ValidateSet('run','test','export')][string]$Action='run',[string]$Output)
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $PcRoot
$Godot=Join-Path $Workspace 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Python=Join-Path $Workspace 'tools/pc-remake/python/Scripts/python.exe'
$Demo=Join-Path $PcRoot 'exploration-demo'
$Reports=Join-Path $PcRoot 'reports/transition'
New-Item -ItemType Directory -Force -Path $Reports | Out-Null
if ($Action -eq 'run') { & $Godot --path $Demo res://transition_main.tscn; exit $LASTEXITCODE }
if ($Action -eq 'export') {
    if (-not $Output) { throw 'Supply -Output with a new build subdirectory; previous candidates are preserved.' }
    & $Python (Join-Path $PSScriptRoot 'export_transition.py') --output $Output
    exit $LASTEXITCODE
}
$PriorAppData=$env:APPDATA; $PriorTemp=$env:TEMP; $PriorTmp=$env:TMP
try {
    $env:APPDATA=Join-Path $Reports 'appdata';$env:TEMP=Join-Path $Reports 'test-temp';$env:TMP=$env:TEMP
    New-Item -ItemType Directory -Force -Path $env:APPDATA,$env:TEMP | Out-Null
    foreach ($Test in @('core','ui','input')) {
        $Log=Join-Path $Reports ('test-transition-'+$Test+'.log')
        & $Godot --headless --path $Demo --script ('res://tests/test_transition_'+$Test+'.gd') *> $Log
        if ($LASTEXITCODE -ne 0 -or (Get-Content -LiteralPath $Log -Raw) -match 'SCRIPT ERROR:|ERROR:|Parse Error:') { throw ('Transition test failed: '+$Log) }
    }
    & $Python -m unittest discover -s (Join-Path $PcRoot 'tests') -p 'test_transition_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Transition Python tests failed.' }
    Write-Output 'Transition functional checks passed. No performance measurement executed.'
} finally { $env:APPDATA=$PriorAppData;$env:TEMP=$PriorTemp;$env:TMP=$PriorTmp }

