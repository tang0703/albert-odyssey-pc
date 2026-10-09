param([ValidateRange(10,3600)][int]$SoakSeconds=600,[switch]$SkipSoak,[ValidateRange(0,120)][int]$WarmupSeconds=15)
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Exe=Join-Path $PcRoot 'build/battle-demo/Triad-Trial.exe'
$Reports=Join-Path $PcRoot 'reports'

function Get-Median([object[]]$Values) {
    if ($Values.Count -eq 0) { throw 'No memory/monitor samples available.' }
    $Sorted=@($Values | Sort-Object)
    $Middle=[int][math]::Floor($Sorted.Count/2)
    if ($Sorted.Count % 2 -eq 1) { return [double]$Sorted[$Middle] }
    return ([double]$Sorted[$Middle-1]+[double]$Sorted[$Middle])/2
}

function Test-SoakReport($Report,[object[]]$ProcessSamples,[int]$Seconds,[int]$Warmup) {
    $Failures=[System.Collections.Generic.List[string]]::new()
    if ($Report.mean_ms -le 0 -or (1000.0/$Report.mean_ms) -lt 59) { $Failures.Add('Average frame rate below 59 FPS.') }
    if ($Report.p95_ms -gt 20) { $Failures.Add('P95 frame time above 20 ms.') }
    if ($Report.battles -lt 1 -or $Report.actions -lt 1) { $Failures.Add('No completed battle loops.') }
    $SteadySeconds=if ($null -ne $Report.measured_seconds) { [double]$Report.measured_seconds } else { [double]$Report.seconds-$Warmup }
    if ($SteadySeconds -lt $Seconds) { $Failures.Add('Steady-state measurement ended early.') }
    $Memory=[ordered]@{evaluated=$false;reason='A run of at least 180 seconds is required for separate comparison windows.'}
    if ($Seconds -ge 180) {
        $Early=@($ProcessSamples | Where-Object { $_.seconds -ge ($Warmup+60) -and $_.seconds -lt ($Warmup+120) })
        $Late=@($ProcessSamples | Where-Object { $_.seconds -ge ($Warmup+$Seconds-60) })
        if ($Early.Count -lt 30 -or $Late.Count -lt 30) { $Failures.Add('Insufficient process memory samples.') }
        else {
            $EarlyPrivate=Get-Median @($Early.private_bytes)
            $LatePrivate=Get-Median @($Late.private_bytes)
            $EarlyWorking=Get-Median @($Early.working_set)
            $LateWorking=Get-Median @($Late.working_set)
            $PrivateGrowth=($LatePrivate/$EarlyPrivate-1.0)*100.0
            $WorkingGrowth=($LateWorking/$EarlyWorking-1.0)*100.0
            $Memory=[ordered]@{evaluated=$true;early_window_seconds=@(($Warmup+60),($Warmup+120));late_window_seconds=@(($Warmup+$Seconds-60),($Warmup+$Seconds));early_private_median=$EarlyPrivate;late_private_median=$LatePrivate;private_growth_percent=$PrivateGrowth;early_working_set_median=$EarlyWorking;late_working_set_median=$LateWorking;working_set_growth_percent=$WorkingGrowth}
            if ($PrivateGrowth -gt 10 -or $WorkingGrowth -gt 10) { $Failures.Add('Process memory median increased by more than 10 percent.') }
        }
    }
    # Prefer identical lifecycle checkpoints. Periodic samples can contain a hit
    # label and impact node, so their raw counts must not override clean checkpoints.
    $Nodes=[ordered]@{evaluated=$false}
    if ($null -ne $Report.battle_node_checkpoints) {
        $Checkpoints=@($Report.battle_node_checkpoints)
        if ($Checkpoints.Count -lt 2) { $Failures.Add('At least two cleaned battle checkpoints are required for node comparison.') }
        else {
            $Persistent=@($Checkpoints | ForEach-Object { $_.persistent_nodes })
            $Nodes=[ordered]@{evaluated=$true;method='cleaned_battle_checkpoints';checkpoints=$Checkpoints.Count;first_persistent=$Persistent[0];last_persistent=$Persistent[-1];minimum=($Persistent | Measure-Object -Minimum).Minimum;maximum=($Persistent | Measure-Object -Maximum).Maximum}
            foreach ($Checkpoint in $Checkpoints) {
                if ($Checkpoint.busy -ne $false -or $null -eq $Checkpoint.transient_nodes -or $Checkpoint.transient_nodes -ne 0 -or $null -eq $Checkpoint.persistent_nodes -or $Checkpoint.persistent_nodes -le 0) {
                    $Failures.Add('Invalid battle checkpoint: presentation or transient nodes were not cleaned.'); break
                }
                if ($null -eq $Checkpoint.tree_nodes -or $Checkpoint.tree_nodes -ne $Checkpoint.persistent_nodes -or ($null -ne $Checkpoint.nodes -and $Checkpoint.nodes -ne $Checkpoint.tree_nodes)) {
                    $Failures.Add('Battle checkpoint scene-tree/global node counts disagree.'); break
                }
            }
            if ($Nodes.minimum -ne $Nodes.maximum) { $Failures.Add('Persistent node count changed between cleaned battles.') }
            if (@($Checkpoints.battles | Select-Object -Unique).Count -lt 2) { $Failures.Add('Node checkpoints must cover different completed battles.') }
            foreach ($Sample in $Report.samples) {
                if ($null -ne $Sample.persistent_nodes -and $Sample.persistent_nodes -ne $Persistent[0]) { $Failures.Add('Periodic inventory shows persistent node growth or loss.'); break }
                if ($null -ne $Sample.tree_nodes -and $null -ne $Sample.transient_nodes -and $null -ne $Sample.persistent_nodes -and $Sample.tree_nodes -ne ($Sample.persistent_nodes+$Sample.transient_nodes)) { $Failures.Add('Periodic node inventory totals disagree.'); break }
            }
        }
    } elseif ($Seconds -ge 180) {
        # Preserve the conservative legacy verdict when no inventory was recorded.
        $EarlyMonitors=@($Report.samples | Where-Object { $_.seconds -ge ($Warmup+60) -and $_.seconds -lt ($Warmup+120) })
        $LateMonitors=@($Report.samples | Where-Object { $_.seconds -ge ($Warmup+$Seconds-60) })
        if ($EarlyMonitors.Count -lt 3 -or $LateMonitors.Count -lt 3) { $Failures.Add('Insufficient engine monitor samples.') }
        else {
            $EarlyNodes=($EarlyMonitors | Measure-Object -Property nodes -Minimum).Minimum
            $LateNodes=($LateMonitors | Measure-Object -Property nodes -Minimum).Minimum
            $Nodes=[ordered]@{evaluated=$true;method='legacy_raw_low_water';early_floor=$EarlyNodes;late_floor=$LateNodes}
            if ($LateNodes -gt $EarlyNodes) { $Failures.Add('Live node low-water mark grew between comparison windows.') }
        }
    }
    $OsPeakSamples=@($ProcessSamples | Where-Object { $null -ne $_.peak_working_set })
    return [ordered]@{schema='battle_demo_soak_acceptance_v3';passed=($Failures.Count -eq 0);full_memory_and_node_acceptance=($Failures.Count -eq 0 -and $Memory.evaluated -and $Nodes.evaluated);failures=@($Failures);mean_fps=(1000.0/[math]::Max(0.001,$Report.mean_ms));p95_ms=$Report.p95_ms;max_ms=$Report.max_ms;spikes_over_100ms_require_review=($Report.max_ms -gt 100);spikes_ms=$Report.spikes_ms;startup_ms=$Report.startup_ms;memory=$Memory;nodes=$Nodes;process_working_set_peak=($ProcessSamples | Measure-Object -Property working_set -Maximum).Maximum;process_working_set_os_peak=($OsPeakSamples | Measure-Object -Property peak_working_set -Maximum).Maximum;process_private_peak=($ProcessSamples | Measure-Object -Property private_bytes -Maximum).Maximum;engine_video_bytes_peak=($Report.samples | Measure-Object -Property video_bytes -Maximum).Maximum}
}

