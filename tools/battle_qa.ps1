param([ValidateRange(10,3600)][int]$SoakSeconds=600,[switch]$SkipSoak)
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Exe=Join-Path $PcRoot 'build/battle-demo/Triad-Trial.exe'
$Reports=Join-Path $PcRoot 'reports'
if (-not (Test-Path -LiteralPath $Exe)) { throw 'Export the battle demo first.' }
function Invoke-DemoQa([string]$Name,[string]$Size,[int]$Seconds,[string]$Variant='') {
    $Output=Join-Path $Reports $Name
    New-Item -ItemType Directory -Force $Output | Out-Null
    $Log=Join-Path $Reports ($Name+'-engine.log')
    $Arguments=@('--log-file',('"'+$Log+'"'),'--',('"--qa-dir='+$Output+'"'),('--qa-size='+$Size),('--qa-seconds='+$Seconds))
    if ($Variant) { $Arguments+=('--qa-variant='+$Variant) }
    $Process=Start-Process -FilePath $Exe -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    $Started=Get-Date
    $Samples=[System.Collections.Generic.List[object]]::new()
    while (-not $Process.HasExited) {
        $Process.Refresh()
        $Samples.Add([pscustomobject]@{seconds=[math]::Round(((Get-Date)-$Started).TotalSeconds,2);working_set=$Process.WorkingSet64;private_bytes=$Process.PrivateMemorySize64;peak_working_set=$Process.PeakWorkingSet64})
        if (((Get-Date)-$Started).TotalSeconds -gt [math]::Max(30,$Seconds+30)) {
            # Only stop the exact process created by this invocation.
            $Process.Kill()
            throw ('QA timed out: '+$Name)
        }
        Start-Sleep -Seconds 1
    }
    $Samples | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Output 'process-memory.json')
    if ($Process.ExitCode -ne 0) { throw ('QA failed: '+$Name) }
    $Text=Get-Content -Raw $Log
    if ($Text -match 'SCRIPT ERROR:|Parse Error:|QA render size mismatch') { throw ('QA engine error: '+$Name) }
    $Report=Get-Content -Raw (Join-Path $Output 'report.json') | ConvertFrom-Json
    if (($Report.size -join 'x') -ne $Size) { throw ('QA size mismatch: '+$Name) }
    if ($Seconds -gt 0 -and ($Report.seconds -lt $Seconds -or $Report.battles -lt 1)) { throw 'Soak did not complete battle loops.' }
    Write-Output ($Name+' passed')
}
foreach ($Size in @('1920x1080','2560x1440','3840x2160')) { Invoke-DemoQa ('battle-'+$Size) $Size 0 'selection' }
if (-not $SkipSoak) { Invoke-DemoQa 'battle-soak' '3840x2160' $SoakSeconds }
