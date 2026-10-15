param([ValidateSet('verify','test','export','run')][string]$Action='run',[string]$Output='')
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $PcRoot
$Godot=Join-Path $Workspace 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Python=Join-Path $Workspace 'tools/pc-remake/python/Scripts/python.exe'
$Demo=Join-Path $PcRoot 'exploration-demo'
$Reports=Join-Path $PcRoot 'reports/event'
function Checked([string]$Exe,[string[]]$Arguments,[string]$Name) {
    $Log=Join-Path $Reports ($Name+'.log')
    & $Exe @Arguments *> $Log
    if ($LASTEXITCODE -ne 0 -or (Get-Content -Raw -LiteralPath $Log) -match 'SCRIPT ERROR:|ERROR:|Parse Error:') { Get-Content -LiteralPath $Log -Tail 30; throw ('Event command failed: '+$Name) }
}
Push-Location -LiteralPath $PcRoot
try {
    Checked $Python @('tools/event_bundle.py','verify') 'entry-verify'
    if ($Action -eq 'verify') { return }
    if ($Action -eq 'run') { & $Godot --path $Demo res://event_main.tscn;return }
    if ($Action -eq 'test') {
        foreach ($Name in @('core','ui')) {
            Checked $Godot @('--headless','--log-file',(Join-Path $Reports ('entry-'+$Name+'-engine.log')),'--path',$Demo,'--script',('res://tests/test_event_'+$Name+'.gd'),'--quit-after','600') ('entry-'+$Name)
        }
        Checked $Python @('-m','unittest','discover','-s','tests','-p','test_event*.py') 'entry-python'
        return
    }
    if (-not $Output) { $Output=Join-Path $PcRoot ('build/event-demo-'+[guid]::NewGuid().ToString('N')) }
    Checked $Python @('tools/export_event.py','--output',$Output) 'entry-export'
    Write-Output ('Event Windows candidate: '+$Output)
} finally { Pop-Location }
