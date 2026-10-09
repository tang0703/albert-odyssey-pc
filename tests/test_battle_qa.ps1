$ErrorActionPreference='Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'tools/battle_qa.ps1')
$Checks=0
function Assert-Check([bool]$Condition,[string]$Message) {
    if (-not $Condition) { throw $Message }
    $script:Checks+=1
}
$ProcessSamples=@(0..615 | ForEach-Object { [pscustomobject]@{seconds=$_;private_bytes=100000000;working_set=80000000} })
$EngineSamples=@(0..61 | ForEach-Object { [pscustomobject]@{seconds=$_*10;nodes=100;video_bytes=20000000} })
$Report=[pscustomobject]@{mean_ms=16.67;p95_ms=17.0;max_ms=25;seconds=615;measured_seconds=600;actions=100;battles=10;samples=$EngineSamples;startup_ms=1500;spikes_ms=@()}
$Good=Test-SoakReport $Report $ProcessSamples 600 15
Assert-Check $Good.passed 'Healthy soak was rejected.'
Assert-Check ($Good.memory.evaluated -and $Good.nodes.evaluated) 'Full soak did not evaluate memory/nodes.'
Assert-Check ($Good.memory.private_growth_percent -eq 0) 'Stable memory growth must be zero.'
$Report.p95_ms=21
Assert-Check (-not (Test-SoakReport $Report $ProcessSamples 600 15).passed) 'Slow P95 accepted.'
$Report.p95_ms=17
$Report.mean_ms=20
Assert-Check (-not (Test-SoakReport $Report $ProcessSamples 600 15).passed) 'Low FPS accepted.'
$Report.mean_ms=16.67
$Report.measured_seconds=590
Assert-Check (-not (Test-SoakReport $Report $ProcessSamples 600 15).passed) 'Short measurement accepted.'
$Report.measured_seconds=600
foreach ($Sample in $ProcessSamples | Where-Object { $_.seconds -ge 555 }) { $Sample.private_bytes=120000000 }
Assert-Check (-not (Test-SoakReport $Report $ProcessSamples 600 15).passed) 'Growing process memory accepted.'
foreach ($Sample in $ProcessSamples) { $Sample.private_bytes=100000000 }
foreach ($Sample in $EngineSamples | Where-Object { $_.seconds -ge 555 }) { $Sample.nodes=110 }
Assert-Check (-not (Test-SoakReport $Report $ProcessSamples 600 15).passed) 'Growing node baseline accepted.'
foreach ($Sample in $EngineSamples) { $Sample.nodes=100 }
$Report.max_ms=174
$Review=Test-SoakReport $Report $ProcessSamples 600 15
Assert-Check ($Review.passed -and $Review.spikes_over_100ms_require_review) 'Large isolated spike must be marked for explicit reproduction review.'
$Report.measured_seconds=30
$Short=Test-SoakReport $Report $ProcessSamples 30 15
Assert-Check ($Short.passed -and -not $Short.memory.evaluated -and -not $Short.nodes.evaluated) 'Short smoke must not claim full leak acceptance.'
$Report.max_ms=28
$Report.measured_seconds=120
$Checkpoints=@(1..3 | ForEach-Object { [pscustomobject]@{battles=$_;busy=$false;persistent_nodes=72;transient_nodes=0;tree_nodes=72;nodes=72} })
$Report | Add-Member -NotePropertyName battle_node_checkpoints -NotePropertyValue $Checkpoints
$Report.samples=@(1..12 | ForEach-Object { [pscustomobject]@{seconds=$_*10;nodes=74;tree_nodes=74;persistent_nodes=72;transient_nodes=2;video_bytes=20000000} })
$Clean=Test-SoakReport $Report @() 120 15
Assert-Check ($Clean.passed -and $Clean.nodes.evaluated -and -not $Clean.memory.evaluated -and -not $Clean.full_memory_and_node_acceptance) 'Clean 72-node checkpoints must accept transient 74-node action phases without claiming full memory acceptance.'
$Checkpoints[-1].persistent_nodes=73
$Checkpoints[-1].tree_nodes=73
$Checkpoints[-1].nodes=73
Assert-Check (-not (Test-SoakReport $Report @() 120 15).passed) 'Real persistent node growth was accepted.'
$Checkpoints[-1].persistent_nodes=72
$Checkpoints[-1].tree_nodes=72
$Checkpoints[-1].nodes=72
$Checkpoints[-1].busy=$true
Assert-Check (-not (Test-SoakReport $Report @() 120 15).passed) 'Busy checkpoint was accepted as cleaned.'
$Checkpoints[-1].busy=$false
$Checkpoints[-1].transient_nodes=2
Assert-Check (-not (Test-SoakReport $Report @() 120 15).passed) 'Transient nodes at cleanup checkpoint accepted.'
$Checkpoints[-1].transient_nodes=0
$Checkpoints[-1].nodes=74
Assert-Check (-not (Test-SoakReport $Report @() 120 15).passed) 'Checkpoint global/tree mismatch accepted.'
$Checkpoints[-1].nodes=72
$PeakSamples=@([pscustomobject]@{working_set=80;private_bytes=90;peak_working_set=120})
$Peaks=Test-SoakReport $Report $PeakSamples 120 15
Assert-Check ($Peaks.process_working_set_peak -eq 80 -and $Peaks.process_working_set_os_peak -eq 120) 'Sampled and operating-system working-set peaks were conflated.'
Write-Output ("Battle QA acceptance: $Checks fixture checks passed.")
