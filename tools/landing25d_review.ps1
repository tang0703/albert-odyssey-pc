param([ValidateSet('room','directions','alignment','all')][string]$Mode='all')
$ErrorActionPreference='Stop'
$Root25d=Split-Path -Parent $PSScriptRoot
$Project25d=Join-Path $Root25d 'art/enhanced25d-landing/review-project'
$Godot25d=Join-Path (Split-Path -Parent $Root25d) 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$Run25d=Join-Path $Root25d ('reports/enhanced25d-landing/review-run-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Run25d | Out-Null
$PreviousAppData25d=$env:APPDATA
try {
    $env:APPDATA=Join-Path $Run25d 'appdata'
    New-Item -ItemType Directory -Path $env:APPDATA | Out-Null
    $Modes25d=if($Mode -eq 'all'){@('directions','room','alignment')}else{@($Mode)}
    foreach($Item25d in $Modes25d){
        $Args25d=@('--path',('"'+$Project25d+'"'),'--script','res://review.gd','--',('--review='+$Item25d))
        $Proc25d=Start-Process -FilePath $Godot25d -ArgumentList $Args25d -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Run25d ($Item25d+'-stdout.log')) -RedirectStandardError (Join-Path $Run25d ($Item25d+'-stderr.log')) -PassThru
        try {
            if(-not $Proc25d.WaitForExit(45000)){'timeout' | Set-Content (Join-Path $Run25d ($Item25d+'-failure.txt'));throw 'Review capture timeout retained.'}
            $Errors25d=Get-Content (Join-Path $Run25d ($Item25d+'-stderr.log')) -Raw
            if($Proc25d.ExitCode -ne 0 -or $Errors25d -match 'ERROR:|Parse Error:|SCRIPT ERROR:'){throw ('Review failed: '+$Errors25d)}
            $Output25d=Join-Path $Root25d ('reports/enhanced25d-landing/'+$Item25d+'-review.png')
            if(-not (Test-Path -LiteralPath $Output25d)){throw 'Review screenshot missing'}
            Copy-Item -LiteralPath $Output25d -Destination (Join-Path $Run25d ($Item25d+'-review.png'))
        } finally {
            if(-not $Proc25d.HasExited){$Proc25d.Kill();$Proc25d.WaitForExit()}
            $Proc25d.Dispose()
        }
    }
    Write-Output $Run25d
} finally {$env:APPDATA=$PreviousAppData25d}
