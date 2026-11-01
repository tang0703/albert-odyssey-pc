param([ValidateSet('build','capture')][string]$Action='capture')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$toolRoot=Join-Path (Split-Path $root -Parent) 'tools/pc-remake'
$run=[guid]::NewGuid().ToString('N')
$log=Join-Path $root "reports/unity/character-c2-$Action-$run.log"
Push-Location $root
try {
    if($Action -eq 'build'){
        $output=Join-Path $root "build/unity-character-review-$run"
        $p=Start-Process (Join-Path $toolRoot 'unity-6000.3.27f2/Editor/Unity.exe') -ArgumentList @('-batchmode','-nographics','-quit','-projectPath',('"'+(Join-Path $root 'unity-remake')+'"'),'-executeMethod','Ao.UnityMigration.Editor.CharacterReviewBuild.Run','-reviewOutput',('"'+$output+'"'),'-logFile',('"'+$log+'"')) -WindowStyle Hidden -PassThru
        $p.WaitForExit()
        if($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review-build.json'))){throw "Review build failed: $log"}
        Set-Content reports/unity/last-character-review-build.txt $output -Encoding UTF8
        Get-Content (Join-Path $output 'review-build.json') -Raw
    } else {
        $build=(Get-Content reports/unity/last-character-review-build.txt -Raw -Encoding UTF8).Trim()
        $output=Join-Path $root "reports/unity/character-c2-capture-$run"
        $p=Start-Process (Join-Path $build 'MAP001-Character-Review.exe') -ArgumentList @('--review-output',('"'+$output+'"'),'-logFile',('"'+$log+'"')) -WindowStyle Hidden -PassThru
        if(-not $p.WaitForExit(90000)){Stop-Process -Id $p.Id;throw "Static capture timeout; retained $log"}
        if($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review.json'))){throw "Review capture failed: $log"}
        Set-Content reports/unity/last-character-review-capture.txt $output -Encoding UTF8
        Get-Content (Join-Path $output 'review.json') -Raw
    }
} finally {Pop-Location}
