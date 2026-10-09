param([ValidateSet('build','test','export','run')][string]$Action='run',[string]$Output='')
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $PcRoot
$Demo=Join-Path $PcRoot 'exploration-demo'
$Reports=Join-Path $PcRoot 'reports/room'
$Godot=Join-Path $Workspace 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Python=Join-Path $Workspace 'tools/pc-remake/python/Scripts/python.exe'
function Checked([string]$Exe,[string[]]$Arguments,[string]$Name) {
    $Log=Join-Path $Reports ($Name+'.log')
    & $Exe @Arguments *> $Log
    if ($LASTEXITCODE -ne 0 -or (Get-Content -Raw -LiteralPath $Log) -match 'SCRIPT ERROR:|ERROR:|Parse Error:') { Get-Content -LiteralPath $Log -Tail 25; throw ('Room command failed: '+$Name) }
}
Push-Location -LiteralPath $PcRoot
try {
    if ($Action -eq 'build') { Checked $Python @('tools/room_bundle.py','build') 'entry-build';return }
    Checked $Python @('tools/room_bundle.py','verify') 'entry-verify'
    if ($Action -eq 'run') { & $Godot --path $Demo res://room_main.tscn;return }
    if ($Action -eq 'test') {
        Checked $Godot @('--headless','--path',$Demo,'--script','res://tests/test_room_core.gd','--',('--fixtures='+(Join-Path $Reports 'reference.json')),('--flags='+(Join-Path $Demo 'generated/scene/flags.bin')),('--report='+(Join-Path $Reports 'entry-core.json'))) 'entry-core'
        Checked $Godot @('--headless','--path',$Demo,'--script','res://tests/test_room_ui.gd','--',('--report='+(Join-Path $Reports 'entry-ui.json'))) 'entry-ui'
        Checked $Python @('-m','unittest','discover','-s','tests','-p','test_room*.py','-v') 'entry-python'
        return
    }
    $Build=[IO.Path]::GetFullPath((Join-Path $PcRoot 'build'))
    if ((Get-Item -LiteralPath $Build).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Redirected build directory is forbidden.' }
    if (-not $Output) { $Output=Join-Path $Build ('room-demo-'+[guid]::NewGuid().ToString('N')) }
    $Output=[IO.Path]::GetFullPath($Output)
    if ([IO.Path]::GetDirectoryName($Output) -ne $Build -or (Test-Path -LiteralPath $Output)) { throw 'Use a new direct child of build; existing deliveries are never overwritten.' }
    New-Item -ItemType Directory -Path $Output | Out-Null
    Checked $Godot @('--headless','--path',$Demo,'--editor','--import','--quit') 'entry-import'
    Checked $Godot @('--headless','--path',$Demo,'--export-release','Windows Room Workbench',(Join-Path $Output 'MAP001-Room.exe')) 'entry-export'
    Checked $Python @('-c',"import sys,json;from pathlib import Path;sys.path.insert(0,'tools');import audit_room_package as a;Path('reports/room/export-allowlist.json').write_text(json.dumps({k:sorted(v) for k,v in a.BUNDLES.items()}))") 'export-allowlist'
    $Bundles=Get-Content -LiteralPath (Join-Path $Reports 'export-allowlist.json') -Raw | ConvertFrom-Json
    foreach ($Name in @('scene','character','character-hd','room')) {
        $Folder=Join-Path $Output $Name
        New-Item -ItemType Directory -Path $Folder | Out-Null
        foreach ($File in $Bundles.$Name) { Copy-Item -LiteralPath (Join-Path $Demo ('generated/'+$Name+'/'+$File)) -Destination (Join-Path $Folder $File) }
    }
    Copy-Item -LiteralPath (Join-Path $PcRoot 'docs/ROOM_README.md') -Destination (Join-Path $Output 'README.md')
    foreach ($Name in @('GODOT-LICENSE.txt','GODOT-COPYRIGHT.txt')) { Copy-Item -LiteralPath (Join-Path $PcRoot ('licenses/'+$Name)) -Destination (Join-Path $Output $Name) }
    foreach ($Number in 1..4) { Copy-Item -LiteralPath (Join-Path $PcRoot ('docs/ROOM_STAGE_R'+$Number+'.md')) -Destination $Output }
    Copy-Item -LiteralPath (Join-Path $Reports 'coverage.png') -Destination (Join-Path $Output 'room-coverage.png')
    @{schema='ao_pc_room_acceptance_v1';passed=$false;status='candidate_pending_R5'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Output 'ROOM_VALIDATION.json') -Encoding utf8
    $Safe='safe.directory='+$PcRoot.Replace('\','/')
    $Commit=(& git -c $Safe rev-parse HEAD).Trim()
    $Changes=@(& git -c $Safe status --porcelain)
    $Arguments=@('tools/audit_room_package.py','build-info',$Output,'--commit',$Commit,'--report',(Join-Path $Reports 'candidate-audit.json'))
    if ($Changes.Count) { $Arguments+='--dirty' }
    Checked $Python $Arguments 'entry-audit'
    @{directory=$Output;executable=(Join-Path $Output 'MAP001-Room.exe');source_commit=$Commit;dirty=($Changes.Count -gt 0)} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Reports 'candidate.json') -Encoding utf8
    Write-Output ('Room Windows candidate: '+$Output)
} finally { Pop-Location }
