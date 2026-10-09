param(
    [string]$ReportPath='',
    [ValidateSet('preflight','postflight')][string]$Phase='preflight',
    [ValidateRange(1,10)][int]$SampleSeconds=3,
    [int[]]$QaProcessIds=@(),
    [string[]]$KnownGameNames=@('bg3','bg3_dx11'),
    [ValidateRange(1,100)][double]$HighGpuPercent=10,
    [ValidateRange(1,6400)][double]$HighCpuPercent=100
)
$ErrorActionPreference='Stop'

function Get-CharacterEnvironmentAssessment([object[]]$Rows,[int[]]$AllowedIds,[string[]]$Games,
    [double]$GpuThreshold=10,[double]$CpuThreshold=100,[bool]$CountersAvailable=$true) {
    $NormalNames=@('dwm','codex','chatgpt','explorer','shellexperiencehost','startmenuexperiencehost','searchhost','textinputhost')
    $Known=@($Games | ForEach-Object { $_.ToLowerInvariant() -replace '\.exe$','' })
    $Blocked=[Collections.Generic.List[object]]::new()
    $Review=[Collections.Generic.List[object]]::new()
    $Normal=[Collections.Generic.List[object]]::new()
    foreach ($Row in $Rows) {
        $Name=([string]$Row.name).ToLowerInvariant() -replace '\.exe$',''
        $Busy=($Row.gpu_3d_peak_percent -ge $GpuThreshold -or $Row.gpu_engine_sum_peak_percent -ge $GpuThreshold -or
            ($null -ne $Row.cpu_percent_one_core -and $Row.cpu_percent_one_core -ge $CpuThreshold))
        if ($Name -in $Known) {
            $Blocked.Add([pscustomobject]@{pid=$Row.pid;name=$Row.name;reason='Configured non-QA game is present; zero sampled GPU usage does not approve concurrent game execution.'})
        } elseif ($Row.pid -in $AllowedIds) {
            continue
        } elseif ($Name -in $NormalNames) {
            if ($Busy) { $Normal.Add([pscustomobject]@{pid=$Row.pid;name=$Row.name;reason='Normal desktop/Codex process retained as visible load, not automatically rejected.'}) }
        } elseif ($Busy) {
            $Review.Add([pscustomobject]@{pid=$Row.pid;name=$Row.name;reason='Unreviewed high-load process; identity as a game is not inferred from load alone.'})
        }
    }
    if (-not $CountersAvailable) { $Review.Add([pscustomobject]@{pid=$null;name=$null;reason='GPU counter evidence is unavailable; quiet GPU cannot be established.'}) }
    $Status=if ($Blocked.Count) { 'blocked' } elseif ($Review.Count) { 'needs_review' } else { 'clear_in_sample_window' }
    return [ordered]@{schema='ao_pc_character_environment_assessment_v1';status=$Status;
        isolated_preflight_passed=($Blocked.Count -eq 0 -and $Review.Count -eq 0);
        blocked_processes=@($Blocked.ToArray());review_processes=@($Review.ToArray());normal_desktop_load=@($Normal.ToArray());
        scope='Short preflight observation only. Does not prove a prior/future run was isolated or attribute any frame spike to a process.';
        gpu_threshold_percent=$GpuThreshold;cpu_threshold_one_core_percent=$CpuThreshold}
}

function Get-CharacterProcessCpuSnapshot {
    $Result=@{}
    foreach ($Process in Get-Process) {
        $Cpu=$null
        try { $Cpu=$Process.TotalProcessorTime.TotalSeconds } catch { }
        $Result[[int]$Process.Id]=[pscustomobject]@{pid=[int]$Process.Id;name=[string]$Process.ProcessName;cpu_seconds=$Cpu}
    }
    return $Result
}

