param([ValidateSet('models','build','review')][string]$Action='review',[string]$ReviewDirectory='', [ValidateSet('startroom-v1','startroom-v2')][string]$ArtVersion='startroom-v2')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$toolRoot=Join-Path (Split-Path $root -Parent) 'tools/pc-remake'
$reports=Join-Path $root 'reports/unity'
$run=[Guid]::NewGuid().ToString('N')
Push-Location $root
try {
    $log=Join-Path $reports "u3-$Action-$run.log"
    if($Action -eq 'models'){
        $modelScript=if($ArtVersion -eq 'startroom-v2'){'tools/unity_draft_models_v2.py'}else{'tools/unity_draft_models.py'}
        & (Join-Path $toolRoot 'blender-5.2.3/blender-5.2.3-windows-x64/blender.exe') --background --factory-startup --python $modelScript *> $log
        if($LASTEXITCODE -ne 0){throw "Blender draft failed: $log"}
        exit
    }
    if($Action -eq 'build'){
        $output=Join-Path $root "build/unity-u3-$run"
        $arguments=@('-batchmode','-nographics','-quit','-projectPath',('"'+(Join-Path $root 'unity-remake')+'"'),'-executeMethod','Ao.UnityMigration.Editor.U3Build.Run','-u3Build',('"'+$output+'"'),'-u3ArtVersion',$ArtVersion,'-logFile',('"'+$log+'"'))
        $p=Start-Process -FilePath (Join-Path $toolRoot 'unity-6000.3.27f2/Editor/Unity.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $p.WaitForExit()
        if($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review-build.txt'))){throw "U3 build failed: $log"}
        Set-Content -LiteralPath (Join-Path $reports 'last-u3-build.txt') -Value $output -Encoding utf8
    } else {
        $output=(Get-Content -LiteralPath (Join-Path $reports 'last-u3-build.txt') -Raw -Encoding UTF8).Trim()
        if(-not [IO.Path]::GetFullPath($output).StartsWith((Join-Path $root 'build/'),[StringComparison]::OrdinalIgnoreCase)){throw 'Unexpected build directory'}
        if($ReviewDirectory -eq ''){$ReviewDirectory=Join-Path $reports "u3-review-$run"}
        $preview=[IO.Path]::GetFullPath($ReviewDirectory)
        if(-not $preview.StartsWith($root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path $preview)){throw 'Review must use a new directory in the repository'}
        $arguments=@('--u3-output',('"'+$preview+'"'),'-logFile',('"'+$log+'"'))
        $p=Start-Process -FilePath (Join-Path $output 'MAP001-Unity-U3-Review.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru
        if(-not $p.WaitForExit(60000)){Stop-Process -Id $p.Id;throw "U3 short capture timeout; retained $log"}
        if($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $preview 'review.json'))){throw "U3 capture failed: $log"}
        Get-Content -LiteralPath (Join-Path $preview 'review.json')
    }
} finally {Pop-Location}
