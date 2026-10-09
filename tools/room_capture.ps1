param(
    [Parameter(Mandatory)][string]$Sequence,
    [Parameter(Mandatory)][string]$Output,
    [ValidateRange(1,1000000)][int]$SampleEvery = 8,
    [switch]$VideoEvidence,
    [switch]$BoundaryEvidence,
    [switch]$DecorationEvidence
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$workspace = Split-Path $project -Parent
$backend = if ($VideoEvidence) { 'ymir_character_capture/capture.ps1' } else { 'ymir_capture/capture.ps1' }
$params = @{
    Ipl = Join-Path $workspace 'EMU/yabause-0.9.15-win64/Bios/SEGA101a[U].bin'
    Disc = Join-Path $workspace 'Albert Odyssey - Legend of Eldean (USA) (RE)/Albert Odyssey - Legend of Eldean (USA) (RE).cue'
    LoadState = Join-Path $project 'reports/exploration/e1-nav-05/frame-000600/state.savestate'
    Sequence = $Sequence
    Output = $Output
    SampleEvery = $SampleEvery
    TraceFunction = '0x060AB61A'
    HookPC = @('0x06094AFC','0x060AA0DE','0x060AAE20','0x060ABFC8','0x060AC0B6','0x060AC20C','0x060AC34A',
        '0x060915A0','0x0609AE32','0x0609B028','0x0609B254','0x060915A6')
    WatchRange = @('0x060C27AA:8','0x060C41EC:1','0x06036642:2','0x060DDDC4:4',
        '0x20220010:0x340','0x060C8758:0x70','0x060C4200:0x100')
}
if ($BoundaryEvidence) {
    $params.HookPC += @('0x060AC360','0x060AC4A4','0x060AC4E0','0x060A14DE','0x060AC458')
    $params.WatchRange += @('0x060C41EE:2','0x060CB55A:64','0x060C1E26:2')
}
if ($DecorationEvidence) {
    $params.HookPC += @('0x060915AC','0x0609DDB4','0x0609E00A','0x0609DDC4')
    $params.WatchRange += @('0x060CA4C0:120','0x260E8A21:98')
}
if ((Get-FileHash -LiteralPath $params.LoadState).Hash -ine '72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54') {
    throw 'Room capture requires the unchanged named exploration seed'
}
& (Join-Path $PSScriptRoot $backend) @params