function Invoke-CharacterEnvironmentProbe {
    $StartedUtc=[DateTime]::UtcNow.ToString('o')
    $Timer=[Diagnostics.Stopwatch]::StartNew()
    $Before=Get-CharacterProcessCpuSnapshot
    $CpuStart=$Timer.Elapsed.TotalSeconds
    $CounterStarted=$Timer.Elapsed.TotalSeconds
    $Errors=[Collections.Generic.List[string]]::new()
    $CounterRows=@()
    try {
        # Run before a soak, never concurrently with frame-time acceptance.
        $CounterArguments=@{Counter=@('\GPU Engine(*)\Utilization Percentage',
            '\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage');
            SampleInterval=$SampleSeconds;MaxSamples=2;ErrorAction='Stop'}
        $CounterRows=@(Get-Counter @CounterArguments)
    } catch { $Errors.Add($_.Exception.Message) }
    $CounterFinished=$Timer.Elapsed.TotalSeconds
    $After=Get-CharacterProcessCpuSnapshot
    $CpuEnd=$Timer.Elapsed.TotalSeconds
    $Elapsed=$CpuEnd-$CpuStart
    $Gpu=@{}
    $GpuSamples=[Collections.Generic.List[object]]::new()
    foreach ($CounterSet in $CounterRows) {
        $PerPid=@{}
        foreach ($Counter in $CounterSet.CounterSamples) {
            if ($Counter.InstanceName -notmatch '^pid_([0-9]+)_') { continue }
            $ObservedId=[int]$Matches[1]
            $Value=[double]$Counter.CookedValue
            if ([double]::IsNaN($Value) -or [double]::IsInfinity($Value) -or $Value -lt 0) { continue }
            if (-not $PerPid.ContainsKey($ObservedId)) { $PerPid[$ObservedId]=[ordered]@{pid=$ObservedId;gpu_3d_percent=0.0;gpu_engine_sum_percent=0.0;dedicated_bytes=0.0;shared_bytes=0.0} }
            $Row=$PerPid[$ObservedId]
            if ($Counter.Path -like '*\utilization percentage') {
                $Row.gpu_engine_sum_percent+=$Value
                if ($Counter.InstanceName -match '_engtype_3d$') { $Row.gpu_3d_percent+=$Value }
            } elseif ($Counter.Path -like '*\dedicated usage') { $Row.dedicated_bytes+=$Value }
            elseif ($Counter.Path -like '*\shared usage') { $Row.shared_bytes+=$Value }
        }
        foreach ($ObservedId in $PerPid.Keys) {
            $Row=$PerPid[$ObservedId]
            $GpuSamples.Add([pscustomobject]@{timestamp_utc=$CounterSet.Timestamp.ToUniversalTime().ToString('o');pid=$ObservedId;
                gpu_3d_percent=$Row.gpu_3d_percent;gpu_engine_sum_percent=$Row.gpu_engine_sum_percent;
                dedicated_bytes=$Row.dedicated_bytes;shared_bytes=$Row.shared_bytes})
            if (-not $Gpu.ContainsKey($ObservedId)) { $Gpu[$ObservedId]=[ordered]@{gpu_3d_peak_percent=0.0;gpu_engine_sum_peak_percent=0.0;gpu_dedicated_peak_bytes=0.0;gpu_shared_peak_bytes=0.0} }
            $Peak=$Gpu[$ObservedId]
            $Peak.gpu_3d_peak_percent=[math]::Max($Peak.gpu_3d_peak_percent,$Row.gpu_3d_percent)
            $Peak.gpu_engine_sum_peak_percent=[math]::Max($Peak.gpu_engine_sum_peak_percent,$Row.gpu_engine_sum_percent)
            $Peak.gpu_dedicated_peak_bytes=[math]::Max($Peak.gpu_dedicated_peak_bytes,$Row.dedicated_bytes)
            $Peak.gpu_shared_peak_bytes=[math]::Max($Peak.gpu_shared_peak_bytes,$Row.shared_bytes)
        }
    }
    $Rows=@(foreach ($ObservedId in @(@($Before.Keys)+@($After.Keys)+@($Gpu.Keys) | Sort-Object -Unique)) {
        $Cpu=$null
        if ($Before.ContainsKey($ObservedId) -and $After.ContainsKey($ObservedId) -and $null -ne $Before[$ObservedId].cpu_seconds -and $null -ne $After[$ObservedId].cpu_seconds -and $Elapsed -gt 0) {
            $Delta=$After[$ObservedId].cpu_seconds-$Before[$ObservedId].cpu_seconds
            if ($Delta -ge 0) { $Cpu=$Delta/$Elapsed*100.0 }
        }
        $Name=if ($After.ContainsKey($ObservedId)) { $After[$ObservedId].name } elseif ($Before.ContainsKey($ObservedId)) { $Before[$ObservedId].name } else { '<unavailable>' }
        $Row=[ordered]@{pid=$ObservedId;name=$Name;present_at_start=$Before.ContainsKey($ObservedId);present_at_end=$After.ContainsKey($ObservedId);
            cpu_percent_one_core=$Cpu;gpu_3d_peak_percent=0.0;gpu_engine_sum_peak_percent=0.0;gpu_dedicated_peak_bytes=0.0;gpu_shared_peak_bytes=0.0}
        if ($Gpu.ContainsKey($ObservedId)) { foreach ($Key in $Gpu[$ObservedId].Keys) { $Row[$Key]=$Gpu[$ObservedId][$Key] } }
        [pscustomobject]$Row
    })
    $Available=($Errors.Count -eq 0 -and $CounterRows.Count -eq 2 -and $GpuSamples.Count -gt 0)
    $Assessment=Get-CharacterEnvironmentAssessment $Rows (@($QaProcessIds)+@($PID)) $KnownGameNames $HighGpuPercent $HighCpuPercent $Available
    $Timer.Stop()
    return [ordered]@{schema='ao_pc_character_environment_probe_v1';observation_phase=$Phase;historical_isolation_proven=$false;
        started_utc=$StartedUtc;elapsed_seconds=$Timer.Elapsed.TotalSeconds;
        requested_counter_interval_seconds=$SampleSeconds;counter_call_start_seconds=$CounterStarted;counter_call_end_seconds=$CounterFinished;
        cpu_interval_seconds=$Elapsed;counter_errors=@($Errors.ToArray());counter_samples=@($GpuSamples.ToArray());
        processes=$Rows;assessment=$Assessment;known_game_names=$KnownGameNames;qa_process_ids=$QaProcessIds;
        cpu_scope='100 percent means one fully occupied CPU core, not percent of all logical processors.';
        gpu_scope='Peak of two samples; sums of matching per-process engine instances may exceed 100 percent and are not a whole-GPU occupancy percentage.';
        read_only=$true;terminated_processes=@();changed_system_settings=$false}
}

if ($MyInvocation.InvocationName -eq '.') { return }
$PcRoot=Split-Path -Parent $PSScriptRoot
if (-not $ReportPath) { $ReportPath=Join-Path $PcRoot ('reports/character/environment-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')+'.json') }
if (Test-Path -LiteralPath $ReportPath) { throw 'Use a new environment report path; previous evidence is preserved.' }
$Directory=Split-Path -Parent ([IO.Path]::GetFullPath($ReportPath))
if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { throw 'Environment report directory must already exist.' }
$Result=Invoke-CharacterEnvironmentProbe
$Result | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath $ReportPath -Encoding utf8
Write-Output ('Environment '+$Phase+' '+$Result.assessment.status+': '+$ReportPath)
if (-not $Result.assessment.isolated_preflight_passed) { throw 'Environment observation did not establish a clear sample window. Review the recorded process identities/load; no process was stopped.' }
