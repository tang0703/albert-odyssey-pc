param([ValidateSet('build','test','export','run')][string]$Action='run')
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $PcRoot
$Demo=Join-Path $PcRoot 'exploration-demo'
$Reports=Join-Path $PcRoot 'reports/exploration'
$Godot=Join-Path $Workspace 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Python=Join-Path $Workspace 'tools/pc-remake/python/Scripts/python.exe'
$Bundle=Join-Path $Demo 'generated/scene'
$PinPath=Join-Path $Demo 'bundle-pin.json'
New-Item -ItemType Directory -Force -Path $Reports | Out-Null

function CheckedPython([string[]]$Arguments,[string]$Name) {
    $Log=Join-Path $Reports ($Name+'.log')
    & $Python @Arguments *> $Log
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $Log -Tail 35
        throw "Exploration Python command failed: $Name"
    }
}
function CheckedGodot([string[]]$Arguments,[string]$Name) {
    $Log=Join-Path $Reports ($Name+'.log')
    $EngineLog=Join-Path $Reports ($Name+'-engine.log')
    & $Godot --log-file $EngineLog @Arguments *> $Log
    if ($LASTEXITCODE -ne 0 -or (Get-Content -LiteralPath $Log -Raw) -match 'SCRIPT ERROR:|ERROR:|Parse Error:|Assertion failed|Failed to load script') {
        Get-Content -LiteralPath $Log -Tail 35
        throw "Exploration Godot command failed: $Name"
    }
}
function BuildBundle {
    CheckedPython @((Join-Path $PSScriptRoot 'exploration_bundle.py'),'build') 'bundle-build'
}
function VerifyBundle {
    if (-not (Test-Path -LiteralPath $Bundle -PathType Container) -or -not (Test-Path -LiteralPath $PinPath -PathType Leaf)) {
        throw 'Local bundle or trusted pin is missing. Run exploration.ps1 build first; export never reconstructs original sources.'
    }
    $Pin=Get-Content -LiteralPath $PinPath -Raw | ConvertFrom-Json
    if ($Pin.schema -ne 'ao_pc_exploration_bundle_pin_v1' -or $Pin.manifest_sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw 'Invalid trusted bundle pin.'
    }
    CheckedPython @((Join-Path $PSScriptRoot 'exploration_bundle.py'),'verify',$Bundle,'--manifest-sha256',$Pin.manifest_sha256) 'bundle-verify'
}

