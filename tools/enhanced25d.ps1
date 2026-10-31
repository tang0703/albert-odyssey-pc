param([ValidateSet('run','test','export')][string]$Action='run',[string]$Output)
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$ToolsRoot=Join-Path (Split-Path -Parent $Root) 'tools/pc-remake'
$Godot=Join-Path $ToolsRoot 'godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Python=Join-Path $ToolsRoot 'python/Scripts/python.exe'
if ($Action -eq 'run') { & $Godot --path (Join-Path $Root 'exploration-demo') res://enhanced25d_main.tscn; exit $LASTEXITCODE }
if ($Action -eq 'export') {
    if (-not $Output) {throw 'Supply a new build subdirectory.'}
    & $Python (Join-Path $PSScriptRoot 'export_enhanced25d.py') export --output $Output; exit $LASTEXITCODE
}
$Previous=$env:APPDATA
try {
    $env:APPDATA=Join-Path $Root 'reports/enhanced25d/appdata'
    foreach ($Name in @('loader','ui')) {
        $Log=Join-Path $Root ('reports/enhanced25d/test-'+$Name+'.log')
        & $Godot --headless --path (Join-Path $Root 'exploration-demo') --script ('res://tests/test_enhanced25d_'+$Name+'.gd') *> $Log
        if ($LASTEXITCODE -ne 0 -or (Get-Content -LiteralPath $Log -Raw) -match 'SCRIPT ERROR:|ERROR:|Parse Error:') {throw ('Failed: '+$Log)}
    }
    & $Python -X utf8 -m unittest discover -s (Join-Path $Root 'tests') -p 'test_enhanced25d_*.py' -v
    if ($LASTEXITCODE -ne 0) {throw '2.5D Python checks failed'}
} finally {$env:APPDATA=$Previous}
