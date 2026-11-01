param([ValidateSet('build','capture')][string]$Action='build', [ValidateSet('refined-01','refined-02','refined-03','refined-04')][string]$ArtVersion='refined-02')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$run=[guid]::NewGuid().ToString('N')
$log=Join-Path $root "reports/unity/headpilot-$Action-$run.log"
Push-Location $root
try {
    $art=Join-Path $root ('art/local/hunyuan-head-v1/'+$ArtVersion)
    $pointer="reports/unity/last-headpilot-$ArtVersion"
    if($Action -eq 'build'){
        $output=Join-Path $root "build/unity-headpilot-$run"
        $arguments=@('-batchmode','-nographics','-quit','-projectPath',('"'+(Join-Path $root 'unity-remake')+'"'),'-executeMethod','Ao.UnityMigration.Editor.HeadPilotReviewBuild.Run','-headArt',('"'+$art+'"'),'-reviewOutput',('"'+$output+'"'),'-logFile',('"'+$log+'"'))
        $unity=Join-Path (Split-Path $root -Parent) 'tools/pc-remake/unity-6000.3.27f2/Editor/Unity.exe'
        $process=Start-Process $unity -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $process.WaitForExit()
        if($process.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review-build.json'))){throw "Head pilot build failed; retained $log"}
        Set-Content reports/unity/last-headpilot-build.txt $output -Encoding UTF8
        Set-Content "$pointer-build.txt" $output -Encoding UTF8
    } else {
        $build=(Get-Content "$pointer-build.txt" -Raw -Encoding UTF8).Trim()
        $manifest=Get-Content (Join-Path $build 'review-build.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $expected=(Get-FileHash -LiteralPath (Join-Path $art 'unity-inputs.json') -Algorithm SHA256).Hash.ToLowerInvariant()
        if($manifest.inputs_sha256 -ne $expected){throw 'Requested head art does not match the built review'}
        $output=Join-Path $root "reports/unity/headpilot-capture-$run"
        $process=Start-Process (Join-Path $build 'Head-Pilot-Review.exe') -ArgumentList @('--review-output',('"'+$output+'"'),'-logFile',('"'+$log+'"')) -WindowStyle Hidden -PassThru
        if(-not $process.WaitForExit(90000)){Stop-Process -Id $process.Id;throw "Static capture timeout; retained $log"}
        if($process.ExitCode -ne 0 -or -not (Test-Path (Join-Path $output 'review.json'))){throw "Static capture failed; retained $log"}
        Set-Content reports/unity/last-headpilot-capture.txt $output -Encoding UTF8
        Set-Content "$pointer-capture.txt" $output -Encoding UTF8
    }
    Write-Output $output
} finally {Pop-Location}
