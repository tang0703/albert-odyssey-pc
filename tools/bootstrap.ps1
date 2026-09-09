param([switch]$SkipDownload)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$InstallRoot = Join-Path $WorkspaceRoot 'tools\pc-remake'
$DownloadRoot = Join-Path $InstallRoot 'downloads'
New-Item -ItemType Directory -Force $DownloadRoot | Out-Null
$release = '4.7.2-stable'
$api = "https://api.github.com/repos/godotengine/godot/releases/tags/$release"
$metadataPath = Join-Path $DownloadRoot 'godot-release.json'
if (-not $SkipDownload) {
    Invoke-WebRequest $api -OutFile $metadataPath
}
$metadata = Get-Content -Raw $metadataPath | ConvertFrom-Json
$names = @('Godot_v4.7.2-stable_win64.exe.zip', 'Godot_v4.7.2-stable_export_templates.tpz', 'SHA512-SUMS.txt')
$records = @()
foreach ($name in $names) {
    $asset = @($metadata.assets | Where-Object name -EQ $name)
    if ($asset.Count -ne 1) { throw "Missing official release asset: $name" }
    $dest = Join-Path $DownloadRoot $name
    if (-not (Test-Path $dest)) {
        if ($SkipDownload) { throw "Missing cached asset: $dest" }
        Invoke-WebRequest $asset[0].browser_download_url -OutFile $dest
    }
    $records += [ordered]@{name=$name;url=$asset[0].browser_download_url;sha256=(Get-FileHash $dest -Algorithm SHA256).Hash;bytes=(Get-Item $dest).Length}
}
$sums = Get-Content (Join-Path $DownloadRoot 'SHA512-SUMS.txt')
foreach ($name in $names[0..1]) {
    $line = @($sums | Where-Object { $_ -match ([regex]::Escape($name) + '$') })
    if ($line.Count -ne 1) { throw "Missing SHA512: $name" }
    $expected = ($line[0] -split '\s+')[0]
    if ((Get-FileHash (Join-Path $DownloadRoot $name) -Algorithm SHA512).Hash -ine $expected) { throw "Checksum mismatch: $name" }
}
$engine = Join-Path $InstallRoot 'godot-4.7.2'
$templates = Join-Path $InstallRoot 'export-templates-4.7.2'
New-Item -ItemType Directory -Force $engine,$templates | Out-Null
& (Join-Path $WorkspaceRoot 'tools\7zip\7z.exe') x (Join-Path $DownloadRoot $names[0]) "-o$engine" -y | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Engine extraction failed' }
& (Join-Path $WorkspaceRoot 'tools\7zip\7z.exe') x (Join-Path $DownloadRoot $names[1]) 'templates/windows_debug_x86_64.exe' 'templates/windows_release_x86_64.exe' 'templates/version.txt' "-o$templates" -y | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Template extraction failed' }
New-Item -ItemType File -Force (Join-Path $engine '_sc_') | Out-Null
$version = & (Join-Path $engine 'Godot_v4.7.2-stable_win64_console.exe') --version
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^4\.7\.2\.stable') { throw "Unexpected engine version: $version" }
$records | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $InstallRoot 'download-manifest.json') -Encoding utf8
Write-Output "Godot verified: $version"
$Python = Join-Path $InstallRoot 'python\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    & python -m venv (Join-Path $InstallRoot 'python')
    if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed' }
}
& $Python -c "import PIL,numpy; assert PIL.__version__ == '11.3.0' and numpy.__version__ == '2.3.2'" 2>$null
if ($LASTEXITCODE -ne 0) {
    if ($SkipDownload) { throw 'Pinned Python dependencies missing; rerun without SkipDownload.' }
    & $Python -m pip install --disable-pip-version-check --index-url https://pypi.org/simple -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
}
$KritaName='krita-x64-5.3.3.zip'
$KritaUrl='https://download.kde.org/stable/krita/5.3.3/krita-x64-5.3.3.zip'
$KritaZip=Join-Path $DownloadRoot $KritaName
# Pinned after the original official HTTPS download; not a publisher signature.
$KritaHash='87278594FAC0267680303280E410578388D606AEC5A290F2B0D009909F4254F0'
if (-not (Test-Path $KritaZip)) {
    if ($SkipDownload) { throw 'Krita archive missing' }
    Invoke-WebRequest $KritaUrl -OutFile $KritaZip
}
if ((Get-FileHash $KritaZip).Hash -ine $KritaHash) { throw 'Krita pinned hash mismatch' }
$KritaRoot=Join-Path $InstallRoot 'krita-5.3.3'
if (-not (Test-Path (Join-Path $KritaRoot 'krita-x64-5.3.3\bin\krita.exe'))) {
    & (Join-Path $WorkspaceRoot 'tools\7zip\7z.exe') x $KritaZip "-o$KritaRoot" -y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Krita extraction failed' }
}
$records += [ordered]@{name=$KritaName;url=$KritaUrl;sha256=$KritaHash;bytes=(Get-Item $KritaZip).Length}
$records | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $InstallRoot 'download-manifest.json') -Encoding utf8
Write-Output 'Pinned Python dependencies ready. Krita extracted; GUI sample acceptance is a separate check.'