function Invoke-DemoQa([string]$Name,[string]$Size,[int]$Seconds,[string]$Mode,[string]$Variant='') {
    $Output=Join-Path $Reports $Name
    New-Item -ItemType Directory -Force $Output | Out-Null
    # Remove only known report outputs to avoid accepting a previous run's result.
    foreach ($Old in @('report.json','screen.png','process-memory.json','acceptance.json')) {
        $OldPath=Join-Path $Output $Old
        if (Test-Path -LiteralPath $OldPath) { Remove-Item -LiteralPath $OldPath -Force }
    }
    $Log=Join-Path $Reports ($Name+'-engine.log')
    $Arguments=@('--log-file',('"'+$Log+'"'),'--',('"--qa-dir='+$Output+'"'),('--qa-mode='+$Mode),('--qa-size='+$Size),('--qa-seconds='+$Seconds),('--qa-warmup='+$WarmupSeconds))
    if ($Variant) { $Arguments+=('--qa-variant='+$Variant) }
    $Started=[Diagnostics.Stopwatch]::StartNew()
    $Process=Start-Process -FilePath $Exe -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    $Samples=[System.Collections.Generic.List[object]]::new()
    try {
        while (-not $Process.HasExited) {
            $Process.Refresh()
            if ($Process.HasExited) { break }
            $Samples.Add([pscustomobject]@{seconds=[math]::Round($Started.Elapsed.TotalSeconds,2);working_set=$Process.WorkingSet64;private_bytes=$Process.PrivateMemorySize64;peak_working_set=$Process.PeakWorkingSet64})
            if ($Started.Elapsed.TotalSeconds -gt [math]::Max(45,$Seconds+$WarmupSeconds+45)) { throw ('QA timed out: '+$Name) }
            Start-Sleep -Seconds 1
        }
        $Process.WaitForExit()
        $Samples | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Output 'process-memory.json')
        if ($Process.ExitCode -ne 0) { throw ('QA failed: '+$Name) }
        $Text=Get-Content -Raw $Log
        if ($Text -match 'SCRIPT ERROR:|Parse Error:|QA render size mismatch|QA ERROR:') { throw ('QA engine error: '+$Name) }
        $Report=Get-Content -Raw (Join-Path $Output 'report.json') | ConvertFrom-Json
        if (($Report.size -join 'x') -ne $Size) { throw ('QA size mismatch: '+$Name) }
        if ($Mode -eq 'screenshot') {
            if (-not (Test-Path -LiteralPath (Join-Path $Output 'screen.png'))) { throw ('Missing QA screenshot: '+$Name) }
        } else {
            if (Test-Path -LiteralPath (Join-Path $Output 'screen.png')) { throw 'Soak unexpectedly wrote a screenshot during timing.' }
            $Acceptance=Test-SoakReport $Report @($Samples.ToArray()) $Seconds $WarmupSeconds
            $Acceptance | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $Output 'acceptance.json')
            if (-not $Acceptance.passed) { throw ('Soak acceptance failed: '+($Acceptance.failures -join ' ')) }
            if ($Acceptance.spikes_over_100ms_require_review) { Write-Warning 'A frame exceeded 100 ms; inspect its event and reproduce separately before delivery acceptance.' }
        }
        Write-Output ($Name+' passed')
    } finally {
        # Stop only the process started by this invocation if validation is aborted.
        if (-not $Process.HasExited) { $Process.Kill(); $Process.WaitForExit() }
        $Process.Dispose()
    }
}

# Dot-sourcing exposes the acceptance functions for deterministic fixture tests.
if ($MyInvocation.InvocationName -eq '.') { return }
if (-not (Test-Path -LiteralPath $Exe)) { throw 'Export the battle demo first.' }
New-Item -ItemType Directory -Force $Reports | Out-Null
$LockPath=Join-Path $Reports 'battle-qa.lock'
$QaLock=$null
try {
    try { $QaLock=[IO.File]::Open($LockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
    catch { throw 'Another battle QA run is active; do not overlap performance measurements.' }
    # Screenshots and cold launches finish before the single stable performance run.
    foreach ($Size in @('1920x1080','2560x1440','3840x2160')) { Invoke-DemoQa ('battle-'+$Size) $Size 0 'screenshot' 'selection' }
    if (-not $SkipSoak) { Invoke-DemoQa 'battle-soak' '3840x2160' $SoakSeconds 'soak' }
} finally {
    if ($null -ne $QaLock) { $QaLock.Dispose() }
}
