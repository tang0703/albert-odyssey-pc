param([string]$Size='1920x1080')
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Godot=Join-Path (Split-Path -Parent $Root) 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Run=Join-Path $Root ('reports/enhanced25d-landing/phases-'+$Size+'-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Prior=$env:APPDATA
try {
    $env:APPDATA=Join-Path $Run 'appdata';New-Item -ItemType Directory -Path $env:APPDATA | Out-Null
    $ArgsPhase=@('--path',('"'+(Join-Path $Root 'exploration-demo')+'"'),'--script','res://capture_landing25d_phases.gd','--',('--size='+$Size),('"--output='+$Run+'"'))
    $ProcessPhase=Start-Process -FilePath $Godot -ArgumentList $ArgsPhase -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Run 'stdout.log') -RedirectStandardError (Join-Path $Run 'stderr.log') -PassThru
    try {
        if (-not $ProcessPhase.WaitForExit(45000)) { 'timeout' | Set-Content (Join-Path $Run 'failure.txt');throw 'Phase capture timeout retained.' }
        if ($ProcessPhase.ExitCode -ne 0 -or (Get-Content (Join-Path $Run 'stderr.log') -Raw) -match 'SCRIPT ERROR:|ERROR:') {throw ('Phase capture failed: '+$Run)}
        Write-Output $Run
    } finally {
        if (-not $ProcessPhase.HasExited) {$ProcessPhase.Kill();$ProcessPhase.WaitForExit()}
        $ProcessPhase.Dispose()
    }
} finally {$env:APPDATA=$Prior}
