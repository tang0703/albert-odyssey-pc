$ErrorActionPreference='Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'tools/character_qa.ps1')
$Checks=0
function Assert-Check([bool]$Condition,[string]$Message) {
    if (-not $Condition) { throw $Message }
    $script:Checks+=1
}
function New-HealthyFixture {
    $Intervals=[double[]]@(1..36000 | ForEach-Object { 1000.0/60.0 })
    $Engine=@(0..599 | ForEach-Object { [pscustomobject]@{seconds=$_;node_count=94;engine_static_memory_bytes=12000000;engine_video_memory_bytes=80000000;window_pixels=@(3840,2160)} })
    $Process=@(0..615 | ForEach-Object { [pscustomobject]@{seconds=$_;private_bytes=100000000;working_set_bytes=80000000;peak_working_set_bytes=120000000;gpu_dedicated_bytes=$(if ($_%10 -eq 0) { 80000000 } else { $null });gpu_shared_bytes=$(if ($_%10 -eq 0) { 5000000 } else { $null })} })
    $Report=[pscustomobject]@{schema='ao_pc_character_ui_qa_v1';mode='soak';passed=$true;surface_verified=$true;error='';actual_viewport=@(3840,2160);measured_seconds=600.0;warmup_seconds=15;samples=$Engine;frame_intervals_ms=$Intervals;average_fps=60.0;p95_frame_ms=1000.0/60.0;max_frame_ms=1000.0/60.0;routes_completed=50;mismatched_updates=0;screenshots_during_measurement=0;frame_spikes_over_50ms=@()}
    $Report | Add-Member -NotePropertyMembers @{appearance_mode='hd';hd_manifest_sha256=('c'*64);character_manifest_sha256=('b'*64);surface_size_checks=37000;pixel_reads_before_measurement=1;pixel_reads_after_measurement=1;pixel_reads_during_measurement=0}
    return [pscustomobject]@{report=$Report;samples=$Process}
}
function Reject-Fixture([scriptblock]$Change,[string]$Message) {
    $Fixture=New-HealthyFixture
    & $Change $Fixture
    $Result=Test-CharacterSoak $Fixture.report $Fixture.samples 600 15
    Assert-Check (-not $Result.passed -and -not $Result.full_acceptance) $Message
}

$Healthy=New-HealthyFixture
$Good=Test-CharacterSoak $Healthy.report $Healthy.samples 600 15
Assert-Check ($Good.passed -and $Good.full_acceptance) ('Healthy source fixture failed: '+($Good.failures -join '; '))
Assert-Check ([math]::Abs($Good.average_fps-60) -lt 0.0001 -and $Good.raw_frame_count -eq 36000 -and [math]::Abs($Good.recomputed_measured_seconds-600) -lt 0.0001) 'Raw interval recomputation is wrong.'
Assert-Check ($Good.memory.evaluated -and $Good.memory.private_growth -eq 0 -and $Good.memory.working_growth -eq 0) 'Stable external memory did not pass.'

$Release=New-HealthyFixture
foreach ($Sample in $Release.report.samples) { $Sample.engine_static_memory_bytes=0 }
$ReleaseResult=Test-CharacterSoak $Release.report $Release.samples 600 15
Assert-Check ($ReleaseResult.full_acceptance -and -not $ReleaseResult.engine_allocator_available -and $ReleaseResult.memory.evaluated) 'Release allocator unavailability was confused with missing process evidence.'
Assert-Check (-not (Test-CharacterSoak $Release.report @() 600 15).passed) 'Unavailable allocator permitted missing OS process memory.'

