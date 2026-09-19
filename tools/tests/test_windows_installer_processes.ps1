param(
  [Parameter(Mandatory=$true)][string]$ProjectRoot,
  [Parameter(Mandatory=$true)][string]$ReportPath
)

# Run the actual installer functions, never either installer at top level.
# All executables and simulated failure cases are confined to this fixture.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$ReportPath = [IO.Path]::GetFullPath($ReportPath)
if(Test-Path -LiteralPath $ReportPath){ throw "Refusing to overwrite regression evidence" }
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ("rb process regression " + [guid]::NewGuid().ToString("N"))
[void][IO.Directory]::CreateDirectory($fixtureRoot)
$started = @()
$checks = @()
$sources = @()
function Say($Message){}
function Die($Message){ throw $Message }

function Start-Probe([string]$Executable){
  [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Executable))
  Copy-Item -LiteralPath $probeBinary -Destination $Executable
  $ready = "$Executable.ready"
  $process = Start-Process -FilePath $Executable -ArgumentList @('"' + $ready + '"') -PassThru -WindowStyle Hidden
  $script:started += $process
  $deadline = [DateTime]::UtcNow.AddSeconds(10)
  do {
    if($process.HasExited){ throw "Process fixture exited early: $Executable" }
    if(Test-Path -LiteralPath $ready){
      try { if([IO.File]::ReadAllText($ready) -eq "ready"){ return $process } } catch [IO.IOException] {}
    }
    Start-Sleep -Milliseconds 50
  } while([DateTime]::UtcNow -lt $deadline)
  throw "Process fixture did not start: $Executable"
}

try {
  $source = Join-Path $fixtureRoot "probe.cs"
  $probeBinary = Join-Path $fixtureRoot "probe.exe"
  [IO.File]::WriteAllText($source, @'
using System;
using System.IO;
using System.Threading;
public class Probe {
    public static void Main(string[] args) { File.WriteAllText(args[0], "ready"); Thread.Sleep(Timeout.Infinite); }
}
'@)
  $compiler = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::Windows)) "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
  if(-not (Test-Path -LiteralPath $compiler)){ throw ".NET Framework x64 compiler is missing" }
  $savedPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $compilerOutput = & $compiler /nologo /target:exe /platform:x64 "/out:$probeBinary" $source 2>&1
    $compilerExit = $LASTEXITCODE
  } finally { $ErrorActionPreference = $savedPreference }
  if($compilerExit -ne 0){ throw "Fixture compiler failed: $compilerOutput" }

  foreach($file in @("install.ps1", "install-test.ps1")){
    $path = Join-Path $ProjectRoot ("install\" + $file)
    $tokens = $null; $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
    if($errors.Count){ throw "Installer parse error: $file" }
    $definitions = @{}
    foreach($name in @("Get-RunningRedBeacon", "Stop-RunningRedBeacon")){
      $definition = $ast.Find({
        param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
      }, $true)
      if(-not $definition){ throw "Installer function missing: $name" }
      $definitions[$name] = $definition.Extent.Text
      Invoke-Expression $definition.Extent.Text
    }
    $sources += [ordered]@{path=$file; sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
    $RedBeaconInstallerExecutionMode = "production"
    $stem = "RBAudit" + [guid]::NewGuid().ToString("N").Substring(0,8)
    $AppName = if($file -eq "install.ps1"){ $stem } else { $stem + "_test" }
    $OtherAppName = if($file -eq "install.ps1"){ $stem + "_test" } else { $stem }
    $CliName = "$AppName-cli"
    $Dest = Join-Path $fixtureRoot $AppName
    $otherDest = Join-Path $fixtureRoot $OtherAppName
    $client = Start-Probe (Join-Path $Dest "$AppName.exe")
    $cli = Start-Probe (Join-Path $Dest "$CliName.exe")
    $renderer = Start-Probe (Join-Path $Dest "RedBeaconRenderer.exe")
    $otherRenderer = Start-Probe (Join-Path $otherDest "RedBeaconRenderer.exe")
    $otherClient = Start-Probe (Join-Path $otherDest "$OtherAppName.exe")
    $unrelated = Start-Probe (Join-Path "$Dest-neighbor" "RedBeaconRenderer.exe")
    $targetIds = @($client.Id, $cli.Id, $renderer.Id)
    $actualIds = @(Get-RunningRedBeacon | ForEach-Object { $_.Id })
    if(@(Compare-Object ($targetIds | Sort-Object) ($actualIds | Sort-Object)).Count){
      throw "The production process selector crossed its channel boundary"
    }
    Stop-RunningRedBeacon
    foreach($process in @($client, $cli, $renderer)){
      if(-not $process.WaitForExit(2000)){ throw "Installer returned before target process exited" }
    }
    foreach($process in @($otherRenderer, $otherClient, $unrelated)){
      if($process.HasExited){ throw "Installer stopped another channel or unrelated renderer" }
      $process.Kill(); [void]$process.WaitForExit(2000)
    }
    $checks += "$file-real-process-channel-isolation-and-exit"

    # An OS refusing termination cannot be created safely with real processes.
    # Simulate that failure while executing the unchanged production wait loop.
    $script:probeClock = [DateTime]::UtcNow
    $script:forceCalls = 0
    function Get-Date { $script:probeClock = $script:probeClock.AddSeconds(1); return $script:probeClock }
    function Start-Sleep {}
    function Get-RunningRedBeacon { [pscustomobject]@{Id=2147483000} }
    function Stop-Process {
      $null = @($input)
      if($args -contains "-Force"){ $script:forceCalls += 1 }
    }
    try {
      $blocked = $false
      try { Stop-RunningRedBeacon } catch {
        if($_.Exception.Message -notlike "*processes did not exit*"){ throw }
        $blocked = $true
      }
      if(-not $blocked -or $script:forceCalls -ne 1){ throw "Unstoppable process did not block the installation" }
      $checks += "$file-unconfirmed-exit-blocks-snapshot-and-replacement"
    } finally {
      foreach($name in @("Get-Date", "Start-Sleep", "Get-RunningRedBeacon", "Stop-Process")){
        Remove-Item -LiteralPath ("Function:\" + $name)
      }
      Invoke-Expression $definitions["Get-RunningRedBeacon"]
    }
  }
  $report = [ordered]@{
    schema="redbeacon-installer-process-regression/v1"
    powershell_version=$PSVersionTable.PSVersion.ToString()
    sources=$sources
    checks=$checks
    passed=$true
  }
  [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($ReportPath))
  [IO.File]::WriteAllText($ReportPath, ($report | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
  Write-Host "Installer process regression passed on PowerShell $($PSVersionTable.PSVersion)"
} finally {
  foreach($process in $started){
    if(-not $process.HasExited){ $process.Kill(); [void]$process.WaitForExit(2000) }
    $process.Dispose()
  }
  Remove-Item -LiteralPath $fixtureRoot -Recurse -Force
}
