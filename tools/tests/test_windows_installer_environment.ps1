param(
  [Parameter(Mandatory=$true)][string]$ProjectRoot,
  [Parameter(Mandatory=$true)][string]$ReportPath,
  [string]$CliPath,
  [string]$PackagePath,
  [string]$RuntimeProfile,
  [string]$ManifestPath,
  [ValidateSet("stable", "test")][string]$BuildChannel = "test",
  [string]$BuildRunId = "source-regression"
)

# Execute the production functions in both PowerShell hosts. No installer is
# executed at top level, and the optional frozen setup uses only a build cache.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$ReportPath = [IO.Path]::GetFullPath($ReportPath)
if(Test-Path -LiteralPath $ReportPath){ throw "Refusing to overwrite regression evidence" }
$checks = @()
$wrappers = @()
$fixture = Join-Path ([IO.Path]::GetTempPath()) ("rb-env-regression-" + [guid]::NewGuid().ToString("N"))
[void][IO.Directory]::CreateDirectory($fixture)

function Set-ProbeEnvironmentValue([string]$Name, $Value){
  if($null -eq $Value){
    [Environment]::SetEnvironmentVariable($Name, [NullString]::Value, "Process")
  } else {
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
  }
}

function Get-ProbeSnapshot($Names){
  $snapshot = @{}
  foreach($name in $Names){ $snapshot[$name] = [Environment]::GetEnvironmentVariable($name, "Process") }
  return $snapshot
}

function Assert-ProbeSnapshot($Expected){
  foreach($name in $Expected.Keys){
    $actual = [Environment]::GetEnvironmentVariable($name, "Process")
    if(($null -eq $actual) -ne ($null -eq $Expected[$name]) -or $actual -cne $Expected[$name]){
      throw "Caller environment was not restored exactly: $name"
    }
  }
}

function Say($Message){ Write-Host $Message }
function Die($Message){ throw $Message }

