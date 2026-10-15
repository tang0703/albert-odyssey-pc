param(
    [ValidateSet('top','center','bottom','reenter','wait','hold')][string[]]$Routes=@('top','center','bottom','reenter','wait','hold'),
    [Parameter(Mandatory)][string]$OutputRoot
)
$ErrorActionPreference='Stop'
$Project=Split-Path -Parent $PSScriptRoot
foreach ($Route in $Routes) {
    foreach ($Repeat in @('a','b','c')) {
        $Output=Join-Path $OutputRoot ($Route+'-'+$Repeat)
        if (Test-Path -LiteralPath $Output) { throw "Preserve prior evidence: $Output" }
        Write-Output "Capturing event route $Route repeat $Repeat"
        & (Join-Path $PSScriptRoot 'event_capture.ps1') -Sequence (Join-Path $Project "data/event/routes/stair-$Route.txt") -Output $Output -SampleEvery 1
    }
}
