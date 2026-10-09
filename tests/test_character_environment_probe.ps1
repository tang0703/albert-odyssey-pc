$ErrorActionPreference='Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'tools/character_environment_probe.ps1')
$Checks=0
function Check([bool]$Value,[string]$Message) { if (-not $Value) { throw $Message }; $script:Checks+=1 }
function Row([int]$Number,[string]$Name,[double]$Gpu=0,[double]$Cpu=0) {
    return [pscustomobject]@{pid=$Number;name=$Name;gpu_3d_peak_percent=$Gpu;gpu_engine_sum_peak_percent=$Gpu;cpu_percent_one_core=$Cpu}
}
$Games=@('bg3','bg3_dx11')
$Clear=Get-CharacterEnvironmentAssessment @((Row 101 'idle_editor' 0 0)) @() $Games
Check ($Clear.status -eq 'clear_in_sample_window' -and $Clear.isolated_preflight_passed) 'Quiet synthetic window failed.'
$Game=Get-CharacterEnvironmentAssessment @((Row 102 'bg3.exe' 0 0)) @() $Games
Check ($Game.status -eq 'blocked' -and -not $Game.isolated_preflight_passed -and $Game.blocked_processes.Count -eq 1) 'Known game escaped because a sample was idle.'
$Alternate=Get-CharacterEnvironmentAssessment @((Row 103 'BG3_DX11' 29 230)) @() $Games
Check ($Alternate.status -eq 'blocked') 'Known game name matching is not case-insensitive.'
$Normal=Get-CharacterEnvironmentAssessment @((Row 104 'dwm' 12 0),(Row 105 'Codex' 15 120)) @() $Games
Check ($Normal.isolated_preflight_passed -and $Normal.normal_desktop_load.Count -eq 2) 'Normal DWM/Codex activity was rejected or hidden.'
$Unknown=Get-CharacterEnvironmentAssessment @((Row 106 'unknown_renderer' 29 0)) @() $Games
Check ($Unknown.status -eq 'needs_review' -and $Unknown.blocked_processes.Count -eq 0 -and $Unknown.review_processes.Count -eq 1) 'Unknown load was assumed to be a known game or called clear.'
$Cpu=Get-CharacterEnvironmentAssessment @((Row 107 'cpu_worker' 0 101)) @() $Games
Check ($Cpu.status -eq 'needs_review') 'Unreviewed CPU load was omitted.'
$Own=Get-CharacterEnvironmentAssessment @((Row 108 'MAP001-Character' 35 110)) @(108) $Games
Check $Own.isolated_preflight_passed 'Explicit QA PID was treated as unrelated load.'
$WrongAllow=Get-CharacterEnvironmentAssessment @((Row 109 'bg3' 0 0)) @(109) $Games
Check ($WrongAllow.status -eq 'blocked') 'An allowed PID bypassed a known non-QA game identity.'
$NoGpu=Get-CharacterEnvironmentAssessment @() @() $Games 10 100 $false
Check ($NoGpu.status -eq 'needs_review' -and -not $NoGpu.isolated_preflight_passed) 'Missing counters were accepted as quiet GPU.'
Check ($Clear.scope -match 'prior/future' -and $Clear.scope -match 'attribute') 'Snapshot scope falsely claims historical isolation or causality.'
$Tokens=$null; $Errors=$null
[System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Split-Path -Parent $PSScriptRoot) 'tools/character_environment_probe.ps1'),[ref]$Tokens,[ref]$Errors) | Out-Null
Check ($Errors.Count -eq 0) 'Probe script does not parse.'
Write-Output ('Character environment classifier: '+$Checks+' synthetic checks passed; no processes or GPU counters sampled.')
