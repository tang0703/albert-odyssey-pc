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
    $Tests=@(Get-ChildItem -LiteralPath (Join-Path $Demo 'tests') -Filter 'test_*.gd' | Sort-Object Name | ForEach-Object { $_.BaseName }) + @('timing')
    foreach ($Test in $Tests) {
        Checked @('--headless','--path',$Demo,'--script',("res://tests/"+$Test+'.gd')) ("battle-"+$Test)
    }
    & (Join-Path $Workspace 'tools/pc-remake/python/Scripts/python.exe') -m unittest discover -s (Join-Path $PcRoot 'tests') -p 'test_battle_package.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Battle package regression tests failed.' }
    & (Join-Path $PcRoot 'tests/test_battle_qa.ps1')
    Write-Output 'Battle core, UI, presentation, timing and package checks passed.'
    exit
}
$Output=Join-Path $PcRoot 'build/battle-demo'
New-Item -ItemType Directory -Force $Output | Out-Null
Checked @('--headless','--path',$Demo,'--export-release','Windows Battle Demo') 'battle-export'
& (Join-Path $Workspace 'tools/pc-remake/python/Scripts/python.exe') (Join-Path $PSScriptRoot 'audit_battle_package.py')
if ($LASTEXITCODE -ne 0) { throw 'Battle package audit failed.' }
Copy-Item -LiteralPath (Join-Path $Demo 'README.md') -Destination (Join-Path $Output 'README.md')
Copy-Item -LiteralPath (Join-Path $PcRoot 'licenses/GODOT-LICENSE.txt') -Destination $Output
Copy-Item -LiteralPath (Join-Path $PcRoot 'licenses/GODOT-COPYRIGHT.txt') -Destination $Output
Checked @('--headless','--path',$PcRoot,'--log-file',(Join-Path $Reports 'battle-preview-engine.log'),'--script','res://tools/preview_battle_animations.gd') 'battle-preview-build'
Copy-Item -LiteralPath (Join-Path $Reports 'character-animation-preview.html') -Destination (Join-Path $Output 'Animation-Preview.html')
Copy-Item -LiteralPath (Join-Path $PcRoot 'licenses/BATTLE-ART-NOTICE.txt') -Destination $Output
Copy-Item -LiteralPath (Join-Path $PcRoot 'docs/BATTLE_DEMO_ROUND2.md') -Destination (Join-Path $Output 'ROUND2-ACCEPTANCE.md')
$SourceCommit=(& git -c ('safe.directory='+$PcRoot.Replace('\','/')) -C $PcRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot record source commit.' }
$SourceDirty=[bool](& git -c ('safe.directory='+$PcRoot.Replace('\','/')) -C $PcRoot status --porcelain --untracked-files=normal)
$BuildInfo=[ordered]@{schema='battle_demo_build_v1';source_commit=$SourceCommit;source_has_uncommitted_changes=$SourceDirty;godot='4.7.2';built_utc=(Get-Date).ToUniversalTime().ToString('o');files=@()}
$Required=@('Triad-Trial.exe','Triad-Trial.pck','README.md','GODOT-LICENSE.txt','GODOT-COPYRIGHT.txt','Animation-Preview.html','BATTLE-ART-NOTICE.txt','ROUND2-ACCEPTANCE.md')
foreach ($Name in $Required) {
    if (-not (Test-Path -LiteralPath (Join-Path $Output $Name) -PathType Leaf)) { throw ('Missing delivery file: '+$Name) }
}
$Allowed=$Required+@('Triad-Trial.console.exe','BUILD-INFO.json')
$Unexpected=Get-ChildItem -LiteralPath $Output | Where-Object { $_.Name -notin $Allowed }
if ($Unexpected) { throw 'Unexpected files in battle package; review before packaging.' }
foreach ($File in Get-ChildItem -LiteralPath $Output -File | Where-Object { $_.Name -ne 'BUILD-INFO.json' } | Sort-Object Name) {
    $BuildInfo.files+=@{path=$File.Name;bytes=$File.Length;sha256=(Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$BuildInfo | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $Output 'BUILD-INFO.json')
$Zip=Join-Path $PcRoot 'build/Triad-Trial-Windows-x64.zip'
Compress-Archive -Path (Join-Path $Output '*') -DestinationPath $Zip -Force
$VerificationRoot=Join-Path $PcRoot ('build/zip-check-'+[guid]::NewGuid().ToString('N'))
try {
    Expand-Archive -LiteralPath $Zip -DestinationPath $VerificationRoot
    $ExpectedFiles=@(Get-ChildItem -LiteralPath $Output -File | Sort-Object Name)
    $ExtractedFiles=@(Get-ChildItem -LiteralPath $VerificationRoot -File | Sort-Object Name)
    if (($ExpectedFiles.Name -join '|') -ne ($ExtractedFiles.Name -join '|')) { throw 'ZIP file list differs from audited delivery.' }
    foreach ($File in $ExpectedFiles) {
        if ((Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath (Join-Path $VerificationRoot $File.Name) -Algorithm SHA256).Hash) {
            throw ('ZIP extraction content mismatch: '+$File.Name)
        }
    }
    $ZipAudit=[ordered]@{schema='battle_demo_zip_audit_v1';zip_sha256=(Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant();source_commit=$SourceCommit;source_has_uncommitted_changes=$SourceDirty;extraction_verified=$true;files=$BuildInfo.files}
    $ZipAudit | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $Reports 'battle-zip.json')
} finally {
    # Delete only this invocation's verified, generated extraction directory.
    $ResolvedVerification=[IO.Path]::GetFullPath($VerificationRoot)
    $ExpectedParent=[IO.Path]::GetFullPath((Join-Path $PcRoot 'build'))
    if ([IO.Path]::GetDirectoryName($ResolvedVerification) -eq $ExpectedParent -and [IO.Path]::GetFileName($ResolvedVerification).StartsWith('zip-check-') -and (Test-Path -LiteralPath $ResolvedVerification)) {
        Remove-Item -LiteralPath $ResolvedVerification -Recurse -Force
    }
}
Write-Output ('Battle ZIP extracted and verified: '+$ZipAudit.zip_sha256)