Reject-Fixture {param($F) $F.report.appearance_mode='original'} 'Original art cannot satisfy HD QA.'
Reject-Fixture {param($F) $F.report.hd_manifest_sha256=$null} 'Missing HD identity accepted.'
Reject-Fixture {param($F) $F.report.character_manifest_sha256='wrong'} 'Wrong source identity accepted.'
Reject-Fixture {param($F) $F.report.schema='ao_pc_exploration_ui_qa_v1'} 'Old entry QA schema accepted.'
Reject-Fixture {param($F) $F.report=$null} 'Missing report accepted.'
Reject-Fixture {param($F) $F.report=[pscustomobject]@{}} 'Empty report accepted.'
Reject-Fixture {param($F) $F.report.PSObject.Properties.Remove('mismatched_updates')} 'Missing mismatch evidence accepted.'
Reject-Fixture {param($F) $F.report.passed='true'} 'String success flag accepted.'
Reject-Fixture {param($F) $F.report.average_fps='60'} 'String numeric field accepted.'
Reject-Fixture {param($F) $F.report.frame_intervals_ms=@()} 'Empty raw intervals accepted.'
Reject-Fixture {param($F) $F.report.frame_intervals_ms[5]=[double]::NaN} 'NaN interval accepted.'
Reject-Fixture {param($F) $F.report.frame_intervals_ms[5]=0} 'Zero interval accepted.'
Reject-Fixture {param($F) $F.report.actual_viewport=@(1920,1080)} 'Non-4K surface accepted.'
Reject-Fixture {param($F) $F.report.surface_verified=$false} 'Unverified surface accepted.'
Reject-Fixture {param($F) $F.report.surface_size_checks=0} 'Missing continuous dimension checks accepted.'
Reject-Fixture {param($F) $F.report.pixel_reads_after_measurement=0} 'Missing final GPU pixel verification accepted.'
Reject-Fixture {param($F) $F.report.pixel_reads_during_measurement=1} 'GPU readback during timing accepted.'
Reject-Fixture {param($F) $F.report.samples[10].window_pixels=@(2560,1440)} 'Window resize during timing accepted.'
Reject-Fixture {param($F) $F.report.measured_seconds=590} 'Short reported duration accepted.'
Reject-Fixture {param($F) $F.report.frame_intervals_ms=[double[]]@(1..35900 | ForEach-Object {1000.0/60.0})} 'Short raw duration hidden by report accepted.'
Reject-Fixture {param($F) $F.report.average_fps=120} 'Tampered FPS accepted.'
Reject-Fixture {param($F) $F.report.p95_frame_ms=1} 'Tampered P95 accepted.'
Reject-Fixture {param($F) $F.report.max_frame_ms=1} 'Tampered maximum accepted.'
Reject-Fixture {param($F) $F.report.warmup_seconds=0} 'Missing warmup accepted.'
Reject-Fixture {param($F) $F.report.mismatched_updates=1} 'Source mismatch accepted.'
Reject-Fixture {param($F) $F.report.routes_completed=3} 'Incomplete route exercise accepted.'
Reject-Fixture {param($F) $F.report.screenshots_during_measurement=1} 'Screenshot I/O contamination accepted.'
Reject-Fixture {param($F) $F.report.samples=@()} 'Missing engine samples accepted.'
Reject-Fixture {param($F) $F.report.samples[-1].node_count=95} 'Node growth accepted.'
Reject-Fixture {param($F) $F.report.samples[10].node_count=$null} 'Missing node count accepted.'
Reject-Fixture {param($F) $F.report.samples[10].engine_static_memory_bytes=-1} 'Negative allocator memory accepted.'
Reject-Fixture {param($F) $F.report.samples[10].engine_static_memory_bytes=0} 'Intermittent allocator availability accepted.'
Reject-Fixture {param($F) $F.samples=@()} 'Missing external process samples accepted.'
Reject-Fixture {param($F) foreach($S in $F.samples) {$S.private_bytes=0}} 'Zero private memory baseline accepted.'
Reject-Fixture {param($F) foreach($S in $F.samples | Where-Object {$_.seconds -ge 555}) {$S.private_bytes=112000000}} 'Private memory growth above 10 percent accepted.'
Reject-Fixture {param($F) foreach($S in $F.samples | Where-Object {$_.seconds -ge 555}) {$S.working_set_bytes=96000000}} 'Working-set growth above 10 percent accepted.'
Reject-Fixture {param($F) foreach($S in $F.samples) {$S.gpu_dedicated_bytes=$null;$S.gpu_shared_bytes=$null}} 'Missing GPU counters accepted.'
Reject-Fixture {param($F) foreach($S in $F.samples) {$S.gpu_shared_bytes=$null}} 'Missing shared GPU observations accepted.'
Reject-Fixture {param($F) foreach($S in $F.samples | Where-Object {$_.seconds -ge 30}) {$S.gpu_dedicated_bytes=$null;$S.gpu_shared_bytes=$null}} 'GPU samples only at startup accepted.'
Reject-Fixture {param($F) $F.report.frame_spikes_over_50ms=@([pscustomobject]@{seconds=1;frame_ms=150;route='open';update=1})} 'Invented spike evidence accepted.'

