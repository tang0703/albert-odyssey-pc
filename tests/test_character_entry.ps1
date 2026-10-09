$ErrorActionPreference='Stop'
$Repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $Repo 'tools/character.ps1')
$Checks=0
$Calls=[Collections.Generic.List[object]]::new()
function Assert-Check([bool]$Condition,[string]$Message) { if (-not $Condition) { throw $Message }; $script:Checks+=1 }
function Reject([scriptblock]$Code,[string]$Message) {
    $Failed=$false
    try { & $Code | Out-Null } catch { $Failed=$true }
    Assert-Check $Failed $Message
}
function CheckedPython([string[]]$Arguments,[string]$Name) { $script:Calls.Add([pscustomobject]@{kind='python';name=$Name;arguments=$Arguments}) }
function CheckedGodot([string[]]$Arguments,[string]$Name) { $script:Calls.Add([pscustomobject]@{kind='godot';name=$Name;arguments=$Arguments}) }
$RealTests=${function:RunCharacterTests}
$RealExport=${function:ExportCharacter}
function RunCharacterTests { $script:Calls.Add([pscustomobject]@{kind='test';name='actual-tests';arguments=@()}) }
function ExportCharacter { $script:Calls.Add([pscustomobject]@{kind='export';name='export';arguments=@()}) }

# Synthetic routing/pin fixtures never create approved image packages.
$Fixture=Join-Path $Repo ('reports/character/entry-contract-'+[guid]::NewGuid().ToString('N'))
$PcRoot=$Fixture; $Demo=Join-Path $Fixture 'exploration-demo'; $Reports=Join-Path $Fixture 'reports/character'
New-Item -ItemType Directory -Force -Path $Demo,$Reports,(Join-Path $Fixture 'build'),(Join-Path $Fixture 'tests') | Out-Null
$Base=[ordered]@{schema='ao_pc_exploration_bundle_pin_v1';manifest_sha256=('a'*64)}
$Source=[ordered]@{schema='ao_pc_character_bundle_pin_v1';manifest_sha256=('b'*64);scene_manifest_sha256=('a'*64)}
$Hd=[ordered]@{schema='ao_pc_character_hd_bundle_pin_v1';manifest_sha256=('c'*64);scene_manifest_sha256=('a'*64);source_character_manifest_sha256=('b'*64)}
function SavePin([string]$Name,$Value) { ConvertTo-Json $Value | Set-Content -LiteralPath (Join-Path $Demo $Name) -Encoding utf8 }
SavePin 'bundle-pin.json' $Base
SavePin 'character-pin.json' $Source

VerifyBundle
Assert-Check ($Calls[-1].name -eq 'entry-bundle-verify' -and $Calls[-1].arguments -contains '--scene') 'Original bundle verification must explicitly bind the scene directory.'
Reject { VerifyHdBundle } 'Missing HD pin accepted.'
foreach ($Action in @('run','test','export')) {
    $Before=$Calls.Count
    Reject { InvokeCharacterAction } ('Missing HD package permitted '+$Action)
    Assert-Check (@($Calls | Select-Object -Skip $Before | Where-Object {$_.kind -in @('godot','test','export')}).Count -eq 0) 'Missing HD launched a process/test/export.'
}
SavePin 'character-hd-pin.json' $Hd
VerifyHdBundle
Assert-Check ($Calls[-1].name -eq 'entry-hd-bundle-verify' -and $Calls[-1].arguments -contains '--source-character-manifest-sha256') 'HD verification lost independent source-character identity.'
$Hd.source_character_manifest_sha256='d'*64; SavePin 'character-hd-pin.json' $Hd
Reject { VerifyHdBundle } 'Cross-package identity mismatch accepted.'
$Hd.source_character_manifest_sha256='b'*64
$Hd.manifest_sha256='C'*64; SavePin 'character-hd-pin.json' $Hd
Reject { VerifyHdBundle } 'Noncanonical uppercase pin hash accepted.'
$Hd.manifest_sha256='c'*64
$Hd['extra']='unapproved'; SavePin 'character-hd-pin.json' $Hd
Reject { VerifyHdBundle } 'Unknown pin field accepted.'
$Hd.Remove('extra'); SavePin 'character-hd-pin.json' $Hd

