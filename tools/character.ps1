param([ValidateSet('build','test','gpu-test','run')][string]$Action='run')
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $PcRoot
$Demo=Join-Path $PcRoot 'exploration-demo'
$Reports=Join-Path $PcRoot 'reports/character'
$Godot=Join-Path $Workspace 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Python=Join-Path $Workspace 'tools/pc-remake/python/Scripts/python.exe'
$PriorAppData=$env:APPDATA
$PriorTemp=$env:TEMP
$PriorTmp=$env:TMP
New-Item -ItemType Directory -Force -Path $Reports | Out-Null

function CheckedPython([string[]]$Arguments,[string]$Name) {
    $Log=Join-Path $Reports ($Name+'.log')
    & $Python @Arguments *> $Log
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $Log -Tail 35
        throw "Character Python command failed: $Name"
    }
}
function CheckedGodot([string[]]$Arguments,[string]$Name) {
    $Log=Join-Path $Reports ($Name+'.log')
    & $Godot --log-file (Join-Path $Reports ($Name+'-engine.log')) @Arguments *> $Log
    if ($LASTEXITCODE -ne 0 -or (Get-Content -LiteralPath $Log -Raw) -match 'SCRIPT ERROR:|ERROR:|Parse Error:|Assertion failed|Failed to load script') {
        Get-Content -LiteralPath $Log -Tail 35
        throw "Character Godot command failed: $Name"
    }
}
function VerifyBundle {
    $PinPath=Join-Path $Demo 'character-pin.json'
    if (-not (Test-Path -LiteralPath $PinPath -PathType Leaf)) { throw 'Approved local character package is missing. Run character.ps1 build after source evidence is complete.' }
    $Pin=Get-Content -LiteralPath $PinPath -Raw | ConvertFrom-Json
    if ($Pin.schema -ne 'ao_pc_character_bundle_pin_v1') { throw 'Invalid local character pin.' }
    CheckedPython @((Join-Path $PSScriptRoot 'character_bundle.py'),'verify',(Join-Path $Demo 'generated/character'),
        '--manifest-sha256',$Pin.manifest_sha256,'--scene-manifest-sha256',$Pin.scene_manifest_sha256) 'entry-bundle-verify'
}

Push-Location -LiteralPath $PcRoot
try {
    $env:APPDATA=Join-Path $Reports 'entry-appdata'
    $env:TEMP=Join-Path $PcRoot 'reports/tmp'
    $env:TMP=$env:TEMP
    New-Item -ItemType Directory -Force -Path $env:APPDATA,$env:TEMP | Out-Null
    if ($Action -eq 'build') {
        CheckedPython @((Join-Path $PSScriptRoot 'character_bundle.py'),'build') 'entry-bundle-build'
        Write-Output 'Source-bound character package built. Source captures, draw-order and presentation approvals are required.'
        return
    }
    VerifyBundle
    if ($Action -eq 'run') {
        CheckedGodot @('--path',$Demo,'res://character_main.tscn') 'entry-run'
        return
    }
    if ($Action -eq 'gpu-test') {
        $Pixels=Join-Path $Reports 'runtime-pixel-fixtures.json'
        if (-not (Test-Path -LiteralPath $Pixels -PathType Leaf)) { throw 'Source video pixel fixtures are required; do not substitute synthetic cases for source acceptance.' }
        CheckedGodot @('--path',$Demo,'--script','res://tests/test_character_compositor.gd','--',
            ('--fixtures='+$Pixels),('--report='+(Join-Path $Reports 'entry-gpu-validation.json'))) 'entry-gpu'
        $Result=Get-Content -LiteralPath (Join-Path $Reports 'entry-gpu-validation.json') -Raw | ConvertFrom-Json
        if (-not $Result.passed -or $Result.source_fixture_status -ne 'passed') { throw 'Real GPU source validation did not pass.' }
        Write-Output 'Real GPU synthetic and original-video character pixel comparisons passed; this is not a performance soak.'
        return
    }
    $Fixtures=Join-Path $Reports 'animation-fixtures.json'
    if (-not (Test-Path -LiteralPath $Fixtures -PathType Leaf)) { throw 'Formal original-capture animation fixtures are required; source acceptance cannot be skipped.' }
    CheckedGodot @('--headless','--path',$Demo,'--editor','--import','--quit') 'entry-import'
    foreach ($Name in @('test_character_animation','test_character_loader','test_character_ui')) {
        $Arguments=@('--headless','--path',$Demo,'--script',('res://tests/'+$Name+'.gd'),'--',('--fixtures='+$Fixtures))
        if ($Name -eq 'test_character_animation') {
            $Arguments+=@(('--movement-profile='+(Join-Path $Demo 'generated/scene/profile.json')),
                ('--wram-low='+(Join-Path $Reports 'cardinal-a/frame-000000/wram-low.bin')),
                ('--report='+(Join-Path $Reports 'entry-animation-validation.json')))
        }
        if ($Name -eq 'test_character_loader') {
            $Pin=Get-Content -LiteralPath (Join-Path $Demo 'character-pin.json') -Raw | ConvertFrom-Json
            $Arguments+=@(('--bundle='+(Join-Path $Demo 'generated/character')),
                ('--manifest-sha256='+$Pin.manifest_sha256),
                ('--scene-manifest-sha256='+$Pin.scene_manifest_sha256),
                ('--report='+(Join-Path $Reports 'entry-loader-validation.json')))
        }
        CheckedGodot $Arguments ('entry-'+$Name)
    }
    foreach ($Name in @('test_character_animation.py','test_character_bundle.py','test_character_draw_order.py','test_character_scene_props.py','test_character_runtime_pixels.py')) {
        CheckedPython @('-m','unittest','discover','-s','tests','-p',$Name,'-v') ('entry-'+[IO.Path]::GetFileNameWithoutExtension($Name))
    }
    Write-Output 'Character source/core/loader/UI tests passed. Real-GPU composition and visual acceptance are separate commands.'
} finally {
    $env:APPDATA=$PriorAppData
    $env:TEMP=$PriorTemp
    $env:TMP=$PriorTmp
    Pop-Location
}
