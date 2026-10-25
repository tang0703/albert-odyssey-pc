param(
    [Parameter(Mandatory)][string[]]$Routes,
    [Parameter(Mandatory)][string]$OutputRoot
)
$ErrorActionPreference='Stop'
$Project=Split-Path -Parent $PSScriptRoot
foreach ($Route in $Routes) {
    if ($Route -notmatch '^[a-z0-9-]+$') { throw 'Invalid route ID' }
    foreach ($Repeat in @('a','b','c')) {
        $Output=Join-Path $OutputRoot ($Route+'-'+$Repeat)
        if (Test-Path -LiteralPath $Output) { throw "Preserve prior evidence: $Output" }
        Write-Output "Capturing interaction $Route repeat $Repeat"
        & (Join-Path $PSScriptRoot 'interaction_capture.ps1') -Sequence (Join-Path $Project "data/interaction/routes/$Route.txt") -Output $Output
    }
}
