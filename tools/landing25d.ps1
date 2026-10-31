param([ValidateSet('run','test')][string]$Action='run')
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Godot=Join-Path (Split-Path -Parent $Root) 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
if ($Action -eq 'run') { & $Godot --path (Join-Path $Root 'exploration-demo') res://landing25d_main.tscn; exit $LASTEXITCODE }
$Prior=$env:APPDATA
try {
    $env:APPDATA=Join-Path $Root 'reports/enhanced25d-landing/appdata'
    New-Item -ItemType Directory -Force -Path $env:APPDATA | Out-Null
    foreach ($Name in @('animation','loader','ui','input')) {
        $Log=Join-Path $Root ('reports/enhanced25d-landing/test-'+$Name+'.log')
        & $Godot --headless --path (Join-Path $Root 'exploration-demo') --script ('res://tests/test_landing25d_'+$Name+'.gd') *> $Log
        if ($LASTEXITCODE -ne 0 -or (Get-Content -LiteralPath $Log -Raw) -match 'SCRIPT ERROR:|ERROR:|Parse Error:') { throw ('Failed '+$Log) }
    }
    'Landing 2.5D functional checks passed; no performance test.'
} finally {$env:APPDATA=$Prior}
