param(
    [Parameter(Mandatory)][string]$Ipl,
    [Parameter(Mandatory)][string]$Disc,
    [Parameter(Mandatory)][string]$Sequence,
    [Parameter(Mandatory)][string]$Output,
    [string]$LoadState,
    [ValidateRange(1,1000000)][int]$SampleEvery = 1,
    [string]$TraceFunction,
    [string[]]$HookPC = @(),
    [string[]]$WatchRange = @()
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$build = Join-Path $project 'reports/exploration/ymir-capture-build'
$executable = Join-Path $build 'Release/ao-ymir-capture.exe'
$buildManifest = Join-Path $build 'build-manifest.json'
if (-not (Test-Path -LiteralPath $buildManifest)) { throw 'Run build.ps1 before capturing' }
$built = Get-Content -LiteralPath $buildManifest -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $executable).Hash -ine $built.executable_sha256) { throw 'Executable differs from build manifest' }
$files = @($Ipl,$Disc,$Sequence)
if ($LoadState) { $files += $LoadState }
# Pin each CUE track, not just the small text descriptor.
if ([IO.Path]::GetExtension($Disc) -ieq '.cue') {
    $base = Split-Path (Resolve-Path -LiteralPath $Disc).Path -Parent
    foreach ($line in Get-Content -LiteralPath $Disc) {
        if ($line -match '^\s*FILE\s+"([^"]+)"\s+') { $files += Join-Path $base $Matches[1] }
    }
}
$inputRecords = @($files | Select-Object -Unique | ForEach-Object {
    $path = (Resolve-Path -LiteralPath $_).Path
    [ordered]@{path=$path;bytes=(Get-Item -LiteralPath $path).Length;sha256=(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()}
})
$arguments = @('--ipl',$Ipl,'--disc',$Disc,'--sequence',$Sequence,'--output',$Output,'--sample-every',"$SampleEvery")
if ($LoadState) { $arguments += @('--load-state',$LoadState) }
if ($TraceFunction) { $arguments += @('--trace-function',$TraceFunction) }
foreach ($pc in $HookPC) { $arguments += @('--hook-pc',$pc) }
foreach ($range in $WatchRange) { $arguments += @('--watch-range',$range) }
& $executable @arguments
if ($LASTEXITCODE) { throw 'Capture failed; partial output is not accepted evidence' }
foreach ($record in $inputRecords) {
    if ((Get-FileHash -LiteralPath $record.path).Hash -ine $record.sha256) { throw "Input changed during capture: $($record.path)" }
}
$root = (Resolve-Path -LiteralPath $Output).Path
$outputs = @(Get-ChildItem -LiteralPath $root -File -Recurse | Sort-Object FullName | ForEach-Object {
    [ordered]@{path=[IO.Path]::GetRelativePath($root,$_.FullName).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
})
[ordered]@{
    schema='ao_ymir_capture_manifest_v1';build=$built;arguments=$arguments;working_directory=(Get-Location).Path;inputs=$inputRecords;outputs=$outputs
    inputs_unchanged=$true;created_utc=[DateTime]::UtcNow.ToString('o')
} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $root 'manifest.json') -Encoding utf8
Write-Output "Capture and hashes verified: $root"
