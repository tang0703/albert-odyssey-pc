param(
    [string]$Executable,
    [string]$OutputRoot,
    [ValidateRange(10,3600)][int]$SoakSeconds=600,
    [ValidateRange(5,120)][int]$WarmupSeconds=15,
    [switch]$SkipSoak,
    [switch]$SoakOnly
)
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
if (-not $Executable) { $Executable=Join-Path $PcRoot 'build/exploration-demo/MAP001-Walk.exe' }
if (-not $OutputRoot) { $OutputRoot=Join-Path $PcRoot ('reports/exploration/qa-'+(Get-Date -Format 'yyyyMMdd-HHmmss')) }

function Get-ExplorationMedian([object[]]$Values) {
    if ($Values.Count -eq 0) { throw 'No samples for median.' }
    $Sorted=@($Values | Sort-Object)
    $Index=[int][math]::Floor($Sorted.Count/2)
    if ($Sorted.Count % 2) { return [double]$Sorted[$Index] }
    return ([double]$Sorted[$Index-1]+[double]$Sorted[$Index])/2
}

function Test-ExplorationNumber($Value,[double]$Minimum=0,[switch]$Integer) {
    if ($null -eq $Value -or [Type]::GetTypeCode($Value.GetType()).ToString() -notin @('Byte','SByte','Int16','UInt16','Int32','UInt32','Int64','UInt64','Single','Double','Decimal')) { return $false }
    $Number=[double]$Value
    return (-not [double]::IsNaN($Number) -and -not [double]::IsInfinity($Number) -and $Number -ge $Minimum -and (-not $Integer -or [math]::Floor($Number) -eq $Number))
}

function Test-ExplorationProperties($Object,[string[]]$Names) {
    if ($null -eq $Object) { return $false }
    foreach ($Name in $Names) {
        if ($Object -is [Collections.IDictionary]) { if (-not $Object.Contains($Name)) { return $false } }
        elseif ($Name -notin $Object.PSObject.Properties.Name) { return $false }
    }
    return $true
}

