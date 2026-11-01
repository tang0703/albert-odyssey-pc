param([ValidateSet('sources','guard','build','launch')][string]$Action='sources')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$toolRoot=Join-Path (Split-Path $root -Parent) 'tools/pc-remake'
$python=Join-Path $toolRoot 'python/Scripts/python.exe'
$editor=Join-Path $toolRoot 'unity-6000.3.27f2/Editor/Unity.exe'
$reportRoot=Join-Path $root 'reports/unity'
New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
Push-Location $root
try {
    & $python -X utf8 tools/unity_source_baseline.py verify
    if($LASTEXITCODE -ne 0){throw 'Source verification failed'}
    if($Action -eq 'sources'){
        & $python -X utf8 tools/unity_source_baseline.py inventory
        if($LASTEXITCODE -ne 0){throw 'Inventory failed'}
        & $python -X utf8 tools/unity_source_baseline.py prepare
        if($LASTEXITCODE -ne 0){throw 'Prepare failed'}
    }
    if($Action -eq 'guard'){
        $env:DOTNET_CLI_HOME=Join-Path $toolRoot 'dotnet-home'
        $env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
        $env:DOTNET_ADD_GLOBAL_TOOLS_TO_PATH='0'
        $env:DOTNET_GENERATE_ASPNET_CERTIFICATE='0'
        & (Join-Path $toolRoot 'dotnet-8.0.427/dotnet.exe') run --project tools/unity-tests/SourceGuardTests.csproj -- $root
        if($LASTEXITCODE -ne 0){throw 'C# source guard failed'}
    }
    if($Action -eq 'build'){
        if(-not (Test-Path -LiteralPath $editor)){throw 'Locked Unity editor is not ready'}
        $run=[Guid]::NewGuid().ToString('N')
        $output=Join-Path $root "build/unity-u1-$run"
        $buildReport=Join-Path $reportRoot "u1-build-$run.json"
        $arguments=@('-batchmode','-nographics','-quit','-projectPath',('"'+(Join-Path $root 'unity-remake')+'"'),'-executeMethod','Ao.UnityMigration.Editor.U1Build.Run','-u1Output',('"'+$output+'"'),'-u1Report',('"'+$buildReport+'"'),'-logFile',('"'+(Join-Path $reportRoot "u1-build-$run.log")+'"'))
        $p=Start-Process -FilePath $editor -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $p.WaitForExit()
        if($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $buildReport)){throw 'Unity U1 build did not pass; inspect the new log, not old reports'}
        $evidence=Get-Content -LiteralPath $buildReport -Raw -Encoding UTF8 | ConvertFrom-Json
        if($evidence.passed -ne $true){throw 'Unity U1 build report did not pass'}
        Set-Content -LiteralPath (Join-Path $reportRoot 'last-u1-build.txt') -Value $output -Encoding utf8
    }
    if($Action -eq 'launch'){
        $output=(Get-Content -LiteralPath (Join-Path $reportRoot 'last-u1-build.txt') -Raw -Encoding UTF8).Trim()
        $resolved=[IO.Path]::GetFullPath($output)
        if(-not $resolved.StartsWith((Join-Path $root 'build/') ,[StringComparison]::OrdinalIgnoreCase)){throw 'Unexpected U1 build directory'}
        $run=[Guid]::NewGuid().ToString('N')
        $report=Join-Path $reportRoot "u1-launch-$run.json"
        $log=Join-Path $reportRoot "u1-launch-$run.log"
        $p=Start-Process -FilePath (Join-Path $output 'MAP001-Unity-U1.exe') -ArgumentList @('--u1-smoke-report',('"'+$report+'"'),'-logFile',('"'+$log+'"')) -WindowStyle Hidden -PassThru
        if(-not $p.WaitForExit(45000)){Stop-Process -Id $p.Id; throw 'U1 short launch timed out; log retained'}
        if($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report)){throw 'U1 launch failed'}
        $evidence=Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
        if($evidence.passed -ne $true){throw 'U1 probe rejected runtime'}
        $evidence | ConvertTo-Json
    }
} finally {Pop-Location}
