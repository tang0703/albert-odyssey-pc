param([ValidateSet('all','directions','room','alignment')][string]$Mode='all')
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $PcRoot
$Python=Join-Path $Workspace 'tools/pc-remake/python/Scripts/python.exe'
$Godot=Join-Path $Workspace 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$ReviewProject=Join-Path $PcRoot 'art/enhanced25d/review-project'
$Reports=Join-Path $PcRoot 'reports/enhanced25d'
& $Python (Join-Path $PSScriptRoot 'prepare_enhanced25d_review.py')
if ($LASTEXITCODE -ne 0) { throw 'Art registration input rejected.' }
$RunFolder=Join-Path $Reports ('review-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $RunFolder | Out-Null
$PriorAppData=$env:APPDATA
try {
    $env:APPDATA=Join-Path $RunFolder 'appdata'
    New-Item -ItemType Directory -Path $env:APPDATA | Out-Null
    $Modes=if ($Mode -eq 'all') {@('directions','room','alignment')} else {@($Mode)}
    foreach ($ReviewMode in $Modes) {
        $Arguments=@('--path',('"'+$ReviewProject+'"'),'--script','res://review.gd','--',('--review='+$ReviewMode),('"--output-dir='+$RunFolder+'"'))
        $Process=Start-Process -FilePath $Godot -ArgumentList $Arguments -WindowStyle Hidden -RedirectStandardOutput (Join-Path $RunFolder ($ReviewMode+'.stdout.log')) -RedirectStandardError (Join-Path $RunFolder ($ReviewMode+'.stderr.log')) -PassThru
        try {
            if (-not $Process.WaitForExit(45000)) { throw 'Art screenshot timed out. Preserve this run for diagnosis.' }
            if ($Process.ExitCode -ne 0) { throw 'Art screenshot failed.' }
            $ErrorLog=Get-Content -LiteralPath (Join-Path $RunFolder ($ReviewMode+'.stderr.log')) -Raw
            if ($ErrorLog -match 'SCRIPT ERROR:|ERROR:|Parse Error:') {throw $ErrorLog}
            if (-not (Test-Path -LiteralPath (Join-Path $RunFolder ($ReviewMode+'-review.png')))) {throw 'Missing art screenshot.'}
        } finally {
            if (-not $Process.HasExited) {$Process.Kill();$Process.WaitForExit()}
            $Process.Dispose()
        }
    }
    Write-Output ('Art review screenshots: '+$RunFolder)
    Write-Output 'Not gameplay acceptance. No performance measurement executed.'
} finally {$env:APPDATA=$PriorAppData}