function Test-ExplorationSoak($Report,[object[]]$Samples,[int]$Seconds,[int]$Warmup) {
    $Failures=[Collections.Generic.List[string]]::new()
    $Rejected=[ordered]@{schema='ao_pc_exploration_soak_acceptance_v1';passed=$false;full_acceptance=$false;failures=@()}
    $Required=@('schema','mode','passed','surface_verified','error','actual_viewport','measured_seconds','warmup_seconds','samples','frame_intervals_ms','average_fps','p95_frame_ms','max_frame_ms','routes_completed','mismatched_updates','screenshots_during_measurement','frame_spikes_over_50ms')
    $Required+=@('surface_size_checks','pixel_reads_before_measurement','pixel_reads_after_measurement','pixel_reads_during_measurement')
    if (-not (Test-ExplorationProperties $Report $Required)) { $Rejected.failures=@('Missing required engine evidence fields.'); return $Rejected }
    if ($Seconds -lt 10 -or $Warmup -lt 5) { $Failures.Add('Invalid requested measurement or warmup duration.') }
    if ($Report.schema -ne 'ao_pc_exploration_ui_qa_v1' -or $Report.mode -ne 'soak' -or $Report.passed -isnot [bool] -or -not $Report.passed -or $Report.error -isnot [string] -or $Report.error.Length -ne 0) { $Failures.Add('Invalid or failed engine report.') }
    if ($Report.surface_verified -isnot [bool] -or -not $Report.surface_verified -or $Report.actual_viewport -isnot [array] -or $Report.actual_viewport.Count -ne 2 -or -not (Test-ExplorationNumber $Report.actual_viewport[0] 1 -Integer) -or -not (Test-ExplorationNumber $Report.actual_viewport[1] 1 -Integer) -or ($Report.actual_viewport -join 'x') -ne '3840x2160') { $Failures.Add('4K render surface was not verified.') }
    foreach ($Key in @('measured_seconds','warmup_seconds','average_fps','p95_frame_ms','max_frame_ms')) {
        if (-not (Test-ExplorationNumber $Report.$Key 0)) { $Failures.Add('Invalid numeric engine field: '+$Key) }
    }
    foreach ($Key in @('routes_completed','mismatched_updates','screenshots_during_measurement')) {
        if (-not (Test-ExplorationNumber $Report.$Key 0 -Integer)) { $Failures.Add('Invalid integer engine field: '+$Key) }
    }
    if ($Report.frame_intervals_ms -isnot [array] -or $Report.frame_intervals_ms.Count -eq 0) { $Failures.Add('Raw frame intervals are missing or empty.') }
    elseif (@($Report.frame_intervals_ms | Where-Object { -not (Test-ExplorationNumber $_ 0.000001) }).Count) { $Failures.Add('Raw frame intervals contain invalid values.') }
    if ($Report.samples -isnot [array] -or $Report.samples.Count -eq 0) { $Failures.Add('Engine samples are missing or empty.') }
    if ($Report.frame_spikes_over_50ms -isnot [array]) { $Failures.Add('Frame spike evidence must be an array.') }
    if ($Failures.Count) { $Rejected.failures=@($Failures); return $Rejected }
    if (-not (Test-ExplorationNumber $Report.surface_size_checks $Report.frame_intervals_ms.Count -Integer) -or
        -not (Test-ExplorationNumber $Report.pixel_reads_before_measurement 1 -Integer) -or
        -not (Test-ExplorationNumber $Report.pixel_reads_after_measurement 1 -Integer) -or
        -not (Test-ExplorationNumber $Report.pixel_reads_during_measurement 0 -Integer) -or $Report.pixel_reads_during_measurement -ne 0) {
        $Failures.Add('Continuous dimensions and timing-excluded GPU pixel verification are incomplete.')
    }

    $TotalMs=0.0
    $RawSpikes=[Collections.Generic.List[object]]::new()
    foreach ($Interval in $Report.frame_intervals_ms) {
        $TotalMs+=[double]$Interval
        if ($Interval -gt 50) { $RawSpikes.Add([pscustomobject]@{seconds=$TotalMs/1000.0;frame_ms=[double]$Interval}) }
    }
    $Duration=$TotalMs/1000.0
    $Average=$Report.frame_intervals_ms.Count/$Duration
    $Sorted=[double[]]$Report.frame_intervals_ms.Clone()
    [Array]::Sort($Sorted)
    $P95=$Sorted[[int][math]::Ceiling($Sorted.Count*0.95)-1]
    $Maximum=$Sorted[-1]
    if ($Duration+0.000001 -lt $Seconds) { $Failures.Add('Raw frame intervals do not cover the requested duration.') }
    if ([math]::Abs([double]$Report.measured_seconds-$Duration) -gt 0.001 -or [math]::Abs([double]$Report.average_fps-$Average) -gt 0.001 -or [math]::Abs([double]$Report.p95_frame_ms-$P95) -gt 0.0001 -or [math]::Abs([double]$Report.max_frame_ms-$Maximum) -gt 0.0001) { $Failures.Add('Reported timing statistics differ from raw frame intervals.') }
    if ([double]$Report.warmup_seconds -ne $Warmup) { $Failures.Add('Engine warmup does not match the requested warmup.') }
    if ($Average -lt 59 -or $P95 -gt 20) { $Failures.Add('Recomputed frame-time target failed.') }
    if ($Report.routes_completed -lt 4 -or $Report.mismatched_updates -ne 0) { $Failures.Add('Source replay did not complete or diverged.') }
    if ($Report.screenshots_during_measurement -ne 0) { $Failures.Add('Screenshot I/O contaminated timing.') }
    if ($Report.frame_spikes_over_50ms.Count -ne $RawSpikes.Count) { $Failures.Add('Frame spike count differs from raw intervals.') }
    else {
        for ($Index=0; $Index -lt $RawSpikes.Count; $Index++) {
            $Spike=$Report.frame_spikes_over_50ms[$Index]
            if (-not (Test-ExplorationProperties $Spike @('seconds','frame_ms','route','update')) -or -not (Test-ExplorationNumber $Spike.seconds 0) -or -not (Test-ExplorationNumber $Spike.frame_ms 50) -or -not (Test-ExplorationNumber $Spike.update 0 -Integer) -or $Spike.route -notin @('cardinal','corners','open','release')) { $Failures.Add('Invalid frame-spike location evidence.'); break }
            if ([math]::Abs($Spike.seconds-$RawSpikes[$Index].seconds) -gt 0.001 -or [math]::Abs($Spike.frame_ms-$RawSpikes[$Index].frame_ms) -gt 0.0001) { $Failures.Add('Frame spike timing differs from raw intervals.'); break }
        }
    }
    $EngineValid=$true
    $Previous=-1.0
    foreach ($Sample in $Report.samples) {
        if (-not (Test-ExplorationProperties $Sample @('seconds','node_count','engine_static_memory_bytes','engine_video_memory_bytes','window_pixels')) -or -not (Test-ExplorationNumber $Sample.seconds 0) -or -not (Test-ExplorationNumber $Sample.node_count 1 -Integer) -or -not (Test-ExplorationNumber $Sample.engine_static_memory_bytes 0) -or -not (Test-ExplorationNumber $Sample.engine_video_memory_bytes 0) -or ($Sample.window_pixels -join 'x') -ne '3840x2160') { $EngineValid=$false; break }
        if ($Sample.seconds -le $Previous -or $Sample.seconds -gt $Duration+0.1 -or ($Previous -ge 0 -and $Sample.seconds-$Previous -gt 3)) { $EngineValid=$false; break }
        $Previous=[double]$Sample.seconds
    }
    $Nodes=@()
    if (-not $EngineValid -or $Report.samples.Count -lt [math]::Floor($Seconds*0.8) -or $Report.samples[0].seconds -gt 2 -or $Report.samples[-1].seconds -lt $Duration-2) { $Failures.Add('Engine node/memory samples are invalid or do not span steady replay.') }
    else {
        $Nodes=@($Report.samples | ForEach-Object { $_.node_count } | Sort-Object -Unique)
        if ($Nodes.Count -ne 1) { $Failures.Add('Scene node count changed during steady replay.') }
    }
    # MEMORY_STATIC is unavailable in Godot release templates (documented as 0).
    # It is diagnostic only. Positive OS private/working-set samples remain mandatory.
    $AllocatorZeroCount=@($Report.samples | Where-Object { $_.engine_static_memory_bytes -eq 0 }).Count
    $AllocatorAvailable=($EngineValid -and $AllocatorZeroCount -eq 0)
    if ($AllocatorZeroCount -gt 0 -and $AllocatorZeroCount -ne $Report.samples.Count) { $Failures.Add('Engine allocator availability changed during measurement.') }
    $ProcessValid=($Samples.Count -gt 0)
    $Previous=-1.0
    foreach ($Sample in $Samples) {
        if (-not (Test-ExplorationProperties $Sample @('seconds','private_bytes','working_set_bytes','peak_working_set_bytes','gpu_dedicated_bytes','gpu_shared_bytes')) -or -not (Test-ExplorationNumber $Sample.seconds 0) -or -not (Test-ExplorationNumber $Sample.private_bytes 1) -or -not (Test-ExplorationNumber $Sample.working_set_bytes 1) -or -not (Test-ExplorationNumber $Sample.peak_working_set_bytes $Sample.working_set_bytes)) { $ProcessValid=$false; break }
        if ($Sample.seconds -le $Previous -or ($Previous -ge 0 -and $Sample.seconds-$Previous -gt 5)) { $ProcessValid=$false; break }
        if (($null -eq $Sample.gpu_dedicated_bytes) -ne ($null -eq $Sample.gpu_shared_bytes) -or ($null -ne $Sample.gpu_dedicated_bytes -and (-not (Test-ExplorationNumber $Sample.gpu_dedicated_bytes 0) -or -not (Test-ExplorationNumber $Sample.gpu_shared_bytes 0)))) { $ProcessValid=$false; break }
        $Previous=[double]$Sample.seconds
    }
    if (-not $ProcessValid -or $Samples.Count -lt [math]::Floor($Seconds*0.5) -or $Samples[0].seconds -gt 5 -or $Samples[-1].seconds -lt $Warmup+$Duration-3) { $Failures.Add('Process memory samples are invalid or do not span the measurement.'); $ProcessValid=$false }
    $Memory=[ordered]@{evaluated=$false}
    if ($Seconds -ge 180 -and $ProcessValid) {
        $Early=@($Samples | Where-Object { $_.seconds -ge ($Warmup+60) -and $_.seconds -lt ($Warmup+120) })
        $Late=@($Samples | Where-Object { $_.seconds -ge ($Warmup+$Duration-60) -and $_.seconds -le ($Warmup+$Duration+3) })
        if ($Early.Count -lt 30 -or $Late.Count -lt 30) { $Failures.Add('Too few process samples in independent memory windows.') }
        else {
            $EarlyPrivate=Get-ExplorationMedian @($Early.private_bytes)
            $LatePrivate=Get-ExplorationMedian @($Late.private_bytes)
            $EarlyWorking=Get-ExplorationMedian @($Early.working_set_bytes)
            $LateWorking=Get-ExplorationMedian @($Late.working_set_bytes)
            $PrivateGrowth=$LatePrivate/$EarlyPrivate-1.0
            $WorkingGrowth=$LateWorking/$EarlyWorking-1.0
            $Memory=[ordered]@{evaluated=$true;early_private_median=$EarlyPrivate;late_private_median=$LatePrivate;private_growth=$PrivateGrowth;early_working_median=$EarlyWorking;late_working_median=$LateWorking;working_growth=$WorkingGrowth}
            if ($PrivateGrowth -gt 0.100000001 -or $WorkingGrowth -gt 0.100000001) { $Failures.Add('Memory median increased by more than 10 percent.') }
        }
    }
    $Gpu=@($Samples | Where-Object { $null -ne $_.gpu_dedicated_bytes -and $null -ne $_.gpu_shared_bytes -and $_.seconds -ge $Warmup -and $_.seconds -le $Warmup+$Duration+3 })
    if ($Gpu.Count -lt [math]::Max(1,[math]::Floor($Seconds/20)) -or ($Gpu.Count -gt 0 -and ($Gpu[0].seconds -gt $Warmup+20 -or $Gpu[-1].seconds -lt $Warmup+$Duration-20))) { $Failures.Add('Per-process dedicated/shared GPU samples do not span the measurement.') }
    for ($Index=1; $Index -lt $Gpu.Count; $Index++) { if ($Gpu[$Index].seconds-$Gpu[$Index-1].seconds -gt 25) { $Failures.Add('GPU monitoring has a gap longer than 25 seconds.'); break } }
    return [ordered]@{
        schema='ao_pc_exploration_soak_acceptance_v1';passed=($Failures.Count -eq 0)
        full_acceptance=($Failures.Count -eq 0 -and $Seconds -ge 600 -and $Memory.evaluated -and $Maximum -le 100)
        failures=@($Failures);average_fps=$Average;p95_ms=$P95;max_ms=$Maximum
        recomputed_measured_seconds=$Duration;raw_frame_count=$Sorted.Count;spikes_over_50ms=@($RawSpikes)
        spikes_over_100ms_require_reproduction_review=($Maximum -gt 100)
        memory=$Memory;node_counts=$Nodes;engine_allocator_available=$AllocatorAvailable
        engine_allocator_note='Zero MEMORY_STATIC in release templates means unavailable, not zero usage; acceptance uses independently sampled OS process memory.'
        working_set_peak=$(if ($ProcessValid) { ($Samples | Measure-Object -Property working_set_bytes -Maximum).Maximum } else { $null })
        os_peak_working_set=$(if ($ProcessValid) { ($Samples | Measure-Object -Property peak_working_set_bytes -Maximum).Maximum } else { $null })
        private_bytes_peak=$(if ($ProcessValid) { ($Samples | Measure-Object -Property private_bytes -Maximum).Maximum } else { $null })
        gpu_dedicated_bytes_peak=$(if ($ProcessValid -and $Gpu.Count) { ($Gpu | Measure-Object -Property gpu_dedicated_bytes -Maximum).Maximum } else { $null })
        gpu_shared_bytes_peak=$(if ($ProcessValid -and $Gpu.Count) { ($Gpu | Measure-Object -Property gpu_shared_bytes -Maximum).Maximum } else { $null })
        gpu_scope='Windows GPU Process Memory counter, summed over adapters for this PID; sampled every 10 seconds'
    }
}

