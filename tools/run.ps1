param([ValidateSet('build','test','export','run','qa')][string]$Action='run')
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$WorkspaceRoot=Split-Path -Parent $PcRoot
$Godot=Join-Path $WorkspaceRoot 'tools\pc-remake\godot-4.7.2\Godot_v4.7.2-stable_win64_console.exe'
$Python=Join-Path $WorkspaceRoot 'tools\pc-remake\python\Scripts\python.exe'
$Reports=Join-Path $PcRoot 'reports'
New-Item -ItemType Directory -Force $Reports | Out-Null
foreach ($Ignored in @($Reports,(Join-Path $PcRoot 'build'))) {
    New-Item -ItemType Directory -Force $Ignored | Out-Null
    if (-not (Test-Path (Join-Path $Ignored '.gdignore'))) {
        New-Item -ItemType File (Join-Path $Ignored '.gdignore') | Out-Null
    }
}
function Run-Checked([string]$Executable,[string[]]$Arguments,[string]$Log) {
    & $Executable @Arguments *> $Log
    if ($LASTEXITCODE -ne 0) { Get-Content $Log -Tail 25; throw "Command failed: $Executable ($LASTEXITCODE)" }
    if ((Get-Content -Raw $Log) -match 'SCRIPT ERROR:|Parse Error:|Failed to load script') { throw "Script error in $Log" }
}
if (-not (Test-Path $Godot) -or -not (Test-Path $Python)) { throw 'Run bootstrap.ps1 and install the isolated Python requirements first.' }
Run-Checked $Python @((Join-Path $PSScriptRoot 'pipeline.py'),'build') (Join-Path $Reports 'pipeline-run.log')
if ($Action -eq 'build') { Get-Content (Join-Path $Reports 'pipeline-run.log'); exit }
Run-Checked $Godot @('--headless','--path',$PcRoot,'--log-file',(Join-Path $Reports 'import-engine.log'),'--editor','--import','--quit') (Join-Path $Reports 'import-run.log')
if ($Action -eq 'test') {
    Run-Checked $Python @('-m','unittest','discover','-s',(Join-Path $PcRoot 'tests'),'-v') (Join-Path $Reports 'python-tests.log')
    Run-Checked $Python @((Join-Path $PSScriptRoot 'probe_v1n.py')) (Join-Path $Reports 'v1n-probe.log')
    Run-Checked $Python @((Join-Path $PSScriptRoot 'trace_vdp1.py')) (Join-Path $Reports 'vdp1-trace.log')
    Run-Checked $Godot @('--headless','--path',$PcRoot,'--log-file',(Join-Path $Reports 'runtime-engine.log'),'--script','res://tests/test_runtime.gd') (Join-Path $Reports 'runtime-run.log')
    Run-Checked $Godot @('--headless','--path',$PcRoot,'--log-file',(Join-Path $Reports 'workbench-test-engine.log'),'--script','res://tests/test_workbench.gd') (Join-Path $Reports 'workbench-test-run.log')
    Write-Output 'Python source tests and Godot contract tests passed.'
    exit
}
if ($Action -eq 'export') {
    New-Item -ItemType Directory -Force (Join-Path $PcRoot 'build\windows') | Out-Null
    Run-Checked $Godot @('--headless','--path',$PcRoot,'--log-file',(Join-Path $Reports 'export-engine.log'),'--export-release','Windows Desktop') (Join-Path $Reports 'export-run.log')
    Write-Output 'Exported build/windows/ao-asset-workbench.exe (development tool, not playable remake).'
    exit
}
if ($Action -eq 'qa') {
    foreach ($size in @('1920x1080','2560x1440','3840x2160')) {
        $Output=Join-Path $Reports "qa-$size"
        Run-Checked $Godot @('--path',$PcRoot,'--log-file',(Join-Path $Reports "qa-$size.log"),'--resolution',$size,'--quit-after','600','--',("--qa-output="+$Output),("--qa-size="+$size)) (Join-Path $Reports "qa-$size-console.log")
        if (-not (Test-Path (Join-Path $Output 'screen.png'))) { throw "Missing QA screenshot for $size" }
    }
    Write-Output 'Three-resolution asset-workbench QA complete.'
    exit
}
& $Godot --path $PcRoot --log-file (Join-Path $Reports 'workbench.log')
exit $LASTEXITCODE
