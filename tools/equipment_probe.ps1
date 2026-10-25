param(
    [Parameter(Mandatory)][string]$Seed,
    [Parameter(Mandatory)][string]$Sequence,
    [Parameter(Mandatory)][string]$Output,
    [int]$SampleEvery=30,
    [string[]]$HookPC=@()
)
$ErrorActionPreference='Stop'
$Project=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $Project
$Parameters=@{
    Ipl=Join-Path $Workspace 'EMU/yabause-0.9.15-win64/Bios/SEGA101a[U].bin'
    Disc=Join-Path $Workspace 'Albert Odyssey - Legend of Eldean (USA) (RE)/Albert Odyssey - Legend of Eldean (USA) (RE).cue'
    LoadState=$Seed; Sequence=$Sequence; Output=$Output; SampleEvery=$SampleEvery
    TraceFunction='0x060AB61A'
    HookPC=@('0x0609E092','0x0609E096','0x060AC4E0','0x060AC458')+$HookPC
    WatchRange=@('0x06036600:1536','0x060C41EC:8','0x060C8758:112','0x060C4260:160','0x060C7FD8:1280')
}
& (Join-Path $PSScriptRoot 'ymir_character_capture/capture.ps1') @Parameters
