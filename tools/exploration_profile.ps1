param([switch]$Launch)
$ErrorActionPreference = 'Stop'
$PcRoot = Split-Path -Parent $PSScriptRoot
$Workspace = Split-Path -Parent $PcRoot
$Profile = Join-Path $PcRoot 'reports\exploration\ymir-profile'
$Executable = Join-Path $Workspace 'tools\ymir\v0.3.3\ymir-sdl3.exe'
$Cue = Join-Path $Workspace 'Albert Odyssey - Legend of Eldean (USA) (RE)\Albert Odyssey - Legend of Eldean (USA) (RE).cue'
$Bios = Join-Path $Workspace 'EMU\yabause-0.9.15-win64\Bios'
$Template = Join-Path $Workspace 'work\ymir\dialogue-trace\Ymir.toml'
foreach ($Path in @($Executable,$Cue,$Bios,$Template)) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Missing local prerequisite: $Path" }
}
$TemplateHash = (Get-FileHash -LiteralPath $Template -Algorithm SHA256).Hash.ToLowerInvariant()
$LegacyLock = Join-Path $PcRoot 'savestate-lock.json'
$LegacyLockHash = if (Test-Path -LiteralPath $LegacyLock) { (Get-FileHash -LiteralPath $LegacyLock -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
$WritableOverrides = [ordered]@{
    BackupMemory = 'backup-memory'
    Dumps = 'dumps'
    ExportedBackups = 'exported-backups'
    PersistentState = 'persistent-state'
    SaveStates = 'savestates'
    Screenshots = 'screenshots'
}
function Set-ConfigPath([string]$Text, [string]$Key, [string]$Target) {
    $Pattern = '(?m)^[ \t]*' + [regex]::Escape($Key) + '[ \t]*=[^\r\n]*'
    if ([regex]::Matches($Text, $Pattern).Count -ne 1) { throw "Expected exactly one config path: $Key" }
    $Quoted = ConvertTo-Json -InputObject $Target.Replace('\','/') -Compress
    return [regex]::Replace($Text, $Pattern, [Text.RegularExpressions.MatchEvaluator]{ param($Match) "$Key = $Quoted" })
}
function Assert-NoReparse([string]$Path) {
    $Cursor = [IO.Path]::GetFullPath($Path)
    while (-not $Cursor.Equals($PcRoot, [StringComparison]::OrdinalIgnoreCase)) {
        if ((Test-Path -LiteralPath $Cursor) -and ((Get-Item -LiteralPath $Cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Isolated profile cannot traverse a symbolic link or junction: $Cursor"
        }
        $Parent = [IO.Directory]::GetParent($Cursor)
        if ($null -eq $Parent) { throw 'Profile escaped its project directory' }
        $Cursor = $Parent.FullName
    }
}
function Assert-PrivatePath([string]$Value, [string]$Key) {
    $Value = $Value.Trim()
    if ($Value -match "^'([^']*)'$") { $Decoded = $Matches[1] }
    elseif ($Value.StartsWith('"')) { $Decoded = ConvertFrom-Json -InputObject $Value }
    else { throw "Unsupported existing path syntax: $Key" }
    if ($Decoded -eq '') { return } # Ymir resolves empty overrides under its -p profile.
    $Resolved = [IO.Path]::GetFullPath($Decoded, $Profile)
    $Prefix = [IO.Path]::GetFullPath($Profile).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    if (-not $Resolved.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Existing profile shares writable path $Key outside its own directory; refusing to launch or overwrite it"
    }
    Assert-NoReparse $Resolved
}
Assert-NoReparse $Profile
New-Item -ItemType Directory -Force -Path $Profile | Out-Null
$Config = Join-Path $Profile 'Ymir.toml'
Assert-NoReparse $Config
$BackupBlockPattern = '(?ms)^[ \t]*\[Cartridge\.BackupRAM\][^\r\n]*\r?\n(?:(?!^[ \t]*\[).)*'
if (-not (Test-Path -LiteralPath $Config)) {
    $Text = Get-Content -LiteralPath $Template -Raw
    $Text = Set-ConfigPath $Text 'IPLROMImages' $Bios
    foreach ($Key in $WritableOverrides.Keys) {
        $Text = Set-ConfigPath $Text $Key (Join-Path $Profile $WritableOverrides[$Key])
    }
    $BackupBlocks = [regex]::Matches($Text, $BackupBlockPattern)
    if ($BackupBlocks.Count -ne 1) { throw 'Expected one Cartridge.BackupRAM section' }
    $BackupBlock = Set-ConfigPath $BackupBlocks[0].Value 'ImagePath' (Join-Path $Profile 'cartridge-backup.ram')
    $Text = $Text.Replace($BackupBlocks[0].Value, $BackupBlock)
    $Text = [regex]::Replace($Text, '(?m)^Mute = false', 'Mute = true')
    $Text = [regex]::Replace($Text, '(?m)^StartPaused = false', 'StartPaused = true')
    [IO.File]::WriteAllText($Config, $Text, [Text.UTF8Encoding]::new($false))
}
$CurrentText = Get-Content -LiteralPath $Config -Raw
foreach ($Key in $WritableOverrides.Keys) {
    $MatchesForKey = [regex]::Matches($CurrentText, ('(?m)^[ \t]*' + $Key + '[ \t]*=([^\r\n]*)'))
    if ($MatchesForKey.Count -ne 1) { throw "Expected one existing config path: $Key" }
    Assert-PrivatePath $MatchesForKey[0].Groups[1].Value $Key
}
$BackupBlocks = [regex]::Matches($CurrentText, $BackupBlockPattern)
if ($BackupBlocks.Count -ne 1) { throw 'Expected one existing Cartridge.BackupRAM section' }
$BackupMatches = [regex]::Matches($BackupBlocks[0].Value, '(?m)^[ \t]*ImagePath[ \t]*=([^\r\n]*)')
if ($BackupMatches.Count -ne 1) { throw 'Expected one existing cartridge backup image path' }
Assert-PrivatePath $BackupMatches[0].Groups[1].Value 'Cartridge.BackupRAM.ImagePath'
if ((Get-FileHash -LiteralPath $Template -Algorithm SHA256).Hash.ToLowerInvariant() -ne $TemplateHash) {
    throw 'Original template changed while preparing the isolated profile'
}
if ($LegacyLockHash -and (Get-FileHash -LiteralPath $LegacyLock -Algorithm SHA256).Hash.ToLowerInvariant() -ne $LegacyLockHash) {
    throw 'Historical save-state lock changed while preparing the isolated profile'
}
$Manifest = [ordered]@{
    schema = 'ao_pc_exploration_profile_v1'
    profile = $Profile
    executable = $Executable
    executable_sha256 = (Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash.ToLowerInvariant()
    cue = $Cue
    cue_sha256 = (Get-FileHash -LiteralPath $Cue -Algorithm SHA256).Hash.ToLowerInvariant()
    bios_reference = $Bios
    template_sha256 = $TemplateHash
    legacy_snapshot_lock_sha256 = $LegacyLockHash
    config_sha256 = (Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash.ToLowerInvariant()
    writable_path_policy = 'All writable PathOverrides stay under the dedicated profile; empty overrides use its defaults'
    old_profile_modified = $false
    old_snapshot_lock_modified = $false
}
if ($Launch) {
    $Process = Start-Process -FilePath $Executable -ArgumentList @('-p', ('"'+$Profile+'"'), '-d', ('"'+$Cue+'"'), '-D', '-P') -WindowStyle Hidden -PassThru
    $Manifest.process_id = $Process.Id
}
$Json = $Manifest | ConvertTo-Json -Depth 5
$LaunchManifest = Join-Path $Profile 'launch.json'
Assert-NoReparse $LaunchManifest
[IO.File]::WriteAllText($LaunchManifest, $Json, [Text.UTF8Encoding]::new($false))
$Json
