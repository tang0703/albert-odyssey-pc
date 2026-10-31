param([Parameter(Mandatory=$true)][string]$Folder)
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Full=(Resolve-Path -LiteralPath $Folder).Path
$Exe=Join-Path $Full 'MAP001-25D-Landing.exe'
$Run=Join-Path $Root ('reports/enhanced25d-landing/extracted-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Prior=$env:APPDATA;$Results=@()
try {
    foreach ($State in @('start','after')) {
        $Case=Join-Path $Run $State;New-Item -ItemType Directory -Path $Case | Out-Null
        $env:APPDATA=Join-Path $Case 'appdata';New-Item -ItemType Directory -Path $env:APPDATA | Out-Null
        $Arguments=@('--','--qa-size=1920x1080',('"--qa-output='+(Join-Path $Case 'screen.png')+'"'),('"--qa-report='+(Join-Path $Case 'result.json')+'"'))
        if ($State -eq 'after') {$Arguments+='--landing-event-state=after'}
        $App=Start-Process -FilePath $Exe -WorkingDirectory $Full -ArgumentList $Arguments -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Case 'stdout.log') -RedirectStandardError (Join-Path $Case 'stderr.log') -PassThru
        try {
            if (-not $App.WaitForExit(45000)) {'timeout' | Set-Content (Join-Path $Case 'failure.txt');throw 'Extracted launch timeout retained.'}
            if ($App.ExitCode -ne 0 -or (Get-Content (Join-Path $Case 'stderr.log') -Raw) -match 'SCRIPT ERROR:|ERROR:') {throw ('Extracted app failed: '+$Case)}
            $Data=Get-Content (Join-Path $Case 'result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            if (-not $Data.passed -or -not $Data.landing25d_preloaded -or $Data.effective_appearance -ne 'enhanced25d' -or $Data.performance_tested) {throw 'Extracted appearance contract failed'}
            if ($State -eq 'after' -and (-not $Data.landing_event_completed -or $Data.scene_id -ne 7)) {throw 'Extracted natural event did not finish'}
            $Results+=@{state=$State;passed=$true;report=(Join-Path $Case 'result.json');exit_code=$App.ExitCode}
        } finally {
            if (-not $App.HasExited) {$App.Kill();$App.WaitForExit()}
            $App.Dispose()
        }
    }
    @{passed=$true;extracted=$Full;launches=$Results;performance_tested=$false;editor_required=$false} | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $Root 'reports/enhanced25d-landing/extracted-launch.json') -Encoding utf8
    Write-Output 'Extracted startup and complete natural LAIA flow passed.'
} finally {$env:APPDATA=$Prior}