$Action='build'; $ArtManifest=''; $ArtSha256=''; $ZipPath=''; $Before=$Calls.Count
InvokeCharacterAction | Out-Null
Assert-Check ($Calls.Count -eq $Before+1 -and $Calls[-1].name -eq 'entry-bundle-build') 'Legacy build must still build only the native package without art arguments.'
$ArtManifest=Join-Path $Fixture 'actual-art-manifest.json'
Set-Content -LiteralPath $ArtManifest -Value '{}' -Encoding utf8
Reject { InvokeCharacterAction } 'Build accepted art without explicit SHA.'
$ArtSha256='d'*64; $Before=$Calls.Count
InvokeCharacterAction | Out-Null
Assert-Check (@($Calls | Select-Object -Skip $Before | Where-Object name -eq 'entry-hd-bundle-build').Count -eq 1) 'Build with explicit art did not invoke HD builder once.'
Assert-Check ($Calls[-2].arguments -contains '--art-sha256' -and $Calls[-2].arguments -contains $ArtSha256) 'HD builder omitted explicit approved art hash.'
$Action='hd-build'; $Before=$Calls.Count
InvokeCharacterAction
Assert-Check (@($Calls | Select-Object -Skip $Before | Where-Object name -eq 'entry-bundle-build').Count -eq 0) 'HD-only build unnecessarily reconstructs original sources.'
$Action='test'
Reject { InvokeCharacterAction } 'Art arguments on test were ignored.'
$ArtManifest=''; $ArtSha256=''
InvokeCharacterAction
Assert-Check ($Calls[-1].kind -eq 'test' -and $Calls[-2].name -eq 'entry-hd-bundle-verify') 'Actual test was not gated by verified HD.'
$Action='run'; InvokeCharacterAction
Assert-Check ($Calls[-1].arguments -contains 'res://character_main.tscn') 'Run lost the independent character entry.'
$Action='export'; InvokeCharacterAction
Assert-Check ($Calls[-1].kind -eq 'export' -and $Calls[-2].name -eq 'entry-hd-bundle-verify') 'Export was not gated by verified HD.'
$Action='run'; $ZipPath='other.zip'
Reject { InvokeCharacterAction } 'ZIP path on unrelated action was ignored.'
$ZipPath=''
$Paths=GetCharacterExportPaths
Assert-Check ([IO.Path]::GetDirectoryName($Paths.output) -eq (Join-Path $Fixture 'build') -and [IO.Path]::GetFileName($Paths.zip) -eq 'MAP001-Character-Windows-x64.zip') 'Export escaped build or used old ZIP name.'
Set-Content -LiteralPath $Paths.zip -Value 'historic delivery'
Reject { GetCharacterExportPaths } 'Existing character ZIP would be overwritten.'
$ZipPath=Join-Path $Fixture 'outside.zip'
Reject { GetCharacterExportPaths } 'ZIP outside build accepted.'
$ZipPath=Join-Path $Fixture 'build/new.exe'
Reject { GetCharacterExportPaths } 'Non-ZIP output accepted.'
$ZipPath=Join-Path $Fixture 'build/new-version.zip'
Assert-Check ((GetCharacterExportPaths).zip -eq $ZipPath) 'Explicit fresh versioned ZIP was rejected.'

# Promotion is a no-overwrite directory rename, never incremental updates of an old release.
$First=GetCharacterExportPaths
$Next=GetCharacterExportPaths
Assert-Check ($First.output -ne $Next.output -and [IO.Path]::GetFileName($First.output) -match '^character-staging-[0-9a-f]{32}$') 'Exports reuse a staging directory.'
Assert-Check ($First.final -eq (Join-Path $Fixture 'build/character-demo')) 'First release should use the unoccupied canonical directory.'
New-Item -ItemType Directory -Path $First.output | Out-Null
Set-Content -LiteralPath (Join-Path $First.output 'sentinel.txt') -Value 'verified fixture bytes'
PublishCharacterDirectory $First
Assert-Check (-not (Test-Path -LiteralPath $First.output) -and (Get-Content -LiteralPath (Join-Path $First.final 'sentinel.txt') -Raw).Trim() -eq 'verified fixture bytes') 'Verified staging promotion lost its bytes.'
$OldHash=(Get-FileHash -LiteralPath (Join-Path $First.final 'sentinel.txt')).Hash
$Later=GetCharacterExportPaths
Assert-Check ($Later.final -ne $First.final -and [IO.Path]::GetFileName($Later.final) -match '^character-demo-[0-9a-f]{32}$') 'Later export targets the existing canonical release.'
New-Item -ItemType Directory -Path $Later.output | Out-Null
Set-Content -LiteralPath (Join-Path $Later.output 'partial.txt') -Value 'failed export retained here'
Assert-Check ((Get-FileHash -LiteralPath (Join-Path $First.final 'sentinel.txt')).Hash -eq $OldHash) 'Partially populated stage modified the old release.'
$Collision=[pscustomobject]@{build=$Later.build;output=$Later.output;final=$First.final}
Reject { PublishCharacterDirectory $Collision } 'Promotion would merge into or overwrite an existing release.'
Assert-Check ((Test-Path -LiteralPath (Join-Path $Later.output 'partial.txt')) -and (Get-FileHash -LiteralPath (Join-Path $First.final 'sentinel.txt')).Hash -eq $OldHash) 'Failed promotion changed the old release or removed staged evidence.'
$Escape=[pscustomobject]@{build=$Later.build;output=$Later.output;final=(Join-Path $Fixture 'character-demo')}
Reject { PublishCharacterDirectory $Escape } 'Promotion accepted a final path outside build.'
PublishCharacterDirectory $Later
Assert-Check ((Test-Path -LiteralPath (Join-Path $Later.final 'partial.txt')) -and (Get-FileHash -LiteralPath (Join-Path $First.final 'sentinel.txt')).Hash -eq $OldHash) 'Versioned promotion modified the preserved old release.'

