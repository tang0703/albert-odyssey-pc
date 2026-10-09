param(
    [ValidateSet('build','hd-build','test','gpu-test','export','run')][string]$Action='run',
    [string]$ArtManifest='', [string]$ArtSha256='', [string]$ZipPath=''
)
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $PcRoot
$Demo=Join-Path $PcRoot 'exploration-demo'
$Reports=Join-Path $PcRoot 'reports/character'
$Godot=Join-Path $Workspace 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Python=Join-Path $Workspace 'tools/pc-remake/python/Scripts/python.exe'

function CheckedPython([string[]]$Arguments,[string]$Name) {
    $Log=Join-Path $Reports ($Name+'.log')
    & $Python @Arguments *> $Log
    if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $Log -Tail 35; throw "Character Python command failed: $Name" }
}
function CheckedGodot([string[]]$Arguments,[string]$Name) {
    $Log=Join-Path $Reports ($Name+'.log')
    & $Godot --log-file (Join-Path $Reports ($Name+'-engine.log')) @Arguments *> $Log
    if ($LASTEXITCODE -ne 0 -or (Get-Content -LiteralPath $Log -Raw) -match 'SCRIPT ERROR:|ERROR:|Parse Error:|Assertion failed|Failed to load script') {
        Get-Content -LiteralPath $Log -Tail 35
        throw "Character Godot command failed: $Name"
    }
}
function ReadCharacterPin([string]$Name,[string]$Schema,[string[]]$Hashes) {
    $Path=Join-Path $Demo $Name
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw ('Approved local pin is missing: '+$Name+'. Build the actual approved package first.') }
    $Pin=Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($Pin.schema -cne $Schema) { throw ('Invalid local pin schema: '+$Name) }
    $Keys=@($Pin.PSObject.Properties.Name | Sort-Object)
    $Expected=@(@('schema')+$Hashes | Sort-Object)
    if (($Keys -join '|') -cne ($Expected -join '|')) { throw ('Unexpected pin fields: '+$Name) }
    foreach ($Key in $Hashes) { if ($Pin.$Key -isnot [string] -or $Pin.$Key -cnotmatch '^[0-9a-f]{64}$') { throw ('Invalid pin hash: '+$Name+'/'+$Key) } }
    return $Pin
}
function VerifyBundle {
    $Scene=ReadCharacterPin 'bundle-pin.json' 'ao_pc_exploration_bundle_pin_v1' @('manifest_sha256')
    $Pin=ReadCharacterPin 'character-pin.json' 'ao_pc_character_bundle_pin_v1' @('manifest_sha256','scene_manifest_sha256')
    if ($Pin.scene_manifest_sha256 -cne $Scene.manifest_sha256) { throw 'Character and scene pins disagree.' }
    CheckedPython @((Join-Path $PSScriptRoot 'character_bundle.py'),'verify',(Join-Path $Demo 'generated/character'),
        '--manifest-sha256',$Pin.manifest_sha256,'--scene',(Join-Path $Demo 'generated/scene'),
        '--scene-manifest-sha256',$Pin.scene_manifest_sha256) 'entry-bundle-verify'
}
function VerifyHdBundle {
    $Scene=ReadCharacterPin 'bundle-pin.json' 'ao_pc_exploration_bundle_pin_v1' @('manifest_sha256')
    $Source=ReadCharacterPin 'character-pin.json' 'ao_pc_character_bundle_pin_v1' @('manifest_sha256','scene_manifest_sha256')
    $Pin=ReadCharacterPin 'character-hd-pin.json' 'ao_pc_character_hd_bundle_pin_v1' @('manifest_sha256','scene_manifest_sha256','source_character_manifest_sha256')
    if ($Pin.scene_manifest_sha256 -cne $Scene.manifest_sha256 -or $Source.scene_manifest_sha256 -cne $Scene.manifest_sha256 -or $Pin.source_character_manifest_sha256 -cne $Source.manifest_sha256) { throw 'HD, original character and scene pins disagree.' }
    CheckedPython @((Join-Path $PSScriptRoot 'character_hd_bundle.py'),'verify',(Join-Path $Demo 'generated/character-hd'),
        '--manifest-sha256',$Pin.manifest_sha256,'--scene',(Join-Path $Demo 'generated/scene'),
        '--scene-manifest-sha256',$Pin.scene_manifest_sha256,'--source-character',(Join-Path $Demo 'generated/character'),
        '--source-character-manifest-sha256',$Pin.source_character_manifest_sha256) 'entry-hd-bundle-verify'
}
function ValidateArtArguments {
    if ([string]::IsNullOrWhiteSpace($ArtManifest) -or $ArtSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'HD build requires -ArtManifest and its explicit approved -ArtSha256.' }
    if (-not (Test-Path -LiteralPath $ArtManifest -PathType Leaf)) { throw 'Actual approved 52-frame art manifest is missing.' }
}
function BuildHdBundle {
    ValidateArtArguments
    CheckedPython @((Join-Path $PSScriptRoot 'character_hd_bundle.py'),'build','--art-manifest',([IO.Path]::GetFullPath($ArtManifest)),
        '--art-sha256',$ArtSha256) 'entry-hd-bundle-build'
    VerifyHdBundle
}
function RunCharacterTests {
    $Fixtures=Join-Path $Reports 'animation-fixtures.json'
    if (-not (Test-Path -LiteralPath $Fixtures -PathType Leaf)) { throw 'Formal original-capture animation fixtures are required; source acceptance cannot be skipped.' }
    CheckedGodot @('--headless','--path',$Demo,'--editor','--import','--quit') 'entry-import'
    foreach ($Name in @('test_character_animation','test_character_loader','test_character_hd','test_character_ui')) {
        $Arguments=@('--headless','--path',$Demo,'--script',('res://tests/'+$Name+'.gd'),'--',('--fixtures='+$Fixtures))
        if ($Name -eq 'test_character_animation') {
            $Arguments+=@(('--movement-profile='+(Join-Path $Demo 'generated/scene/profile.json')),
                ('--wram-low='+(Join-Path $Reports 'cardinal-a/frame-000000/wram-low.bin')),
                ('--report='+(Join-Path $Reports 'entry-animation-validation.json')))
        }
        if ($Name -eq 'test_character_loader') {
            $Pin=ReadCharacterPin 'character-pin.json' 'ao_pc_character_bundle_pin_v1' @('manifest_sha256','scene_manifest_sha256')
            $Arguments+=@(('--bundle='+(Join-Path $Demo 'generated/character')),('--manifest-sha256='+$Pin.manifest_sha256),
                ('--scene-manifest-sha256='+$Pin.scene_manifest_sha256),('--report='+(Join-Path $Reports 'entry-loader-validation.json')))
        }
        if ($Name -eq 'test_character_hd') { $Arguments+=('--report='+(Join-Path $Reports 'entry-hd-validation.json')) }
        if ($Name -eq 'test_character_ui') { $Arguments+=('--report='+(Join-Path $Reports 'entry-ui-validation.json')) }
        CheckedGodot $Arguments ('entry-'+$Name)
    }
    $HD=Get-Content -LiteralPath (Join-Path $Reports 'entry-hd-validation.json') -Raw | ConvertFrom-Json
    if ($HD.passed -ne $true -or $HD.source_comparison_status -ne 'passed' -or $HD.source_updates -le 0) { throw 'HD selector did not run and pass original source comparison.' }
    $UILog=Get-Content -LiteralPath (Join-Path $Reports 'entry-test_character_ui.log') -Raw
    if ($UILog -notmatch '(?m)^CHARACTER_UI_HD_STATUS=passed\s*$') { throw 'Actual HD entry/UI parity acceptance is missing; synthetic HD tests cannot replace it.' }
    $UI=Get-Content -LiteralPath (Join-Path $Reports 'entry-ui-validation.json') -Raw | ConvertFrom-Json
    if ($UI.schema -cne 'ao_pc_character_ui_tests_v2' -or $UI.passed -isnot [bool] -or -not $UI.passed -or $UI.hd_package_status -cne 'passed' -or $UI.source_updates -ne 6156 -or ($UI.modes -join '|') -cne 'hd|original|marker' -or $UI.synthetic_hd_package -isnot [bool] -or $UI.synthetic_hd_package) { throw 'Actual-HD UI report lacks all three source modes or uses synthetic assets.' }
    foreach ($Name in @('test_character_animation.py','test_character_bundle.py','test_character_draw_order.py','test_character_scene_props.py',
        'test_character_runtime_pixels.py','test_character_hd_art.py','test_character_hd_bundle.py','test_character_package.py')) {
        CheckedPython @('-m','unittest','discover','-s','tests','-p',$Name,'-v') ('entry-'+[IO.Path]::GetFileNameWithoutExtension($Name))
    }
    foreach ($Name in @('test_character_qa.ps1','test_character_entry.ps1','test_character_environment_probe.ps1')) {
        & (Join-Path $PcRoot ('tests/'+$Name)) *> (Join-Path $Reports ('entry-'+$Name+'.log'))
    }
    Write-Output 'Character source/core/actual-HD/UI and package contract tests passed. GPU composition and performance remain separate acceptance.'
}
function GetCharacterExportInputs {
    $Paths=@('exploration-demo/project.godot','exploration-demo/export_presets.cfg','exploration-demo/character_main.tscn',
        'exploration-demo/character_priority.gdshader','exploration-demo/bundle-pin.json','exploration-demo/character-pin.json','exploration-demo/character-hd-pin.json',
        'tools/character.ps1','tools/audit_character_package.py','tools/character_hd_bundle.py','tools/character_bundle.py','tools/exploration_bundle.py')
    foreach ($Name in @('main','movement_core','package_loader','character_main','character_animation_core','character_loader','character_layer','character_hd_animation','character_hd_loader')) { $Paths+=('exploration-demo/'+$Name+'.gd') }
    $Rows=@(foreach ($Path in $Paths) {
        $File=Get-Item -LiteralPath (Join-Path $PcRoot $Path)
        [ordered]@{path=$Path;bytes=$File.Length;sha256=(Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    })
    return (ConvertTo-Json -InputObject $Rows -Depth 6 -Compress)
}
function GetCharacterRevision {
    $Safe='safe.directory='+$PcRoot.Replace('\','/')
    $Commit=(& git -c $Safe -C $PcRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $Commit -cnotmatch '^[0-9a-f]{40}$') { throw 'Cannot record source commit.' }
    $Changes=@(& git -c $Safe -C $PcRoot status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record source working tree state.' }
    return [pscustomobject]@{commit=$Commit;dirty=($Changes.Count -gt 0);status=$Changes}
}
function GetCharacterExportPaths {
    $BuildRoot=[IO.Path]::GetFullPath((Join-Path $PcRoot 'build'))
    $Archive=if ([string]::IsNullOrWhiteSpace($ZipPath)) { Join-Path $BuildRoot 'MAP001-Character-Windows-x64.zip' } else { [IO.Path]::GetFullPath($ZipPath) }
    if ([IO.Path]::GetDirectoryName($Archive) -ne $BuildRoot -or [IO.Path]::GetExtension($Archive) -cne '.zip') { throw 'Character ZIP must be a direct .zip file in this repository build directory.' }
    if (Test-Path -LiteralPath $Archive) { throw 'Use a new -ZipPath; previous ZIP deliveries must be preserved.' }
    if (Test-Path -LiteralPath $BuildRoot) {
        if ((Get-Item -LiteralPath $BuildRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Redirected build directory is forbidden.' }
    }
    $RunId=[guid]::NewGuid().ToString('N')
    $Final=Join-Path $BuildRoot 'character-demo'
    if (Test-Path -LiteralPath $Final) { $Final=Join-Path $BuildRoot ('character-demo-'+$RunId) }
    return [pscustomobject]@{build=$BuildRoot;output=(Join-Path $BuildRoot ('character-staging-'+$RunId));final=$Final;
        zip=$Archive;extraction=(Join-Path $BuildRoot ('character-zip-check-'+$RunId))}
}
function PublishCharacterDirectory($Paths) {
    # Same-volume, no-overwrite rename after both package and ZIP audits passed.
    $Build=[IO.Path]::GetFullPath((Join-Path $PcRoot 'build'))
    $Stage=[IO.Path]::GetFullPath($Paths.output)
    $Final=[IO.Path]::GetFullPath($Paths.final)
    if ([IO.Path]::GetFullPath($Paths.build) -ne $Build -or [IO.Path]::GetDirectoryName($Stage) -ne $Build -or [IO.Path]::GetDirectoryName($Final) -ne $Build -or
        [IO.Path]::GetFileName($Stage) -cnotmatch '^character-staging-[0-9a-f]{32}$' -or [IO.Path]::GetFileName($Final) -cnotmatch '^character-demo(?:-[0-9a-f]{32})?$') { throw 'Release promotion paths escape the intended build directory.' }
    foreach ($Path in @($Build,$Stage)) {
        $Entry=Get-Item -LiteralPath $Path
        if (-not $Entry.PSIsContainer -or ($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Redirected or non-directory release promotion path.' }
    }
    if (Test-Path -LiteralPath $Final) { throw 'Final release directory already exists; staged release is retained without overwriting it.' }
    [IO.Directory]::Move($Stage,$Final)
}
function ExportCharacter {
    # Existing packages only. Original sources are never rebuilt during export.
    $Paths=GetCharacterExportPaths
    $Before=GetCharacterExportInputs
    $Revision=GetCharacterRevision
    RunCharacterTests
    if ((GetCharacterExportInputs) -cne $Before) { throw 'Export inputs changed while testing; rerun against a stable source version.' }
    $Documents=[ordered]@{
        'README.md'=(Join-Path $PcRoot 'docs/CHARACTER_README.md')
        'GODOT-LICENSE.txt'=(Join-Path $PcRoot 'licenses/GODOT-LICENSE.txt')
        'GODOT-COPYRIGHT.txt'=(Join-Path $PcRoot 'licenses/GODOT-COPYRIGHT.txt')
        'CHARACTER_DELIVERY.md'=(Join-Path $PcRoot 'docs/CHARACTER_DELIVERY.md')
        'CHARACTER_STAGE_A2.md'=(Join-Path $PcRoot 'docs/CHARACTER_STAGE_A2.md')
        'CHARACTER_ANIMATION_MODEL.md'=(Join-Path $PcRoot 'docs/CHARACTER_ANIMATION_MODEL.md')
    }
    foreach ($Source in $Documents.Values) { if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw ('Required delivery document is missing: '+$Source) } }
    CheckedPython @('-c',"import sys,json;from pathlib import Path;sys.path.insert(0,'tools');import audit_character_package as a;Path('reports/character/entry-export-allowlist.json').write_text(json.dumps({k:sorted(v) for k,v in a.BUNDLES.items()}),encoding='utf-8')") 'entry-export-allowlist'
    $Bundles=Get-Content -LiteralPath (Join-Path $Reports 'entry-export-allowlist.json') -Raw | ConvertFrom-Json
    if (@($Bundles.scene).Count -ne 6 -or @($Bundles.character).Count -ne 33 -or @($Bundles.'character-hd').Count -ne 58) { throw 'Unexpected approved bundle contract.' }
    if (Test-Path -LiteralPath $Paths.output) { throw 'Fresh staging directory unexpectedly exists; nothing will be overwritten.' }
    New-Item -ItemType Directory -Force -Path $Paths.build | Out-Null
    New-Item -ItemType Directory -Path $Paths.output | Out-Null
    CheckedGodot @('--headless','--path',$Demo,'--editor','--import','--quit') 'entry-export-import'
    CheckedGodot @('--headless','--path',$Demo,'--export-release','Windows Character Workbench',(Join-Path $Paths.output 'MAP001-Character.exe')) 'entry-export'
    VerifyHdBundle
    foreach ($Name in @('scene','character','character-hd')) {
        $Folder=Join-Path $Paths.output $Name
        New-Item -ItemType Directory -Force -Path $Folder | Out-Null
        foreach ($Payload in $Bundles.$Name) { Copy-Item -LiteralPath (Join-Path $Demo ('generated/'+$Name+'/'+$Payload)) -Destination (Join-Path $Folder $Payload) -Force }
    }
    foreach ($Name in $Documents.Keys) { Copy-Item -LiteralPath $Documents[$Name] -Destination (Join-Path $Paths.output $Name) -Force }
    $AfterRevision=GetCharacterRevision
    if ((GetCharacterExportInputs) -cne $Before -or $Revision.commit -cne $AfterRevision.commit -or $Revision.dirty -ne $AfterRevision.dirty -or ($Revision.status -join [Environment]::NewLine) -cne ($AfterRevision.status -join [Environment]::NewLine)) { throw 'Source identity changed during export; package cannot be sealed.' }
    $Before | Set-Content -LiteralPath (Join-Path $Reports 'entry-export-inputs.json') -Encoding utf8
    $Dirty=if ($Revision.dirty) { 'true' } else { 'false' }
    $Audit=Join-Path $PSScriptRoot 'audit_character_package.py'
    $PinArgs=@('--scene-pin',(Join-Path $Demo 'bundle-pin.json'),'--character-pin',(Join-Path $Demo 'character-pin.json'),'--hd-pin',(Join-Path $Demo 'character-hd-pin.json'))
    CheckedPython (@($Audit,'build-info','--delivery',$Paths.output,'--source-commit',$Revision.commit,'--dirty',$Dirty,
        '--report',(Join-Path $Reports 'entry-package-audit.json'))+$PinArgs) 'entry-package-audit'
    CheckedPython (@($Audit,'zip','--delivery',$Paths.output,'--zip',$Paths.zip,'--extract-to',$Paths.extraction,
        '--report',(Join-Path $Reports 'entry-zip-audit.json'))+$PinArgs) 'entry-zip-audit'
    PublishCharacterDirectory $Paths
    Write-Output ('Verified release directory: '+$Paths.final)
    Write-Output ('Windows character ZIP verified: '+$Paths.zip)
    Write-Output ('Verified extraction retained for independent cold-start/QA: '+$Paths.extraction)
}
function InvokeCharacterAction {
    if ($Action -notin @('build','hd-build') -and (-not [string]::IsNullOrWhiteSpace($ArtManifest) -or -not [string]::IsNullOrWhiteSpace($ArtSha256))) { throw 'Art approval arguments are accepted only for build or hd-build.' }
    if ($Action -ne 'export' -and -not [string]::IsNullOrWhiteSpace($ZipPath)) { throw '-ZipPath applies only to export.' }
    if ($Action -eq 'build') {
        $WithHD=(-not [string]::IsNullOrWhiteSpace($ArtManifest) -or -not [string]::IsNullOrWhiteSpace($ArtSha256))
        if ($WithHD) { ValidateArtArguments }
        CheckedPython @((Join-Path $PSScriptRoot 'character_bundle.py'),'build') 'entry-bundle-build'
        if ($WithHD) { BuildHdBundle }
        Write-Output 'Source-bound character package built. HD is built only when explicit approved art arguments are supplied.'
        return
    }
    VerifyBundle
    if ($Action -eq 'hd-build') { BuildHdBundle; return }
    if ($Action -eq 'gpu-test') {
        $Pixels=Join-Path $Reports 'runtime-pixel-fixtures.json'
        if (-not (Test-Path -LiteralPath $Pixels -PathType Leaf)) { throw 'Source video pixel fixtures are required; do not substitute synthetic cases for source acceptance.' }
        CheckedGodot @('--path',$Demo,'--script','res://tests/test_character_compositor.gd','--',
            ('--fixtures='+$Pixels),('--report='+(Join-Path $Reports 'entry-gpu-validation.json'))) 'entry-gpu'
        $Result=Get-Content -LiteralPath (Join-Path $Reports 'entry-gpu-validation.json') -Raw | ConvertFrom-Json
        if (-not $Result.passed -or $Result.source_fixture_status -ne 'passed') { throw 'Real GPU source validation did not pass.' }
        Write-Output 'Real GPU synthetic and original-video character pixel comparisons passed; this is not an HD performance soak.'
        return
    }
    VerifyHdBundle
    if ($Action -eq 'run') { CheckedGodot @('--path',$Demo,'res://character_main.tscn') 'entry-run'; return }
    if ($Action -eq 'test') { RunCharacterTests; return }
    ExportCharacter
}

# Dot-source exposes only functions for process-free contract tests.
if ($MyInvocation.InvocationName -eq '.') { return }
$PriorAppData=$env:APPDATA; $PriorTemp=$env:TEMP; $PriorTmp=$env:TMP
Push-Location -LiteralPath $PcRoot
try {
    $env:APPDATA=Join-Path $Reports 'entry-appdata'
    $env:TEMP=Join-Path $PcRoot 'reports/tmp'; $env:TMP=$env:TEMP
    New-Item -ItemType Directory -Force -Path $Reports,$env:APPDATA,$env:TEMP | Out-Null
    InvokeCharacterAction
} finally {
    $env:APPDATA=$PriorAppData; $env:TEMP=$PriorTemp; $env:TMP=$PriorTmp
    Pop-Location
}
