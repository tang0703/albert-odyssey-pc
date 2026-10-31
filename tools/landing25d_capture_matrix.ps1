$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Rows=[Collections.Generic.List[object]]::new()
$States=@('start','equipment-equipped','before','approach','page-1','page-2','page-3','page-4','page-5','page-6','page-7','page-8','after','boundary')
foreach ($Size in @('1920x1080','2560x1440','3840x2160')) {
    foreach ($State in $States) {
        $Folder=& (Join-Path $PSScriptRoot 'landing25d_capture.ps1') -Size $Size -State $State
        $Result=Get-Content -LiteralPath (Join-Path $Folder 'result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($Result.performance_tested -or $Result.mode -ne 'screenshot' -or $Result.measured_seconds -ne 0 -or $Result.effective_appearance -ne 'enhanced25d') {throw 'Invalid short screenshot contract'}
        $Rows.Add(@{size=$Size;state=$State;folder=$Folder})
        ConvertTo-Json -InputObject @($Rows.ToArray()) -Depth 6 | Set-Content -LiteralPath (Join-Path $Root 'reports/enhanced25d-landing/capture-matrix.json') -Encoding UTF8
        Write-Output ($Size+' '+$State+' captured')
    }
}
