param([ValidateSet('build','launch')][string]$Action='build',[int]$Width=1920,[int]$Height=1080)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$toolRoot=Join-Path (Split-Path $root -Parent) 'tools/pc-remake'
$reports=Join-Path $root 'reports/unity'
Push-Location $root
try {
    & (Join-Path $toolRoot 'python/Scripts/python.exe') -X utf8 tools/unity_presentation_prepare.py
    if($LASTEXITCODE -ne 0){throw 'Source preparation failed'}
    $run=[Guid]::NewGuid().ToString('N')
    $report=Join-Path $reports "u2-$Action-$run.json"
    $log=Join-Path $reports "u2-$Action-$run.log"
    if($Action -eq 'build'){
        $output=Join-Path $root "build/unity-u2-$run"
        $editor=Join-Path $toolRoot 'unity-6000.3.27f2/Editor/Unity.exe'
        $arguments=@('-batchmode','-nographics','-quit','-projectPath',('"'+(Join-Path $root 'unity-remake')+'"'),'-executeMethod','Ao.UnityMigration.Editor.U2Build.Run','-u2Output',('"'+$output+'"'),'-u2Report',('"'+$report+'"'),'-logFile',('"'+$log+'"'))
        $p=Start-Process -FilePath $editor -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $p.WaitForExit()
    } else {
        $output=(Get-Content -LiteralPath (Join-Path $reports 'last-u2-build.txt') -Raw -Encoding UTF8).Trim()
        if(-not [IO.Path]::GetFullPath($output).StartsWith((Join-Path $root 'build/'),[StringComparison]::OrdinalIgnoreCase)){throw 'Invalid build location'}
        $shots=Join-Path $reports "u2-shots-$Width-$run"
        $arguments=@('--u2-report',('"'+$report+'"'),'--u2-shots',('"'+$shots+'"'),'-screen-width',$Width,'-screen-height',$Height,'-screen-fullscreen','0','-logFile',('"'+$log+'"'))
        $p=Start-Process -FilePath (Join-Path $output 'MAP001-Unity-U2.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru
        # One functional route, never a performance loop. Preserve timeout evidence.
        if(-not $p.WaitForExit(90000)){Stop-Process -Id $p.Id;throw "U2 functional startup timeout; retained $log"}
    }
    if($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report)){throw "U2 $Action failed; inspect $log"}
    $evidence=Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
    if($evidence.passed -ne $true){throw "U2 $Action report rejected"}
    if($Action -eq 'build'){Set-Content -LiteralPath (Join-Path $reports 'last-u2-build.txt') -Value $output -Encoding utf8}
    $evidence | ConvertTo-Json
} finally {Pop-Location}