Push-Location -LiteralPath $PcRoot
try {
    if ($Action -eq 'build') {
        BuildBundle
        Write-Output 'Source-pinned local exploration bundle built and verified.'
        return
    }
    if ($Action -eq 'test' -and -not (Test-Path -LiteralPath $Bundle -PathType Container)) { BuildBundle }
    if ($Action -eq 'run') {
        & $Godot --path $Demo --log-file (Join-Path $Reports 'run-engine.log')
        if ($LASTEXITCODE -ne 0) { throw 'Exploration workbench exited with an error.' }
        return
    }
    VerifyBundle
    if ($Action -eq 'test') {
        CheckedGodot @('--headless','--path',$Demo,'--editor','--import','--quit') 'test-import'
        $Tests=@(Get-ChildItem -LiteralPath (Join-Path $Demo 'tests') -Filter 'test_*.gd' -File | Sort-Object Name)
        if (-not ($Tests.Name -contains 'test_movement.gd')) { throw 'Required Godot movement test is missing.' }
        foreach ($Test in $Tests) {
            if ($Test.Name -in @('test_character_compositor.gd','test_character_hd_compositor.gd')) {
                Write-Output ('GPU-only validation is run separately with an actual renderer: '+$Test.Name)
                continue
            }
            $Arguments=@('--headless','--path',$Demo,'--script',('res://tests/'+$Test.Name))
            if ($Test.Name -eq 'test_movement.gd') {
                $Arguments+=@('--',('--profile='+(Join-Path $Reports 'player-profile.json')),
                    ('--fixtures='+(Join-Path $Reports 'player-replay-fixtures.json')),
                    ('--flags='+(Join-Path $Bundle 'flags.bin')),
                    ('--report='+(Join-Path $Reports 'godot-movement-validation.json')))
            }
            CheckedGodot $Arguments $Test.BaseName
        }
        foreach ($TestName in @('test_exploration_bundle.py','test_exploration_package.py')) {
            if (-not (Test-Path -LiteralPath (Join-Path $PcRoot ('tests/'+$TestName)) -PathType Leaf)) {
                throw ('Required Python test file is missing: '+$TestName)
            }
            CheckedPython @('-m','unittest','discover','-s',(Join-Path $PcRoot 'tests'),'-p',$TestName,'-v') ([IO.Path]::GetFileNameWithoutExtension($TestName))
        }
        $QaTest=Join-Path $PcRoot 'tests/test_exploration_qa.ps1'
        if (-not (Test-Path -LiteralPath $QaTest -PathType Leaf)) { throw 'Required QA acceptance fixture test is missing.' }
        & $QaTest *> (Join-Path $Reports 'qa-fixture-tests.txt')
        Write-Output 'Exploration Godot, bundle, package and QA acceptance tests passed.'
        return
    }

    # Export uses only the already-built six-file bundle and trusted pin.
    $Documents=[ordered]@{
        'README.md'=(Join-Path $Demo 'README.md')
        'GODOT-LICENSE.txt'=(Join-Path $PcRoot 'licenses/GODOT-LICENSE.txt')
        'GODOT-COPYRIGHT.txt'=(Join-Path $PcRoot 'licenses/GODOT-COPYRIGHT.txt')
        'EXPLORATION_MOVEMENT.md'=(Join-Path $PcRoot 'docs/EXPLORATION_MOVEMENT.md')
        'EXPLORATION_ACCEPTANCE.md'=(Join-Path $PcRoot 'docs/EXPLORATION_ACCEPTANCE.md')
    }
    foreach ($Source in $Documents.Values) {
        if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw ('Required delivery document is missing: '+$Source) }
    }
    $BuildRoot=[IO.Path]::GetFullPath((Join-Path $PcRoot 'build'))
    $Output=[IO.Path]::GetFullPath((Join-Path $BuildRoot 'exploration-demo'))
    if ([IO.Path]::GetDirectoryName($Output) -ne $BuildRoot) { throw 'Export output escapes the build directory.' }
    $Allowed=@('MAP001-Walk.exe','MAP001-Walk.console.exe','MAP001-Walk.pck','BUILD-INFO.json','scene')+@($Documents.Keys)
    if (Test-Path -LiteralPath $Output) {
        $Existing=Get-Item -LiteralPath $Output
        if (-not $Existing.PSIsContainer -or ($Existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe export output path.' }
        foreach ($Entry in Get-ChildItem -LiteralPath $Output) {
            if ($Entry.Name -notin $Allowed -or ($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected or redirected export entry; review it before exporting.' }
            if ($Entry.PSIsContainer -and $Entry.Name -ne 'scene') { throw 'Unexpected export directory.' }
        }
    }
    $SceneOutput=Join-Path $Output 'scene'
    $Payloads=@('flags.bin','nbg0.png','nbg1.png','package.json','profile.json','traces.json')
    if (Test-Path -LiteralPath $SceneOutput) {
        foreach ($Entry in Get-ChildItem -LiteralPath $SceneOutput) {
            if ($Entry.Name -notin $Payloads -or $Entry.PSIsContainer -or ($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected or redirected scene payload.' }
        }
    }
    New-Item -ItemType Directory -Force -Path $Output,$SceneOutput | Out-Null
    CheckedGodot @('--headless','--path',$Demo,'--editor','--import','--quit') 'export-import'
    CheckedGodot @('--headless','--path',$Demo,'--export-release','Windows Exploration Workbench',(Join-Path $Output 'MAP001-Walk.exe')) 'export'
    foreach ($Name in $Payloads) { Copy-Item -LiteralPath (Join-Path $Bundle $Name) -Destination (Join-Path $SceneOutput $Name) -Force }
    foreach ($Name in $Documents.Keys) { Copy-Item -LiteralPath $Documents[$Name] -Destination (Join-Path $Output $Name) -Force }
    $SourceCommit=(& git -c ('safe.directory='+$PcRoot.Replace('\','/')) -C $PcRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record source commit.' }
    $SourceChanges=@(& git -c ('safe.directory='+$PcRoot.Replace('\','/')) -C $PcRoot status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record source working tree state.' }
    $Dirty=if ($SourceChanges.Count -gt 0) { 'true' } else { 'false' }
    $Audit=Join-Path $PSScriptRoot 'audit_exploration_package.py'
    CheckedPython @($Audit,'build-info','--delivery',$Output,'--pin',$PinPath,'--source-commit',$SourceCommit,'--dirty',$Dirty,
        '--report',(Join-Path $Reports 'package-audit.json')) 'package-audit'
    $Zip=Join-Path $BuildRoot 'MAP001-Walk-Windows-x64.zip'
    $Extraction=Join-Path $BuildRoot ('exploration-zip-check-'+[guid]::NewGuid().ToString('N'))
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Extraction)) -ne $BuildRoot) { throw 'Extraction path escapes build directory.' }
    CheckedPython @($Audit,'zip','--delivery',$Output,'--pin',$PinPath,'--zip',$Zip,'--extract-to',$Extraction,
        '--report',(Join-Path $Reports 'zip-audit.json')) 'zip-audit'
    Write-Output ('Windows ZIP verified: '+$Zip)
    Write-Output ('Verified extraction retained for cold-start QA: '+$Extraction)
} finally {
    Pop-Location
}
