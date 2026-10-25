param([string]$Executable,[string]$OutputRoot,[string[]]$Sizes=@('1920x1080','2560x1440','3840x2160'),[string[]]$States=@('unowned','owned','equipped','removed','boundary'))
$ErrorActionPreference='Stop'
$PcRoot=Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { throw 'Supply a fresh short screenshot output directory.' }
if (Test-Path -LiteralPath $OutputRoot) { throw 'Preserve previous evidence; use a fresh directory.' }
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$OutputRoot=(Resolve-Path -LiteralPath $OutputRoot).ProviderPath
$PriorAppData=$env:APPDATA
$env:APPDATA=Join-Path $OutputRoot 'appdata'
New-Item -ItemType Directory -Path $env:APPDATA | Out-Null
$Results=[Collections.Generic.List[object]]::new()
try {
    foreach ($Size in $Sizes) {
        if ($Size -notin @('1920x1080','2560x1440','3840x2160')) { throw 'Unknown screenshot resolution.' }
        foreach ($State in $States) {
            if ($State -notin @('unowned','owned','equipped','removed','boundary')) { throw 'Unknown equipment state.' }
            $Folder=Join-Path $OutputRoot ($Size+'-'+$State)
            New-Item -ItemType Directory -Path $Folder | Out-Null
            $Report=Join-Path $Folder 'report.json'; $Image=Join-Path $Folder 'screen.png'; $Log=Join-Path $Folder 'engine.log'
            $Launch=$Executable
            $Arguments=@('--log-file',('"'+$Log+'"'))
            if (-not $Launch) {
                $Launch=Join-Path (Split-Path -Parent $PcRoot) 'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
                $Arguments+=@('--path',('"'+(Join-Path $PcRoot 'exploration-demo')+'"'),'res://equipment_main.tscn')
            }
            $Arguments+=@('--',('--qa-size='+$Size),('--equipment-state='+$State),('"--qa-output='+$Image+'"'),('"--qa-report='+$Report+'"'))
            $Process=Start-Process -FilePath $Launch -ArgumentList $Arguments -WindowStyle Hidden -PassThru
            try {
                if (-not $Process.WaitForExit(45000)) { throw 'Short screenshot launch timed out.' }
                if ($Process.ExitCode -ne 0) { throw 'Screenshot process failed.' }
                if ((Get-Content -LiteralPath $Log -Raw) -match 'SCRIPT ERROR:|ERROR:|Parse Error:') { throw 'Engine error; inspect screenshot log.' }
                $Data=Get-Content -LiteralPath $Report -Raw -Encoding UTF8 | ConvertFrom-Json
                if (-not $Data.passed -or -not $Data.surface_verified -or -not $Data.panel_layout_valid -or -not $Data.toolbar_layout_valid -or $Data.performance_tested -ne $false -or $Data.mode -ne 'screenshot' -or ($Data.actual_viewport -join 'x') -ne $Size -or $Data.equipment_state -ne $State) { throw 'Screenshot evidence rejected.' }
                $ExpectedWeapon=if ($State -in @('equipped','boundary')) {27} else {255}
                $ExpectedStory=if ($State -eq 'unowned') {'01'} elseif ($State -eq 'owned') {'03'} else {'07'}
                if ($Data.weapon -ne $ExpectedWeapon -or $Data.story -ne $ExpectedStory -or $Data.boundary_shown -ne ($State -eq 'boundary')) { throw 'Incorrect captured equipment state.' }
                $Results.Add([ordered]@{size=$Size;state=$State;image=$Image;sha256=(Get-FileHash -LiteralPath $Image -Algorithm SHA256).Hash.ToLowerInvariant();report=$Report;report_sha256=(Get-FileHash -LiteralPath $Report -Algorithm SHA256).Hash.ToLowerInvariant()})
                Write-Output ('Screenshot passed: '+$Size+' '+$State)
            } finally { if (-not $Process.HasExited) { $Process.Kill(); $Process.WaitForExit() }; $Process.Dispose() }
        }
    }
    [ordered]@{schema='ao_pc_equipment_screenshots_v1';passed=$true;performance_tested=$false;cases=@($Results.ToArray())} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputRoot 'screenshots.json') -Encoding UTF8
} finally { $env:APPDATA=$PriorAppData }