try {
  foreach($file in @("install.ps1", "install-test.ps1")){
    $path = Join-Path $ProjectRoot ("install\" + $file)
    $tokens = $null
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
    if($errors.Count){ throw "Installer has parser errors: $file" }
    $keyAssignment = $ast.Find({
      param($node)
      $node -is [Management.Automation.Language.AssignmentStatementAst] -and
      $node.Left.Extent.Text -eq '$script:InstallerEnvironmentKeys'
    }, $true)
    if(-not $keyAssignment){ throw "Installer environment snapshot declaration missing" }
    Invoke-Expression $keyAssignment.Extent.Text
    foreach($name in @("Initialize-TrustedWindowsInstallerEnvironment", "Restore-CallerWindowsInstallerEnvironment", "Push-RuntimeEnvironment", "Pop-RuntimeEnvironment", "Run-BrowserSetup")){
      $definition = $ast.Find({
        param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
      }, $true)
      if(-not $definition){ throw "Production function missing: $name" }
      Invoke-Expression $definition.Extent.Text
    }
    $wrappers += [ordered]@{path=$file; sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
    $Channel = if($file -eq "install.ps1"){ "stable" } else { "test" }
    $RuntimeRoot = Join-Path $fixture $Channel
    $RuntimeDataDir = Join-Path $RuntimeRoot "data"
    $RuntimePlaywrightDir = Join-Path $RuntimeRoot "browser\ms-playwright"
    $RuntimeCloakDir = Join-Path $RuntimeRoot "browser\cloakbrowser"
    $allNames = @($script:InstallerEnvironmentKeys) + @("REDBEACON_DESKTOP_SMOKE", "REDBEACON_DESKTOP_SMOKE_DATA_DIR", "REDBEACON_OUT")
    $processBefore = Get-ProbeSnapshot $allNames
    try {
      foreach($state in @("absent", "empty", "configured")){
        foreach($failure in @($false, $true)){
          $value = if($state -eq "absent"){ $null } elseif($state -eq "empty"){ "" } else { "C:\caller tools\node.exe" }
          Set-ProbeEnvironmentValue "PLAYWRIGHT_NODEJS_PATH" $value
          Set-ProbeEnvironmentValue "CLOAKBROWSER_BINARY_PATH" $value
          $script:OriginalInstallerEnvironment = Get-ProbeSnapshot $script:InstallerEnvironmentKeys
          try {
            Initialize-TrustedWindowsInstallerEnvironment
            foreach($cleared in @("PLAYWRIGHT_NODEJS_PATH", "CLOAKBROWSER_BINARY_PATH", "CLOAKBROWSER_VERSION", "CLOAKBROWSER_SKIP_CHECKSUM")){
              if($null -ne [Environment]::GetEnvironmentVariable($cleared, "Process")){
                throw "Installer retained an empty or configured override: $cleared"
              }
            }
            if($env:REDBEACON_CHANNEL -cne $Channel){ throw "Installer channel changed" }
            Set-ProbeEnvironmentValue "CLOAKBROWSER_BINARY_PATH" $value
            $runtimeBefore = Get-ProbeSnapshot $allNames
            $runtimeSaved = Push-RuntimeEnvironment
            try {
              if($null -ne [Environment]::GetEnvironmentVariable("CLOAKBROWSER_BINARY_PATH", "Process")){
                throw "Runtime setup did not remove the binary override"
              }
              if($failure){ throw [InvalidOperationException]::new("injected-setup-failure") }
            }
            catch {
              if($_.Exception.Message -ne "injected-setup-failure"){ throw }
            }
            finally { Pop-RuntimeEnvironment $runtimeSaved }
            Assert-ProbeSnapshot $runtimeBefore
          }
          finally { Restore-CallerWindowsInstallerEnvironment }
          Assert-ProbeSnapshot $script:OriginalInstallerEnvironment
          $checks += "$file/$state/failure-$failure/restored"
        }
      }

      if($CliPath -and $Channel -eq $BuildChannel){
        if(-not $PackagePath -or -not $RuntimeProfile -or -not $ManifestPath){ throw "Frozen probe inputs are incomplete" }
        $CliPath = [IO.Path]::GetFullPath($CliPath)
        $RuntimeProfile = [IO.Path]::GetFullPath($RuntimeProfile)
        $script:ReleaseManifestFile = [IO.Path]::GetFullPath($ManifestPath)
        $script:OriginalInstallerEnvironment = Get-ProbeSnapshot $script:InstallerEnvironmentKeys
        try {
          Initialize-TrustedWindowsInstallerEnvironment
          # Only the test process selects a disposable build profile. Production
          # startup and Run-BrowserSetup remain byte-for-byte installer functions.
          $env:USERPROFILE = $RuntimeProfile
          $runtimeName = if($Channel -eq "test"){ ".redbeacon_test" } else { ".redbeacon" }
          $RuntimeRoot = Join-Path $RuntimeProfile $runtimeName
          $RuntimeDataDir = Join-Path $RuntimeRoot "data"
          $RuntimePlaywrightDir = Join-Path $RuntimeRoot "browser\ms-playwright"
          $RuntimeCloakDir = Join-Path $RuntimeRoot "browser\cloakbrowser"
          $database = Join-Path $RuntimeDataDir "redbeacon.db"
          $databaseBefore = if(Test-Path $database){ (Get-FileHash $database -Algorithm SHA256).Hash } else { $null }
          Run-BrowserSetup $CliPath
          $databaseAfter = if(Test-Path $database){ (Get-FileHash $database -Algorithm SHA256).Hash } else { $null }
          if($databaseBefore -cne $databaseAfter){ throw "Browser setup changed the database" }
          $checks += "frozen-cli/installer-browser-setup/real-launch"
          $checks += "frozen-cli/installer-browser-setup/database-unchanged"
        }
        finally { Restore-CallerWindowsInstallerEnvironment }
        Assert-ProbeSnapshot $script:OriginalInstallerEnvironment
      }
    }
    finally {
      foreach($name in $processBefore.Keys){ Set-ProbeEnvironmentValue $name $processBefore[$name] }
    }
  }
  $report = [ordered]@{
    schema = "redbeacon-powershell-environment-regression/v1"
    powershell_version = $PSVersionTable.PSVersion.ToString()
    build_run_id = $BuildRunId
    channel = $BuildChannel
    wrappers = $wrappers
    checks = $checks
    frozen_cli_sha256 = if($CliPath){ (Get-FileHash -LiteralPath $CliPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    package_sha256 = if($PackagePath){ (Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
  }
  [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($ReportPath))
  [IO.File]::WriteAllText($ReportPath, (($report | ConvertTo-Json -Depth 8) + "`n"), [Text.UTF8Encoding]::new($false))
  Write-Host "PowerShell $($PSVersionTable.PSVersion) installer environment regression passed ($($checks.Count) checks)"
}
finally { Remove-Item -LiteralPath $fixture -Recurse -Force -ErrorAction SilentlyContinue }
