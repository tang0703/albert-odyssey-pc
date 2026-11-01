param([ValidateSet('build','capture')][string]$Action='build',[string]$ArtVersion='body-fit-01',[switch]$TripoBody)
$ErrorActionPreference='Stop'
if($ArtVersion -notmatch '^body-fit-[0-9]{2}$'){throw 'Invalid body review version'}
$root=Split-Path $PSScriptRoot -Parent
$run=[guid]::NewGuid().ToString('N');$log=Join-Path $root "reports/unity/body-$Action-$run.log"
Push-Location $root
try {
    $family=if($TripoBody){'tripo-body-v1'}else{'tripo-head-v1'}
    $art=Join-Path $root ('art/local/'+$family+'/'+$ArtVersion)
    $pointer=if($TripoBody){"reports/unity/last-tripo-$ArtVersion"}else{"reports/unity/last-$ArtVersion"}
    if($Action -eq 'build'){
        $output=Join-Path $root "build/unity-body-review-$run"
        $arguments=@('-batchmode','-nographics','-quit','-projectPath',('"'+(Join-Path $root 'unity-remake')+'"'),'-executeMethod','Ao.UnityMigration.Editor.BodyFitReviewBuild.Run','-bodyArt',('"'+$art+'"'),'-reviewOutput',('"'+$output+'"'),'-logFile',('"'+$log+'"'))
        $unity=Join-Path (Split-Path $root -Parent) 'tools/pc-remake/unity-6000.3.27f2/Editor/Unity.exe'
        $process=Start-Process $unity -ArgumentList $arguments -WindowStyle Hidden -PassThru;$process.WaitForExit()
        if($process.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review-build.json'))){throw "Build failed; retained $log"}
        Set-Content "$pointer-build.txt" $output -Encoding UTF8
    } else {
        $build=(Get-Content "$pointer-build.txt" -Raw -Encoding UTF8).Trim();$manifest=Get-Content (Join-Path $build 'review-build.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $expected=(Get-FileHash -LiteralPath (Join-Path $art 'unity-inputs.json') -Algorithm SHA256).Hash.ToLowerInvariant()
        if($manifest.art -ne $ArtVersion -or $manifest.inputs_sha256 -ne $expected){throw 'Wrong body review build'}
        $output=Join-Path $root "reports/unity/body-capture-$run"
        $process=Start-Process (Join-Path $build 'Body-Fit-Review.exe') -ArgumentList @('-force-d3d11','--review-output',('"'+$output+'"'),'-logFile',('"'+$log+'"')) -WindowStyle Hidden -PassThru
        $processHandle=$process.Handle
        if(-not $process.WaitForExit(90000)){Stop-Process -Id $process.Id;throw "Capture timeout; retained $log"}
        $process.WaitForExit();$process.Refresh()
        @{exit_code=$process.ExitCode;has_exited=$process.HasExited;output=$output;log=$log} | ConvertTo-Json | Set-Content "$log.process.json" -Encoding UTF8
        if($process.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review.json'))){throw "Capture failed; retained $log"}
        Set-Content "$pointer-capture.txt" $output -Encoding UTF8
    }
    Write-Output $output
} finally {Pop-Location}
