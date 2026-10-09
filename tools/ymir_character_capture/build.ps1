param([switch]$Fetch)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$workspace = Split-Path $project -Parent
$source = Join-Path $workspace 'tools/pc-remake/ymir-capture-source'
$build = Join-Path $project 'reports/character/ymir-character-capture-build'
$revision = '54fead6a0001d3e4b6741a8d095ee8342266c3dc'
$cerealRevision = 'ebef1e929807629befafbb2918ea1a08c7194554'
$cereal = Join-Path $source 'capture-cereal'
$modules = @('vendor/mio','vendor/fmt','vendor/concurrentqueue/concurrentqueue','vendor/xxHash/xxHash','vendor/libchdr/libchdr')
$v1Files = @((Get-ChildItem -LiteralPath (Join-Path $project 'tools/ymir_capture') -File).FullName)
$v1Files += Join-Path $project 'reports/exploration/ymir-capture-build/Release/ao-ymir-capture.exe'
$v1Files += Join-Path $project 'reports/exploration/ymir-capture-build/build-manifest.json'
$v1Before = @($v1Files | ForEach-Object { [ordered]@{path=$_;sha256=(Get-FileHash -LiteralPath $_).Hash.ToLowerInvariant()} })
if ($Fetch) {
    if (-not (Test-Path -LiteralPath $source)) {
        & git clone --depth 1 --branch v0.3.3 https://github.com/ymir-emu/Ymir.git $source
        if ($LASTEXITCODE) { throw 'Ymir clone failed' }
    }
    & git -C $source -c "safe.directory=$($source.Replace('\','/'))" submodule update --init --depth 1 --jobs 5 -- @modules
    if ($LASTEXITCODE) { throw 'Ymir dependency fetch failed' }
    if (-not (Test-Path -LiteralPath $cereal)) {
        & git clone --depth 1 --branch v1.3.2 https://github.com/USCiLab/cereal.git $cereal
        if ($LASTEXITCODE) { throw 'cereal clone failed' }
    }
}
foreach ($pair in @(@($source,$revision),@($cereal,$cerealRevision))) {
    $actual = & git -C $pair[0] -c "safe.directory=$($pair[0].Replace('\','/'))" rev-parse HEAD
    if ($LASTEXITCODE -or $actual -ne $pair[1]) { throw "Pinned revision mismatch: $($pair[0])" }
    & git -C $pair[0] -c "safe.directory=$($pair[0].Replace('\','/'))" diff --exit-code --ignore-submodules=all HEAD --
    if ($LASTEXITCODE) { throw "Tracked third-party source was modified: $($pair[0])" }
}
$moduleStatus = & git -C $source -c "safe.directory=$($source.Replace('\','/'))" submodule status -- @modules
if ($LASTEXITCODE -or @($moduleStatus | Where-Object { $_ -notmatch '^ ' }).Count) { throw 'Missing or changed core dependency revision' }
foreach ($module in $modules) {
    $path = Join-Path $source $module
    & git -C $path -c "safe.directory=$($path.Replace('\','/'))" diff --exit-code HEAD --
    if ($LASTEXITCODE) { throw "Core dependency source was modified: $module" }
}
$cmake = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
if (-not (Test-Path -LiteralPath $cmake)) { throw 'Expected local Visual Studio CMake was not found' }
& $cmake -S $PSScriptRoot -B $build -G 'Visual Studio 17 2022' -A x64 "-DYMIR_SOURCE_DIR=$($source.Replace('\','/'))"
if ($LASTEXITCODE) { throw 'CMake configure failed' }
& $cmake --build $build --config Release --target ao-ymir-character-capture --parallel 8
if ($LASTEXITCODE) { throw 'Capture build failed' }
$executable = Join-Path $build 'Release/ao-ymir-character-capture.exe'
$sources = Get-ChildItem -LiteralPath $PSScriptRoot -File | Sort-Object Name | ForEach-Object {
    [ordered]@{path=$_.Name;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
}
foreach ($entry in $v1Before) {
    if ((Get-FileHash -LiteralPath $entry.path).Hash -ine $entry.sha256) { throw "Sealed v1 changed: $($entry.path)" }
}
$originalVDP = Join-Path $source 'libs/ymir-core/src/ymir/hw/vdp/vdp.cpp'
$observedVDP = Join-Path $build 'generated/vdp_character.cpp'
[ordered]@{
    schema='ao_ymir_character_capture_build_v2'; ymir_url='https://github.com/ymir-emu/Ymir'; ymir_revision=$revision
    cereal_url='https://github.com/USCiLab/cereal'; cereal_revision=$cerealRevision
    submodules=$moduleStatus; cmake=(& $cmake --version | Select-Object -First 1)
    configuration='Release x64 SSE2; library-only; no extra-inlining; no LTO'
    executable=$executable; executable_sha256=(Get-FileHash -LiteralPath $executable).Hash.ToLowerInvariant(); sources=$sources
    instrumentation=[ordered]@{
        original_path=$originalVDP; original_sha256=(Get-FileHash -LiteralPath $originalVDP).Hash.ToLowerInvariant()
        generated_path=$observedVDP; generated_sha256=(Get-FileHash -LiteralPath $observedVDP).Hash.ToLowerInvariant()
        patch='instrument.cmake'; patch_text=(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'instrument.cmake') -Raw)
        semantics='Const observer only; separate translation unit; upstream checkout is unchanged'
    }
    preserved_v1=$v1Before; preserved_v1_unchanged=$true
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $build 'build-manifest.json') -Encoding utf8
& $executable --help
if ($LASTEXITCODE) { throw 'Capture binary smoke check failed' }
