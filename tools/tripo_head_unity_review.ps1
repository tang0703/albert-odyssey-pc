param([ValidateSet('build','capture')][string]$Action='build',[string]$ArtVersion='prepared-01')
$ErrorActionPreference='Stop'
if($ArtVersion -notmatch '^(prepared|refined|eye-color)-[0-9]{2}$'){throw 'Invalid review version'}
$eyeColor=$ArtVersion.StartsWith('eye-color-')
$root=Split-Path $PSScriptRoot -Parent
$run=[guid]::NewGuid().ToString('N')
$log=Join-Path $root "reports/unity/tripo-head-$Action-$run.log"
Push-Location $root
try {
    $art=Join-Path $root ('art/local/tripo-head-v1/'+$ArtVersion)
    $pointer="reports/unity/last-tripo-head-$ArtVersion"
    if($Action -eq 'build'){
        $output=Join-Path $root "build/unity-tripo-head-$run"
        $arguments=@('-batchmode','-nographics','-quit','-projectPath',('"'+(Join-Path $root 'unity-remake')+'"'),'-executeMethod','Ao.UnityMigration.Editor.HeadPilotReviewBuild.Run','-tripoReview','-headArt',('"'+$art+'"'),'-reviewOutput',('"'+$output+'"'),'-logFile',('"'+$log+'"'))
        if($eyeColor){$arguments+='-eyeColorReview'}
        $unity=Join-Path (Split-Path $root -Parent) 'tools/pc-remake/unity-6000.3.27f2/Editor/Unity.exe'
        $process=Start-Process $unity -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $process.WaitForExit()
        if($process.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review-build.json'))){throw "Build failed; retained $log"}
        Set-Content "$pointer-build.txt" $output -Encoding UTF8
    } else {
        $build=(Get-Content "$pointer-build.txt" -Raw -Encoding UTF8).Trim()
        $manifest=Get-Content (Join-Path $build 'review-build.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $expected=(Get-FileHash -LiteralPath (Join-Path $art 'unity-inputs.json') -Algorithm SHA256).Hash.ToLowerInvariant()
        if(-not $manifest.tripo_review -or $manifest.inputs_sha256 -ne $expected){throw 'Wrong Tripo head build'}
        if($eyeColor -and -not $manifest.eye_color_review){throw 'Wrong eye color build'}
        $output=Join-Path $root "reports/unity/tripo-head-capture-$run"
        $process=Start-Process (Join-Path $build 'Head-Pilot-Review.exe') -ArgumentList @('--review-output',('"'+$output+'"'),'-logFile',('"'+$log+'"')) -WindowStyle Hidden -PassThru
        if(-not $process.WaitForExit(90000)){Stop-Process -Id $process.Id;throw "Capture timeout; retained $log"}
        if($process.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review.json'))){throw "Capture failed; retained $log"}
        Set-Content "$pointer-capture.txt" $output -Encoding UTF8
    }
    Write-Output $output
} finally {Pop-Location}