$Spike=New-HealthyFixture
$Spike.report.frame_intervals_ms[5]=150
$Duration=($Spike.report.frame_intervals_ms | Measure-Object -Sum).Sum/1000.0
$Spike.report.measured_seconds=$Duration
$Spike.report.average_fps=36000/$Duration
$Spike.report.max_frame_ms=150
$Spike.report.frame_spikes_over_50ms=@([pscustomobject]@{seconds=(5*(1000.0/60.0)+150)/1000;frame_ms=150;route='open';update=1})
$SpikeResult=Test-CharacterSoak $Spike.report $Spike.samples 600 15
Assert-Check ($SpikeResult.passed -and -not $SpikeResult.full_acceptance -and $SpikeResult.spikes_over_100ms_require_reproduction_review) ('Isolated spike did not require separate review: '+($SpikeResult.failures -join '; '))
$Spike.report.frame_spikes_over_50ms[0].seconds=5
Assert-Check (-not (Test-CharacterSoak $Spike.report $Spike.samples 600 15).passed) 'Wrong spike timestamp accepted.'

$FixtureRoot=[IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $PSScriptRoot) ('reports/tmp/character-qa-'+[guid]::NewGuid().ToString('N'))))
$AllowedRoot=[IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $PSScriptRoot) 'reports/tmp'))
if ([IO.Path]::GetDirectoryName($FixtureRoot) -ne $AllowedRoot) { throw 'Fixture path escaped reports/tmp.' }
foreach($Directory in @('scene','character','character-hd')) { New-Item -ItemType Directory -Path (Join-Path $FixtureRoot $Directory) -Force | Out-Null }
try {
    [IO.File]::WriteAllText((Join-Path $FixtureRoot 'MAP001-Character.exe'),'synthetic exe')
    [IO.File]::WriteAllText((Join-Path $FixtureRoot 'MAP001-Character.pck'),'synthetic pck')
    [IO.File]::WriteAllText((Join-Path $FixtureRoot 'scene/package.json'),'synthetic manifest')
    [IO.File]::WriteAllText((Join-Path $FixtureRoot 'character/package.json'),'synthetic source character manifest')
    [IO.File]::WriteAllText((Join-Path $FixtureRoot 'character-hd/package.json'),'synthetic HD manifest')
    @{source_commit=('a'*40);source_has_uncommitted_changes=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $FixtureRoot 'BUILD-INFO.json') -Encoding utf8
    $Identity=Get-CharacterLaunchIdentity (Join-Path $FixtureRoot 'MAP001-Character.exe')
    Assert-Check ($Identity.executable_path -eq (Join-Path $FixtureRoot 'MAP001-Character.exe') -and $Identity.executable_sha256.Length -eq 64 -and $Identity.pck_sha256.Length -eq 64 -and $Identity.scene_manifest_sha256.Length -eq 64 -and $Identity.character_manifest_sha256.Length -eq 64 -and $Identity.hd_manifest_sha256.Length -eq 64 -and $Identity.source_commit -eq ('a'*40) -and -not $Identity.source_dirty) 'Launch binary/source identity incomplete.'
} finally {
    $Resolved=[IO.Path]::GetFullPath($FixtureRoot)
    if ([IO.Path]::GetDirectoryName($Resolved) -ne $AllowedRoot) { throw 'Fixture cleanup escaped reports/tmp.' }
    Remove-Item -LiteralPath $Resolved -Recurse -Force
}
Write-Output ("Character QA acceptance: $Checks fixture checks passed.")
