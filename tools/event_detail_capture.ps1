param(
    [Parameter(Mandatory)][string]$Sequence,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference='Stop'
$Project=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $Project
$Seed=Join-Path $Project 'reports/exploration/e1-nav-05/frame-000600/state.savestate'
if ((Get-FileHash -LiteralPath $Seed).Hash -ine '72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54') { throw 'Changed named seed' }
$Parameters=@{
    Ipl=Join-Path $Workspace 'EMU/yabause-0.9.15-win64/Bios/SEGA101a[U].bin'
    Disc=Join-Path $Workspace 'Albert Odyssey - Legend of Eldean (USA) (RE)/Albert Odyssey - Legend of Eldean (USA) (RE).cue'
    LoadState=$Seed; Sequence=$Sequence; Output=$Output; SampleEvery=1
    TraceFunction='0x060AB61A'
    HookPC=@('0x0609E092','0x0609E096','0x060AC4E0','0x060AC458',
        '0x06091588','0x0609158E','0x06091594','0x0609159A','0x060915A0',
        '0x060915A6','0x060915AC','0x060915B2','0x060915BE','0x060915C4')
    WatchRange=@('0x060C27AA:8','0x060C41EC:8','0x060C1E1C:16',
        '0x06036642:8','0x060C51D4:64','0x060C6690:64',
        '0x060C7FD8:1280','0x060C84D8:320','0x060C8758:3584','0x060C4260:160',
        '0x060CA358:960','0x06036938:128','0x20220010:832',
        '0x06074080:32','0x06037D68:64','0x060C1F0C:16','0x060CB55A:64')
}
& (Join-Path $PSScriptRoot 'ymir_character_capture/capture.ps1') @Parameters
