param([string]$Size='1920x1080',[string]$State='start',[string]$Mode='enhanced25d')
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Godot=Join-Path (Split-Path -Parent $Root) 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Run=Join-Path $Root ('reports/enhanced25d/capture-'+$Size+'-'+$State+'-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Run | Out-Null
$PreviousAppData=$env:APPDATA
try {
    $env:APPDATA=Join-Path $Run 'appdata'
    New-Item -ItemType Directory -Path $env:APPDATA | Out-Null
    $Args25d=@('--path',('"'+(Join-Path $Root 'exploration-demo')+'"'),'res://enhanced25d_main.tscn','--',('--qa-size='+$Size),('"--qa-output='+(Join-Path $Run 'screen.png')+'"'),('"--qa-report='+(Join-Path $Run 'result.json')+'"'),('--appearance25d='+$Mode))
    if ($State.StartsWith('walk-')) { $Args25d+=('--enhanced-capture='+$State) }
    elseif ($State.StartsWith('equipment-')) { $Args25d+=('--equipment-state='+$State.Substring(10)) }
    elseif ($State.StartsWith('interaction-')) { $Args25d+=('--interaction-state='+$State.Substring(12)) }
    elseif ($State -ne 'start') { $Args25d+=('--landing-event-state='+$State) }
    $Process25d=Start-Process -FilePath $Godot -ArgumentList $Args25d -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Run 'stdout.log') -RedirectStandardError (Join-Path $Run 'stderr.log') -PassThru
    try {
        if (-not $Process25d.WaitForExit(45000)) { 'timeout' | Set-Content (Join-Path $Run 'failure.txt'); throw 'Capture timeout retained for investigation.' }
        if ($Process25d.ExitCode -ne 0) {throw 'Capture process failed'}
        $Errors25d=Get-Content -LiteralPath (Join-Path $Run 'stderr.log') -Raw
        if ($Errors25d -match 'SCRIPT ERROR:|ERROR:|Parse Error:') {throw $Errors25d}
        $Result25d=Get-Content -LiteralPath (Join-Path $Run 'result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $Result25d.passed) {throw 'Capture report failed'}
        Write-Output $Run
    } finally {
        if (-not $Process25d.HasExited) {$Process25d.Kill();$Process25d.WaitForExit()}
        $Process25d.Dispose()
    }
} finally {$env:APPDATA=$PreviousAppData}
