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
Write-Output ("Battle QA acceptance: $Checks fixture checks passed.")
