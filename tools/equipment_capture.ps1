param(
    [Parameter(Mandatory)][string]$Sequence,
    [Parameter(Mandatory)][string]$Output,
    [ValidateRange(1,1000000)][int]$SampleEvery=60
)
$ErrorActionPreference='Stop'
$Project=Split-Path -Parent $PSScriptRoot
$Workspace=Split-Path -Parent $Project
$Seed=Join-Path $Project 'reports/exploration/e1-nav-05/frame-000600/state.savestate'
$Inputs=@{
    (Join-Path $Workspace 'work/extract/0')='95054f9128b7ab47f88c6659b103e7bee9db94c13548f815bbda5999b30da2ff'
    $Seed='72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54'
    (Join-Path $Workspace 'work/extract/TWN.BIN')='fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6'
    (Join-Path $Workspace 'work/extract/MAP001.TWN')='8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9'
}
foreach ($Path in $Inputs.Keys) {
    if ((Get-FileHash -LiteralPath $Path).Hash -ine $Inputs[$Path]) { throw "Interaction capture source mismatch: $Path" }
}
$Parameters=@{
    Ipl=Join-Path $Workspace 'EMU/yabause-0.9.15-win64/Bios/SEGA101a[U].bin'
    Disc=Join-Path $Workspace 'Albert Odyssey - Legend of Eldean (USA) (RE)/Albert Odyssey - Legend of Eldean (USA) (RE).cue'
    LoadState=$Seed; Sequence=$Sequence; Output=$Output; SampleEvery=$SampleEvery
    TraceFunction='0x060AB61A'
    HookPC=@('0x0609E092','0x0609E096','0x060AC4E0','0x060AC458',
        '0x06091588','0x0609158E','0x06091594','0x0609159A','0x060915A0',
        '0x060915A6','0x060915AC','0x060915B2','0x060915BE','0x060915C4',
        '0x06017EDE','0x060181F4','0x06018226','0x06018248','0x06017FEC','0x060180EA','0x0601813E','0x06017968',
        '0x060AC698','0x060AC776','0x060AC81A','0x060AC826','0x060ACBEA')
    WatchRange=@('0x060C27AA:8','0x060C41EC:8','0x060C1E1C:16',
        '0x06036642:8','0x060C51D4:64','0x060C6690:64',
        '0x060C7FD8:1280','0x060C84D8:320','0x060C8758:3584','0x060C4260:160',
        '0x060CA358:960','0x06036938:128','0x20220010:832',
        '0x06074080:32','0x06037D68:64','0x060C1F0C:16','0x060CB55A:64',
        '0x060CC55A:32','0x060C6236:4','0x060367B4:256','0x060741C0:128','0x06037C40:32',
        '0x060C41FC:96','0x0603666C:328','0x060CB258:2','0x06036600:1536','0x060C27F0:32')
}
& (Join-Path $PSScriptRoot 'ymir_character_capture/capture.ps1') @Parameters
foreach ($Path in $Inputs.Keys) {
    if ((Get-FileHash -LiteralPath $Path).Hash -ine $Inputs[$Path]) { throw "Source changed during capture: $Path" }
}