# Restore actual test orchestrator, stub external processes, and exercise its gates.
Set-Item -Path Function:RunCharacterTests -Value $RealTests
Set-Content -LiteralPath (Join-Path $Reports 'animation-fixtures.json') -Value '{}'
foreach ($Name in @('test_character_qa.ps1','test_character_entry.ps1','test_character_environment_probe.ps1')) { Set-Content -LiteralPath (Join-Path $Fixture ('tests/'+$Name)) -Value "Write-Output 'routing fixture only'" }
$HdReport=[ordered]@{passed=$true;source_comparison_status='passed';source_updates=2052}
ConvertTo-Json $HdReport | Set-Content -LiteralPath (Join-Path $Reports 'entry-hd-validation.json')
Set-Content -LiteralPath (Join-Path $Reports 'entry-test_character_ui.log') -Value 'CHARACTER_UI_HD_STATUS=not_run'
Reject { RunCharacterTests } 'Synthetic HD success replaced missing actual-HD UI parity.'
Set-Content -LiteralPath (Join-Path $Reports 'entry-test_character_ui.log') -Value 'CHARACTER_UI_HD_STATUS=passed'
$UiReport=[ordered]@{schema='ao_pc_character_ui_tests_v2';passed=$true;hd_package_status='passed';source_updates=6156;modes=@('hd','original','marker');synthetic_hd_package=$false}
ConvertTo-Json $UiReport | Set-Content -LiteralPath (Join-Path $Reports 'entry-ui-validation.json')
$HdReport.source_updates=0
ConvertTo-Json $HdReport | Set-Content -LiteralPath (Join-Path $Reports 'entry-hd-validation.json')
Reject { RunCharacterTests } 'No source updates accepted as formal HD comparison.'
$HdReport.source_updates=2052
ConvertTo-Json $HdReport | Set-Content -LiteralPath (Join-Path $Reports 'entry-hd-validation.json')
$UiReport.synthetic_hd_package=$true
ConvertTo-Json $UiReport | Set-Content -LiteralPath (Join-Path $Reports 'entry-ui-validation.json')
Reject { RunCharacterTests } 'Synthetic asset UI report accepted.'
$UiReport.synthetic_hd_package=$false
$UiReport.source_updates=4104
ConvertTo-Json $UiReport | Set-Content -LiteralPath (Join-Path $Reports 'entry-ui-validation.json')
Reject { RunCharacterTests } 'Two-mode UI source coverage accepted as HD parity.'
$UiReport.source_updates=6156
ConvertTo-Json $UiReport | Set-Content -LiteralPath (Join-Path $Reports 'entry-ui-validation.json')
RunCharacterTests | Out-Null
Assert-Check (@($Calls | Where-Object name -eq 'entry-test_character_hd').Count -eq 5) 'Test pipeline omitted HD source/core test.'
Assert-Check (@($Calls | Where-Object name -eq 'entry-test_character_package').Count -eq 1) 'Test pipeline omitted packaging tests after real-HD gate.'

$ParseTokens=$null; $ParseErrors=$null
[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Repo 'tools/character.ps1'),[ref]$ParseTokens,[ref]$ParseErrors) | Out-Null
Assert-Check ($ParseErrors.Count -eq 0) 'Entry script has syntax errors.'
Write-Output ('Character entry contracts passed: '+$Checks+' checks; external processes and art approval were mocked, no real HD export performed.')
