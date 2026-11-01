param([ValidateSet('build','capture')][string]$Action='capture', [ValidateSet('player-refined-v1','player-refined-v2')][string]$ArtVersion='player-refined-v1', [switch]$SurfaceMaterials)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$toolRoot=Join-Path (Split-Path $root -Parent) 'tools/pc-remake'
$run=[guid]::NewGuid().ToString('N')
$log=Join-Path $root "reports/unity/character-c2-$ArtVersion-$Action-$run.log"
$pointer="reports/unity/last-$ArtVersion-review"
Push-Location $root
try {
    if($Action -eq 'build'){
        $output=Join-Path $root "build/unity-character-review-$run"
        $arguments=@('-batchmode','-nographics','-quit','-projectPath',('"'+(Join-Path $root 'unity-remake')+'"'),'-executeMethod','Ao.UnityMigration.Editor.CharacterReviewBuild.Run','-reviewArt',$ArtVersion,'-reviewOutput',('"'+$output+'"'),'-logFile',('"'+$log+'"'))
        if($SurfaceMaterials){$arguments+='-reviewSurfaceMaterials'}
        $p=Start-Process (Join-Path $toolRoot 'unity-6000.3.27f2/Editor/Unity.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $p.WaitForExit()
        if($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review-build.json'))){throw "Review build failed: $log"}
        Set-Content "$pointer-build.txt" $output -Encoding UTF8
        if($ArtVersion -eq 'player-refined-v1'){Set-Content reports/unity/last-character-review-build.txt $output -Encoding UTF8}
        Get-Content (Join-Path $output 'review-build.json') -Raw
    } else {
        $buildPointer="$pointer-build.txt"
        if($ArtVersion -eq 'player-refined-v1' -and -not (Test-Path $buildPointer)){$buildPointer='reports/unity/last-character-review-build.txt'}
        $build=(Get-Content $buildPointer -Raw -Encoding UTF8).Trim()
        $manifest=Get-Content (Join-Path $build 'review-build.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if($manifest.art_version -ne $ArtVersion -and -not ($ArtVersion -eq 'player-refined-v1' -and -not $manifest.art_version)){throw 'Review build version mismatch'}
        $output=Join-Path $root "reports/unity/character-c2-capture-$run"
        $p=Start-Process (Join-Path $build 'MAP001-Character-Review.exe') -ArgumentList @('--review-output',('"'+$output+'"'),'-logFile',('"'+$log+'"')) -WindowStyle Hidden -PassThru
        if(-not $p.WaitForExit(90000)){Stop-Process -Id $p.Id;throw "Static capture timeout; retained $log"}
        if($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review.json'))){throw "Review capture failed: $log"}
        Set-Content "$pointer-capture.txt" $output -Encoding UTF8
        if($ArtVersion -eq 'player-refined-v1'){Set-Content reports/unity/last-character-review-capture.txt $output -Encoding UTF8}
        Get-Content (Join-Path $output 'review.json') -Raw
    }
} finally {Pop-Location}