function Get-ExplorationLaunchIdentity([string]$Path) {
    $Absolute=(Resolve-Path -LiteralPath $Path).ProviderPath
    $Directory=Split-Path -Parent $Absolute
    $Pck=Join-Path $Directory 'MAP001-Walk.pck'
    $Manifest=Join-Path $Directory 'scene/package.json'
    $Identity=[ordered]@{executable_path=$Absolute;executable_sha256=$null;pck_path=$Pck;pck_sha256=$null;scene_manifest_path=$Manifest;scene_manifest_sha256=$null;build_info_sha256=$null;source_commit=$null;source_dirty=$null}
    foreach ($Pair in @(@($Absolute,'executable_sha256'),@($Pck,'pck_sha256'),@($Manifest,'scene_manifest_sha256'))) {
        $Before=Get-Item -LiteralPath $Pair[0]
        if ($Before.PSIsContainer -or ($Before.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'QA binary identity must reference a regular file.' }
        $Identity[$Pair[1]]=(Get-FileHash -LiteralPath $Pair[0] -Algorithm SHA256).Hash.ToLowerInvariant()
        $After=Get-Item -LiteralPath $Pair[0]
        if ($Before.Length -ne $After.Length -or $Before.LastWriteTimeUtc -ne $After.LastWriteTimeUtc) { throw 'QA binary changed while hashing.' }
    }
    $BuildInfo=Join-Path $Directory 'BUILD-INFO.json'
    if (Test-Path -LiteralPath $BuildInfo -PathType Leaf) {
        $Info=Get-Content -LiteralPath $BuildInfo -Raw | ConvertFrom-Json
        if (-not (Test-ExplorationProperties $Info @('source_commit','source_has_uncommitted_changes')) -or $Info.source_commit -cnotmatch '^[0-9a-f]{40}$' -or $Info.source_has_uncommitted_changes -isnot [bool]) { throw 'Invalid adjacent build source identity.' }
        $Identity.build_info_sha256=(Get-FileHash -LiteralPath $BuildInfo -Algorithm SHA256).Hash.ToLowerInvariant()
        $Identity.source_commit=$Info.source_commit
        $Identity.source_dirty=$Info.source_has_uncommitted_changes
    }
    return $Identity
}

function Invoke-ExplorationQa([string]$Name,[string]$Size,[bool]$Soak) {
    $Folder=Join-Path $OutputRoot $Name
    if (Test-Path -LiteralPath $Folder) { throw 'Use a fresh QA output directory to preserve prior evidence.' }
    New-Item -ItemType Directory -Path $Folder -Force | Out-Null
    $Report=Join-Path $Folder 'report.json'
    $Output=if ($Soak) { $Report } else { Join-Path $Folder 'screen.png' }
    $Log=Join-Path $Folder 'engine.log'
    $Arguments=@('--log-file',('"'+$Log+'"'),'--',('"--qa-output='+$Output+'"'),('"--qa-report='+$Report+'"'),('--qa-size='+$Size),('--qa-warmup-seconds='+$WarmupSeconds))
    if ($Soak) { $Arguments+=('--qa-soak-seconds='+$SoakSeconds) }
    $LaunchIdentity=Get-ExplorationLaunchIdentity $Executable
    $Timer=[Diagnostics.Stopwatch]::StartNew()
    $Process=Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    $Samples=[Collections.Generic.List[object]]::new()
    $ReadySeconds=$null
    $NextGpu=0.0
    $NextProgress=60.0
    $CounterErrors=[Collections.Generic.List[string]]::new()
    try {
        while (-not $Process.HasExited) {
            $Process.Refresh()
            if ($Process.HasExited) { break }
            if ($null -eq $ReadySeconds -and (Test-Path -LiteralPath ($Report+'.ready.json'))) {
                $ObservedReady=$Timer.Elapsed.TotalSeconds
                $Marker=Get-Content -LiteralPath ($Report+'.ready.json') -Raw | ConvertFrom-Json
                if (-not (Test-ExplorationProperties $Marker @('schema','ticks_usec','actual_viewport','surface_verified')) -or $Marker.schema -ne 'ao_pc_exploration_first_frame_v1' -or -not (Test-ExplorationNumber $Marker.ticks_usec 1 -Integer) -or $Marker.surface_verified -isnot [bool] -or -not $Marker.surface_verified -or ($Marker.actual_viewport -join 'x') -ne $Size) { throw 'Invalid first-frame ready marker.' }
                $ReadySeconds=$ObservedReady
            }
            $Sample=[ordered]@{seconds=[math]::Round($Timer.Elapsed.TotalSeconds,3);working_set_bytes=$Process.WorkingSet64;private_bytes=$Process.PrivateMemorySize64;peak_working_set_bytes=$Process.PeakWorkingSet64;gpu_dedicated_bytes=$null;gpu_shared_bytes=$null}
            if ($Soak -and $null -ne $ReadySeconds -and $Timer.Elapsed.TotalSeconds -ge $NextGpu) {
                try {
                    $Counters=Get-Counter -Counter @('\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage') -ErrorAction Stop
                    $Owned=@($Counters.CounterSamples | Where-Object { $_.InstanceName -like ('pid_'+$Process.Id+'_*') })
                    $Dedicated=@($Owned | Where-Object { $_.Path -like '*\dedicated usage' })
                    $Shared=@($Owned | Where-Object { $_.Path -like '*\shared usage' })
                    if ($Dedicated.Count) { $Sample.gpu_dedicated_bytes=($Dedicated | Measure-Object -Property CookedValue -Sum).Sum }
                    if ($Shared.Count) { $Sample.gpu_shared_bytes=($Shared | Measure-Object -Property CookedValue -Sum).Sum }
                } catch { $CounterErrors.Add($_.Exception.Message) }
                $NextGpu=$Timer.Elapsed.TotalSeconds+10
            }
            $Samples.Add([pscustomobject]$Sample)
            if ($Soak -and $Timer.Elapsed.TotalSeconds -ge $NextProgress) {
                Write-Output ('Soak sampling: {0:N0}s elapsed, {1} process samples, private memory {2:N1} MiB' -f $Timer.Elapsed.TotalSeconds,$Samples.Count,($Process.PrivateMemorySize64/1MB))
                $NextProgress=$Timer.Elapsed.TotalSeconds+60
            }
            if ($Timer.Elapsed.TotalSeconds -gt $(if ($Soak) { $SoakSeconds+$WarmupSeconds+60 } else { 45 })) { throw ('QA timed out: '+$Name) }
            Start-Sleep -Milliseconds $(if ($null -eq $ReadySeconds) { 100 } else { 1000 })
        }
        $Process.WaitForExit()
        $Samples | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Folder 'process-memory.json') -Encoding utf8
        $FinalIdentity=Get-ExplorationLaunchIdentity $Executable
        $Unchanged=($LaunchIdentity.executable_sha256 -eq $FinalIdentity.executable_sha256 -and $LaunchIdentity.pck_sha256 -eq $FinalIdentity.pck_sha256 -and $LaunchIdentity.scene_manifest_sha256 -eq $FinalIdentity.scene_manifest_sha256)
        $LaunchIdentity.process_id=$Process.Id
        $LaunchIdentity.fresh_process=$true
        $LaunchIdentity.launch_to_first_surface_observed_ms=$(if ($null -ne $ReadySeconds) { $ReadySeconds*1000 } else { $null })
        $LaunchIdentity.poll_resolution_ms=100
        $LaunchIdentity.startup_observation_note='Polling before first ready marker is 100 ms; scheduling/filesystem latency is additional. GPU counter calls begin after ready. Filesystem caches were not flushed.'
        $LaunchIdentity.os_disk_cache_flushed=$false
        $LaunchIdentity.total_process_seconds=$Timer.Elapsed.TotalSeconds
        $LaunchIdentity.gpu_counter_errors=@($CounterErrors)
        $LaunchIdentity.binary_identity_unchanged=$Unchanged
        $LaunchIdentity | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Folder 'launch.json') -Encoding utf8
        if (-not $Unchanged) { throw 'Executable, PCK or scene manifest changed during QA.' }
        if ($Process.ExitCode -ne 0) { throw ('Runtime QA failed: '+$Name) }
        if ((Get-Content -Raw -LiteralPath $Log) -match 'SCRIPT ERROR:|Parse Error:|ERROR:') { throw ('Engine errors in '+$Log) }
        $Data=Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
        if (-not $Data.passed -or ($Data.actual_viewport -join 'x') -ne $Size -or $null -eq $ReadySeconds) { throw ('Surface/startup evidence failed: '+$Name) }
        if ($Soak) {
            if (Test-Path -LiteralPath (Join-Path $Folder 'screen.png')) { throw 'Soak unexpectedly wrote a screenshot.' }
            $Acceptance=Test-ExplorationSoak $Data @($Samples.ToArray()) $SoakSeconds $WarmupSeconds
            $Acceptance | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Folder 'acceptance.json') -Encoding utf8
            if (-not $Acceptance.passed) { throw ('Soak failed: '+($Acceptance.failures -join ' ')) }
        } elseif (-not (Test-Path -LiteralPath $Output)) { throw 'Missing rendered screenshot.' }
        Write-Output ('QA passed: '+$Folder)
    } finally {
        if (-not $Process.HasExited) { $Process.Kill(); $Process.WaitForExit() }
        $Process.Dispose()
    }
}

if ($MyInvocation.InvocationName -eq '.') { return }
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw 'Export the exploration workbench first.' }
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$LockPath=Join-Path $PcRoot 'reports/exploration/render-qa.lock'
$QaLock=$null
try {
    $QaLock=[IO.File]::Open($LockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    if (-not $SoakOnly) {
        foreach ($Size in @('1920x1080','2560x1440','3840x2160')) { Invoke-ExplorationQa $Size $Size $false }
    }
    if (-not $SkipSoak) { Invoke-ExplorationQa 'soak-4k' '3840x2160' $true }
} finally { if ($QaLock) { $QaLock.Dispose() } }
