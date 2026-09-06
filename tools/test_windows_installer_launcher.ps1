param([Parameter(Mandatory=$true)][string]$InstallerDirectory)

$ErrorActionPreference = "Stop"
if($PSVersionTable.PSVersion.Major -ne 5){ throw "Run this regression with Windows PowerShell 5.1." }
$fixture = Join-Path ([IO.Path]::GetTempPath()) ("rb-launcher-regression-" + [guid]::NewGuid().ToString("N"))
$originalLocalAppData = $env:LOCALAPPDATA
$originalResultPath = $env:RB_LAUNCHER_TEST_RESULT
$results = @()
try {
  [void][IO.Directory]::CreateDirectory($fixture)
  # ASCII-only test source, with real Unicode user and argument values at runtime.
  $unicodeName = ([string][char]0x5F20) + ([string][char]0x4E09)
  $unicodeArgument = ([string][char]0x4E2D) + ([string][char]0x6587) + " argument"
  $profile = Join-Path $fixture ($unicodeName + " space")
  $env:LOCALAPPDATA = Join-Path $profile "AppData\Local"
  $BinDir = Join-Path $profile ".local\bin"
  $probe = Join-Path $fixture "launcher-probe.exe"
  Add-Type -OutputAssembly $probe -OutputType ConsoleApplication -TypeDefinition @'
using System;
using System.IO;
using System.Text;
public static class LauncherProbe {
    public static int Main(string[] args) {
        File.WriteAllLines(Environment.GetEnvironmentVariable("RB_LAUNCHER_TEST_RESULT"), args, new UTF8Encoding(false));
        return 37;
    }
}
'@
  $cmdExe = Join-Path ([Environment]::SystemDirectory) "cmd.exe"
  foreach($channel in @("stable", "test")){
    $filename = "install.ps1"
    $AppName = "RedBeacon"
    $CmdName = "redbeacon"
    if($channel -eq "test"){
      $filename = "install-test.ps1"
      $AppName = "RedBeacon_test"
      $CmdName = "redbeacon-test"
    }
    $CliName = "$CmdName-cli"
    $installer = Join-Path $InstallerDirectory $filename
    $source = [IO.File]::ReadAllText($installer)
    if(@([IO.File]::ReadAllBytes($installer) | Where-Object { $_ -gt 127 }).Count){
      throw "$filename must remain ASCII-only."
    }
    $tokens = $null
    $parseErrors = $null
    $ast = [Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$parseErrors)
    if($parseErrors.Count){ throw ($parseErrors | Out-String) }
    $launcherFunction = $ast.Find({param($node)
      $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Write-CliLauncher"
    }, $true)
    if(-not $launcherFunction){ throw "Missing production launcher writer." }
    # Only load the writer. Never execute the installer bootstrap or downloads.
    Invoke-Expression $launcherFunction.Extent.Text
    $Dest = Join-Path $env:LOCALAPPDATA "Programs\$AppName"
    [void][IO.Directory]::CreateDirectory($Dest)
    $cliExe = Join-Path $Dest "$CliName.exe"
    Copy-Item -LiteralPath $probe -Destination $cliExe
    $shim = Join-Path $BinDir "$CmdName.cmd"
    $env:RB_LAUNCHER_TEST_RESULT = Join-Path $fixture "$channel-arguments.txt"

    foreach($mode in @("new", "healthy-repeat")){
      if($mode -eq "new"){
        Write-CliLauncher
      } else {
        # Reproduce the old corrupted shim, then execute the production healthy
        # branch with unrelated skills/desktop effects replaced by no-ops.
        Set-Content -LiteralPath $shim -Encoding ASCII -Value @("@echo off", "`"$cliExe`" %*")
        if(-not ([IO.File]::ReadAllText($shim).Contains("??"))){ throw "Old shim did not reproduce Unicode loss." }
        $healthyIf = $ast.Find({param($node)
          $node -is [Management.Automation.Language.IfStatementAst] -and $node.Extent.Text.StartsWith('if($healthy){')
        }, $true)
        if(-not $healthyIf){ throw "Missing production healthy-install branch." }
        function Install-Skills { }
        function Commit-Skills { }
        function Say { }
        function Start-InstalledApp { }
        $healthy = $true
        $current = "0.0.0"
        $tmp = $fixture
        & ([scriptblock]::Create($healthyIf.Extent.Text))
      }
      if(@([IO.File]::ReadAllBytes($shim) | Where-Object { $_ -gt 127 }).Count){
        throw "The launcher is not ASCII-only."
      }
      Remove-Item -LiteralPath $env:RB_LAUNCHER_TEST_RESULT -Force -ErrorAction SilentlyContinue
      $command = 'chcp 936>nul & "' + $shim + '" --check "' + $unicodeArgument + '" "two words"'
      & $cmdExe /d /c $command
      if($LASTEXITCODE -ne 37){ throw "Launcher did not preserve the probe exit code: $LASTEXITCODE" }
      $arguments = @([IO.File]::ReadAllLines($env:RB_LAUNCHER_TEST_RESULT, [Text.Encoding]::UTF8))
      if($arguments.Count -ne 3 -or $arguments[0] -cne "--check" -or $arguments[1] -cne $unicodeArgument -or $arguments[2] -cne "two words"){
        throw "Launcher did not preserve Unicode and quoted arguments."
      }
      $results += [pscustomobject]@{ channel=$channel; mode=$mode; code_page=936; unicode_and_space_path=$true; arguments_preserved=$true; exit_code_preserved=$true }
    }
  }
  [pscustomobject]@{ powershell=$PSVersionTable.PSVersion.ToString(); checks=$results; passed=$true } | ConvertTo-Json -Depth 4
}
finally {
  $env:LOCALAPPDATA = $originalLocalAppData
  $env:RB_LAUNCHER_TEST_RESULT = $originalResultPath
  if(Test-Path -LiteralPath $fixture){ Remove-Item -LiteralPath $fixture -Recurse -Force }
}
