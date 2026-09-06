param([Parameter(Mandatory=$true)][string]$SmokeScript)
$ErrorActionPreference = "Stop"
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
  [IO.Path]::GetFullPath($SmokeScript), [ref]$tokens, [ref]$errors
)
if($errors.Count){ throw "Installer smoke source has parser errors" }
$function = $ast.Find({
  param($node)
  $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
  $node.Name -eq "Invoke-ObservedPublicWrapper"
}, $true)
if(-not $function){ throw "Production observer function missing" }
Invoke-Expression $function.Extent.Text
$work = Join-Path ([IO.Path]::GetTempPath()) ("redbeacon-observer-test-" + [guid]::NewGuid().ToString("N"))
[void][IO.Directory]::CreateDirectory($work)
try {
  $fixture = Join-Path $work "short-lived-children.ps1"
  $smokeWrappers = @{ "fixture" = $fixture }
  foreach($count in @(0, 1, 2, 1, 0, 2)){
    $body = @'
for($index=0; $index -lt CHILD_COUNT; $index++){
  $child = Start-Process -FilePath (Join-Path $PSHOME "powershell.exe") -ArgumentList @("-NoProfile", "-NonInteractive", "-Command", "exit 0") -PassThru -Wait -WindowStyle Hidden
  Write-Output ("CHILD_PID=" + $child.Id)
}
$global:LASTEXITCODE = 0
'@
    [IO.File]::WriteAllText($fixture, $body.Replace("CHILD_COUNT", [string]$count))
    $result = Invoke-ObservedPublicWrapper "fixture"
    $expected = @($result.Captured | ForEach-Object {
      if(([string]$_) -match '^CHILD_PID=(\d+)$'){ [int]$Matches[1] }
    } | Sort-Object)
    $actual = @($result.SecondaryPowerShell | ForEach-Object { [int]$_.pid } | Sort-Object)
    if($result.ExitCode -ne 0 -or $expected.Count -ne $count -or $actual.Count -ne $count -or
       ($expected -join ',') -cne ($actual -join ',')){
      throw "Observer missed or invented a short-lived child: expected=$($expected -join ',') actual=$($actual -join ',')"
    }
    if(@(Get-EventSubscriber | Where-Object { $_.SourceIdentifier -like "RedBeaconInstallerSmoke-*" }).Count){
      throw "Observer leaked an event subscription"
    }
    Write-Host "Observer verified $count short-lived children by actual PID"
  }
}
finally { Remove-Item -LiteralPath $work -Recurse -Force }
