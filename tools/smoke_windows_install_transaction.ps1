param(
  [string]$ProjectRoot = ".",
  [string]$PythonExe = "python.exe",
  [Parameter(Mandatory=$true)][string]$ReportPath,
  [Parameter(Mandatory=$true)][string]$BuildRunId,
  [Parameter(Mandatory=$true)][string]$RootCommit,
  [Parameter(Mandatory=$true)][string]$CliCommit,
  [Parameter(Mandatory=$true)][string]$Version,
  [Parameter(Mandatory=$true)][ValidateSet("stable", "test")][string]$Channel
)

# Local Windows installer smoke. Everything except temporary shortcuts is
# redirected under one disposable home; pre-existing shortcuts are restored.
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$PythonExe = [System.IO.Path]::GetFullPath($PythonExe)
$ReportPath = [System.IO.Path]::GetFullPath($ReportPath)
if(-not (Test-Path $PythonExe)){ throw "Python executable not found: $PythonExe" }
if($BuildRunId -cnotmatch '^[a-z0-9][a-z0-9_-]{15,127}$'){ throw "BuildRunId has an invalid format" }
if($RootCommit -cnotmatch '^(?:[0-9a-f]{40}|[0-9a-f]{64})$'){ throw "RootCommit must be a full lowercase Git object id" }
if($CliCommit -cnotmatch '^(?:[0-9a-f]{40}|[0-9a-f]{64})$'){ throw "CliCommit must be a full lowercase Git object id" }
if($Version -cnotmatch '^\d+\.\d+\.\d+$'){ throw "Version must be a three-part semantic version" }
if([System.IO.File]::Exists($ReportPath) -or [System.IO.Directory]::Exists($ReportPath)){
  throw "Refusing to overwrite installer smoke report: $ReportPath"
}

& (Join-Path $PSScriptRoot "tests\smoke_windows_process_observer.ps1") -SmokeScript $PSCommandPath

$scripts = @(
  "install\install.ps1",
  "install\install-test.ps1",
  "install\uninstall.ps1",
  "install\uninstall-core.ps1",
  "install\uninstall-test.ps1"
)
$publicWrappers = @(
  "install\install.ps1",
  "install\install-test.ps1",
  "install\uninstall.ps1",
  "install\uninstall-test.ps1"
)
$publicWrapperHashes = @{}
$coreHashes = @{}
foreach($relative in $scripts){
  $path = Join-Path $ProjectRoot $relative
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors) | Out-Null
  if($errors -and $errors.Count -gt 0){
    throw "$relative has PowerShell parser errors: $($errors | Out-String)"
  }
  Write-Host "PowerShell syntax ok: $relative"
  if($publicWrappers -contains $relative){
    $publicWrapperHashes[$relative] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
  } elseif($relative -like "*core.ps1") {
    $coreHashes[$relative] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
  }
}

# Windows Defender, the renderer, or the newly launched desktop process can
# retain a TEMP handle briefly after installation. Reproduce that exact case:
# cleanup may leave the temporary directory behind, but it must not throw and
# turn an already committed installation into a reported failure.
$installerPath = Join-Path $ProjectRoot "install\install.ps1"
$cleanupTokens = $null
$cleanupErrors = $null
$installerAst = [System.Management.Automation.Language.Parser]::ParseFile(
  $installerPath, [ref]$cleanupTokens, [ref]$cleanupErrors
)
$cleanupAst = $installerAst.Find({
  param($node)
  return ($node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
          $node.Name -eq "Remove-InstallerTemp")
}, $true)
if(-not $cleanupAst){ throw "install.ps1 has no Remove-InstallerTemp function" }
Invoke-Expression $cleanupAst.Extent.Text
function Warn($m){ Write-Host "!! $m" -ForegroundColor Yellow }
$cleanupProbe = Join-Path $env:TEMP ("redbeacon_cleanup_lock_" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $cleanupProbe | Out-Null
$lockedFile = Join-Path $cleanupProbe "locked.tmp"
$lockHandle = [System.IO.File]::Open(
  $lockedFile,
  [System.IO.FileMode]::Create,
  [System.IO.FileAccess]::ReadWrite,
  [System.IO.FileShare]::None
)
try {
  Remove-InstallerTemp $cleanupProbe
  if(-not [System.IO.Directory]::Exists($cleanupProbe)){
    throw "cleanup lock probe unexpectedly removed an open Windows file"
  }
}
finally {
  $lockHandle.Dispose()
  Remove-Item -LiteralPath $cleanupProbe -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "Windows locked TEMP cleanup is non-fatal"

$work = Join-Path $env:TEMP ("redbeacon_installer_smoke_" + [guid]::NewGuid())
$fake = Join-Path $work "fake-oss"
$build = Join-Path $work "fake-build"
$fakeHome = Join-Path $work "home"
$fakeLocalAppData = Join-Path $work "localappdata"
$fakeAppData = Join-Path $work "appdata"
New-Item -ItemType Directory -Force -Path $fake, $build, $fakeHome, $fakeLocalAppData, $fakeAppData | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $fakeHome "Desktop") | Out-Null

$originalHome = $HOME
$originalUserProfile = $env:USERPROFILE
$originalLocalAppData = $env:LOCALAPPDATA
$originalAppData = $env:APPDATA
$originalTemp = $env:TEMP
$originalCi = $env:CI
$originalNoPause = $env:REDBEACON_NO_PAUSE
$originalPurge = $env:REDBEACON_PURGE
$originalForceInstall = $env:REDBEACON_FORCE_INSTALL
$originalProcessPath = $env:Path
$hostileEnvironmentNames = @(
  "HOME",
  "USERPROFILE",
  "LOCALAPPDATA",
  "APPDATA",
  "PATH",
  "TEMP",
  "TMP",
  "TMPDIR",
  "PSModulePath",
  "REDBEACON_CHANNEL",
  "REDBEACON_BUILD_CHANNEL",
  "REDBEACON_UPDATE_URL",
  "REDBEACON_UPDATE_WORKDIR",
  "REDBEACON_DATA_DIR",
  "REDBEACON_LOG_DIR",
  "REDBEACON_SKILL_DIR",
  "REDBEACON_CODEX_SKILL_DIR",
  "REDBEACON_OPENCLAW_SKILL_DIR",
  "REDBEACON_HERMES_SKILL_DIR",
  "REDBEACON_WORKBUDDY_SKILL_DIR",
  "REDBEACON_PLAYWRIGHT_DIR",
  "REDBEACON_CLOAKBROWSER_DIR",
  "PLAYWRIGHT_BROWSERS_PATH",
  "CLOAKBROWSER_CACHE_DIR",
  "CLOAKBROWSER_BINARY_PATH",
  "CLOAKBROWSER_VERSION",
  "CLOAKBROWSER_SKIP_CHECKSUM",
  "BYTESTAFF_HOME",
  "REDBEACON_OSS",
  "REDBEACON_PLAYWRIGHT_DOWNLOAD_URL",
  "REDBEACON_CLOAKBROWSER_DOWNLOAD_URL",
  "REDBEACON_INSTALLER_TEST_MODE",
  "REDBEACON_INSTALL_MANIFEST_FILE",
  "REDBEACON_OUT",
  "REDBEACON_HIJACK_MARKER"
)
$originalHostileEnvironment = @{}
foreach($name in $hostileEnvironmentNames){
  $originalHostileEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$originalPersistentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$shortcutBackup = Join-Path $work "shortcut-backup"
New-Item -ItemType Directory -Force -Path $shortcutBackup | Out-Null
$shortcutDirs = @(
  [Environment]::GetFolderPath("Desktop"),
  (Join-Path $originalAppData "Microsoft\Windows\Start Menu\Programs")
)
foreach($dir in $shortcutDirs){
  foreach($name in @("RedBeacon.lnk", "RedBeacon_test.lnk")){
    $path = Join-Path $dir $name
    if(Test-Path $path){ Copy-Item -Force $path (Join-Path $shortcutBackup ($dir.GetHashCode().ToString() + "-" + $name)) }
  }
}

$centralOrigin = "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
$smokeOrigin = "http://127.0.0.1:8765"
$smokeWrapperDir = Join-Path $work "smoke-wrappers"
$serverRequestLog = Join-Path $work "http-server-requests.log"
$smokeWrappers = @{}
$productionTestWrappers = @{}

function ConvertTo-PowerShellSingleQuotedLiteral([string]$Value) {
  return "'" + $Value.Replace("'", "''") + "'"
}

function New-SmokeWrappers() {
  New-Item -ItemType Directory -Force -Path $smokeWrapperDir | Out-Null
  foreach($relative in $publicWrappers){
    $source = Join-Path $ProjectRoot $relative
    $name = Split-Path $relative -Leaf
    $destination = Join-Path $smokeWrapperDir $name
    $text = [System.IO.File]::ReadAllText($source, [System.Text.UTF8Encoding]::new($false, $true))
    $fixedChannel = if($name -like "*-test.ps1"){ "test" } else { "stable" }
    $canonicalUrl = "$centralOrigin/projects/redbeacon/$fixedChannel/latest.json"
    if([regex]::Matches($text, [regex]::Escape($canonicalUrl)).Count -ne 2){
      throw "$relative does not contain exactly two fixed canonical-manifest literals"
    }
    foreach($forbidden in @(
      "REDBEACON_INSTALLER_TEST_MODE", "RedBeaconStableManifestUrl", "RedBeaconTestManifestUrl"
    )){
      if($text.Contains($forbidden)){ throw "$relative still accepts forbidden channel input: $forbidden" }
    }
    $knownFolders = @{
      '[Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)' = (ConvertTo-PowerShellSingleQuotedLiteral $fakeHome)
      '[Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)' = (ConvertTo-PowerShellSingleQuotedLiteral $fakeLocalAppData)
      '[Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData)' = (ConvertTo-PowerShellSingleQuotedLiteral $fakeAppData)
    }
    foreach($entry in $knownFolders.GetEnumerator()){
      if([regex]::Matches($text, [regex]::Escape($entry.Key)).Count -ne 1){
        throw "$relative lost its fixed Windows known-folder expression: $($entry.Key)"
      }
      $text = $text.Replace($entry.Key, $entry.Value)
    }
    if($name.StartsWith("install")){
      $desktopExpression = '[Environment]::GetFolderPath("Desktop")'
      if([regex]::Matches($text, [regex]::Escape($desktopExpression)).Count -ne 2){
        throw "$relative lost its two Windows desktop known-folder expressions"
      }
      $text = $text.Replace(
        $desktopExpression,
        (ConvertTo-PowerShellSingleQuotedLiteral (Join-Path $fakeHome "Desktop"))
      )
    }
    foreach($required in @(
      '[Environment]::SystemDirectory', 'Microsoft.PowerShell.Utility\Invoke-WebRequest',
      'Microsoft.PowerShell.Utility\Get-FileHash'
    )){
      if(-not $text.Contains($required)){ throw "$relative lost trusted execution primitive: $required" }
    }
    if($name.StartsWith("install")){
      $argumentGuardIndex = $text.IndexOf('$args.Count -ne 0')
      $firstNetworkIndex = $text.IndexOf('Microsoft.PowerShell.Utility\Invoke-WebRequest')
      if($argumentGuardIndex -lt 0 -or $firstNetworkIndex -lt 0 -or $argumentGuardIndex -gt $firstNetworkIndex){
        throw "$relative does not reject arguments before its first network primitive"
      }
      $fixedChannelAssignment = '$Channel = "' + $fixedChannel + '"'
      if([regex]::Matches($text, [regex]::Escape($fixedChannelAssignment)).Count -ne 1){
        throw "$relative does not contain exactly one fixed channel assignment"
      }
      if($text.Contains('.PowerShellExe -NoProfile -NonInteractive')){
        throw "$relative still starts a second PowerShell installer"
      }
      foreach($forbiddenCore in @("install-core.ps1", "Read-VerifiedStableCore", "Get-StableCoreArtifact")){
        if($text.Contains($forbiddenCore)){ throw "$relative still references removed installer core: $forbiddenCore" }
      }
      $initializeIndex = $text.IndexOf("Initialize-TrustedWindowsInstallerEnvironment")
      $tempReadIndex = $text.IndexOf('$env:TEMP')
      if($initializeIndex -lt 0 -or $tempReadIndex -lt $initializeIndex){
        throw "$relative reads caller TEMP before trusted environment initialization"
      }
      # Console.Out deliberately bypasses PowerShell's success stream. Make the
      # disposable smoke copy emit the same marker through the capturable stream
      # so the report can bind the actually observed fixed channel.
      $consoleMarker = '[Console]::Out.WriteLine("BYTESTAFF_SMOKE_CORE_CHANNEL=$Channel")'
      if([regex]::Matches($text, [regex]::Escape($consoleMarker)).Count -ne 1){
        throw "$relative lost its fixed-channel smoke marker"
      }
      $text = $text.Replace(
        $consoleMarker,
        'Write-Output "BYTESTAFF_SMOKE_CORE_CHANNEL=$Channel"'
      )
    } elseif(-not $text.Contains('.PowerShellExe -NoProfile -NonInteractive')){
      throw "$relative lost its verified uninstaller helper invocation"
    }
    $originCount = [regex]::Matches($text, [regex]::Escape($centralOrigin)).Count
    if($originCount -ne 3){ throw "$relative does not contain exactly three fixed central-origin literals" }
    $text = $text.Replace($centralOrigin, $smokeOrigin)
    if($text.Contains($centralOrigin)){ throw "$relative temporary copy retained the production origin" }
    if($name.StartsWith("uninstall")){
      $productionMode = '-RedBeaconUninstallerExecutionMode "production"'
      $smokeMode = '-RedBeaconUninstallerExecutionMode "smoke"'
    } else {
      $productionMode = '$RedBeaconInstallerExecutionMode = "production"'
      $smokeMode = '$RedBeaconInstallerExecutionMode = "smoke"'
    }
    $modeCount = [regex]::Matches($text, [regex]::Escape($productionMode)).Count
    if($modeCount -ne 1){ throw "$relative does not contain exactly one fixed production execution mode" }
    if($name.StartsWith("uninstall")){
      $productionDestination = Join-Path $smokeWrapperDir ("production-" + $name)
      [System.IO.File]::WriteAllText($productionDestination, $text, [System.Text.UTF8Encoding]::new($false))
      $productionTestWrappers[$name] = $productionDestination
    }
    $text = $text.Replace($productionMode, $smokeMode)
    [System.IO.File]::WriteAllText($destination, $text, [System.Text.UTF8Encoding]::new($false))
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($destination, [ref]$tokens, [ref]$errors) | Out-Null
    if($errors -and $errors.Count -gt 0){ throw "Temporary smoke wrapper has parser errors: $name" }
    $smokeWrappers[$name] = $destination
  }
}

function Assert-PublicWrapperSourcesUnchanged() {
  foreach($relative in $publicWrappers){
    $current = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ProjectRoot $relative)).Hash
    if($current -cne $publicWrapperHashes[$relative]){
      throw "Smoke mutated production wrapper source: $relative"
    }
  }
}

function Assert-PublicWrapperRejectsArguments([string]$ScriptName) {
  $source = Join-Path $ProjectRoot "install\$ScriptName"
  $legacyManifestParameter = if($ScriptName -like "*-test.ps1"){
    "-RedBeaconTestManifestUrl"
  } else {
    "-RedBeaconStableManifestUrl"
  }
  $argumentSets = @(
    [pscustomobject]@{ Values = @( "unexpected" ) },
    [pscustomobject]@{ Values = @( $legacyManifestParameter, "$smokeOrigin/forged.json" ) },
    [pscustomobject]@{ Values = @( "-RedBeaconInstallerExecutionMode", "smoke" ) }
  )
  foreach($argumentSet in $argumentSets){
    $arguments = @($argumentSet.Values)
    $rejected = $false
    try { & $source @arguments }
    catch {
      $rejected = $_.Exception.Message -like "*accepts no arguments*"
      $probe = [pscustomobject]@{ ExitCode = 0; Thrown = $true; Output = $_.Exception.Message }
    }
    if(-not $rejected){ throw "$ScriptName accepted caller-controlled arguments: $($arguments -join ' ')" }
    Add-RejectionEvidence $ScriptName "extra-arguments" $probe "accepts no arguments"
  }
}

function New-ExecutionHijacks() {
  $script:HostileBin = Join-Path $work "hostile-bin"
  $script:ExecutionHijackMarker = Join-Path $work "execution-hijack-ran.txt"
  New-Item -ItemType Directory -Force -Path $script:HostileBin | Out-Null
  $source = Join-Path $script:HostileBin "HijackProbe.cs"
  $template = Join-Path $script:HostileBin "HijackProbe.exe"
  $text = @"
using System;
using System.IO;
public static class HijackProbe {
  public static int Main() {
    var marker = Environment.GetEnvironmentVariable("REDBEACON_HIJACK_MARKER");
    if (!String.IsNullOrEmpty(marker)) File.AppendAllText(marker, "path-hijack\n");
    return 97;
  }
}
"@
  [System.IO.File]::WriteAllText($source, $text, [System.Text.UTF8Encoding]::new($false))
  $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
  & $csc /nologo /target:exe "/out:$template" $source
  if($LASTEXITCODE -ne 0){ throw "Execution hijack probe compilation failed" }
  $expected = @($source, $template)
  foreach($name in @("powershell.exe", "pwsh.exe", "tar.exe", "curl.exe", "python.exe", "uv.exe")){
    $path = Join-Path $script:HostileBin $name
    Copy-Item -LiteralPath $template -Destination $path -Force
    $expected += $path
  }
  $sentinel = Join-Path $script:HostileBin "sentinel.txt"
  [System.IO.File]::WriteAllText($sentinel, "hostile-path", [System.Text.UTF8Encoding]::new($false))
  $expected += $sentinel
  $script:ForeignDirectoryExpected[$script:HostileBin] = @($expected)
}

function New-FakeChannel([string]$Channel, [string]$FixtureVersion = "9.9.9", [string]$Failure = "") {
  if($Channel -eq "test"){
    $appName = "RedBeacon_test"
    $cliName = "redbeacon-test-cli"
    $skillFile = "redbeacon-test.md"
    $skillCommand = "redbeacon-test"
    $runtimeFolder = ".redbeacon_test"
    $typeSuffix = "Test"
  } else {
    $appName = "RedBeacon"
    $cliName = "redbeacon-cli"
    $skillFile = "redbeacon.md"
    $skillCommand = "redbeacon"
    $runtimeFolder = ".redbeacon"
    $typeSuffix = "Stable"
  }

  $pkgRoot = Join-Path $build "pkg-$Channel"
  $appDir = Join-Path $pkgRoot $appName
  $assetDir = Join-Path $appDir "_internal\assets"
  New-Item -ItemType Directory -Force -Path $assetDir | Out-Null
  $cliPath = Join-Path $appDir "$cliName.exe"
  $cliSource = @"
using System;
using System.IO;
namespace RedBeaconInstallerSmoke$typeSuffix {
  public static class Cli {
    public static int Main(string[] args) {
      bool placed = System.Reflection.Assembly.GetExecutingAssembly().Location.IndexOf("\\Programs\\", StringComparison.OrdinalIgnoreCase) >= 0;
      if (args.Length > 0 && args[0] == "--version") { Console.WriteLine("redbeacon $FixtureVersion"); return 0; }
      if (args.Length > 0 && args[0] == "setup") {
        if ("$Failure" == "stage" || ("$Failure" == "placed" && placed)) { Console.Error.WriteLine("injected setup failure: $Failure"); return 51; }
        var home = Environment.GetEnvironmentVariable("USERPROFILE");
        var root = Path.Combine(home, "$runtimeFolder");
        if (Environment.GetEnvironmentVariable("REDBEACON_DATA_DIR") != Path.Combine(root, "data")) return 34;
        if (Environment.GetEnvironmentVariable("PLAYWRIGHT_BROWSERS_PATH") != Path.Combine(root, "browser", "ms-playwright")) return 35;
        if (Environment.GetEnvironmentVariable("CLOAKBROWSER_CACHE_DIR") != Path.Combine(root, "browser", "cloakbrowser")) return 36;
        if (args.Length < 3 || args[1] != "--manifest-file" || !File.Exists(args[2])) return 37;
        Console.WriteLine("{\"ok\":true}"); return 0;
      }
      if (Environment.GetEnvironmentVariable("REDBEACON_DESKTOP_SMOKE") == "1") {
        if ("$Failure" == "post_skills" && placed) { Console.Error.WriteLine("injected post-skills failure"); return 52; }
        Console.WriteLine("RedBeacon desktop smoke ok");
      }
      return 0;
    }
  }
}
"@
  $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
  if(-not (Test-Path $csc)){ throw "Windows C# compiler not found: $csc" }
  $cliCs = Join-Path $pkgRoot "FakeCli-$Channel.cs"
  [System.IO.File]::WriteAllText($cliCs, $cliSource, [System.Text.UTF8Encoding]::new($false))
  & $csc /nologo /target:exe "/out:$cliPath" $cliCs
  if($LASTEXITCODE -ne 0){ throw "Fake CLI compilation failed" }
  Copy-Item -Force $cliPath (Join-Path $appDir "$appName.exe")

  $rendererPath = Join-Path $appDir "RedBeaconRenderer.exe"
  $rendererSource = @"
using System;
using System.IO;
namespace RedBeaconInstallerSmokeRenderer$typeSuffix {
  public static class Renderer {
    public static int Main(string[] args) {
      string output = null;
      for (var i = 0; i + 1 < args.Length; i++) if (args[i] == "--output-dir") output = args[i + 1];
      if (String.IsNullOrEmpty(output)) return 41;
      Directory.CreateDirectory(output);
      File.WriteAllBytes(Path.Combine(output, "cover.png"), new byte[] { 1, 2, 3 });
      File.WriteAllBytes(Path.Combine(output, "card_1.png"), new byte[] { 1, 2, 3 });
      return 0;
    }
  }
}
"@
  $rendererCs = Join-Path $pkgRoot "FakeRenderer-$Channel.cs"
  [System.IO.File]::WriteAllText($rendererCs, $rendererSource, [System.Text.UTF8Encoding]::new($false))
  & $csc /nologo /target:exe "/out:$rendererPath" $rendererCs
  if($LASTEXITCODE -ne 0){ throw "Fake renderer compilation failed" }
  [System.IO.File]::WriteAllBytes((Join-Path $assetDir "RedBeacon.ico"), [byte[]](0))

  if($Failure -eq "bundle_entry"){ Remove-Item -LiteralPath $rendererPath -Force }

  $channelRoot = Join-Path $fake "projects\redbeacon\$Channel"
  $releaseRoot = Join-Path $channelRoot "releases\$FixtureVersion"
  $zipDir = Join-Path $releaseRoot "packages"
  New-Item -ItemType Directory -Force -Path $zipDir | Out-Null
  $zip = Join-Path $zipDir "$appName-win-x64.zip"
  Compress-Archive -Path $appDir -DestinationPath $zip -Force

  $skillRoot = Join-Path $build "skill-$Channel"
  $commands = Join-Path $skillRoot ".claude\commands"
  New-Item -ItemType Directory -Force -Path $commands | Out-Null
  $skillText = "---`ndescription: smoke $Channel $FixtureVersion`n---`n# smoke`n$skillCommand checkin"
  [System.IO.File]::WriteAllText((Join-Path $commands $skillFile), $skillText, [System.Text.UTF8Encoding]::new($false))
  $portableRoot = Join-Path $skillRoot "agent-skills\$([System.IO.Path]::GetFileNameWithoutExtension($skillFile))"
  New-Item -ItemType Directory -Force -Path $portableRoot | Out-Null
  $portableText = "---`nname: $([System.IO.Path]::GetFileNameWithoutExtension($skillFile))`ndescription: `"smoke $Channel $FixtureVersion`"`n---`n`n# smoke`n$skillCommand checkin"
  [System.IO.File]::WriteAllText((Join-Path $portableRoot "SKILL.md"), $portableText, [System.Text.UTF8Encoding]::new($false))
  $skillMetadata = @{
    schema = 2
    channel = $Channel
    version = "$FixtureVersion"
    files = @($skillFile)
    assistants = @("claude-code", "codex", "openclaw", "hermes", "workbuddy")
    portable_skills = @("agent-skills/$([System.IO.Path]::GetFileNameWithoutExtension($skillFile))/SKILL.md")
  } | ConvertTo-Json -Compress
  [System.IO.File]::WriteAllText(
    (Join-Path $skillRoot "redbeacon-skill-manifest.json"),
    $skillMetadata,
    [System.Text.UTF8Encoding]::new($false)
  )
  $skillDir = Join-Path $releaseRoot "skill"
  New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
  $skillBundle = Join-Path $skillDir "redbeacon-skill.tar.gz"
  & (Join-Path ([Environment]::SystemDirectory) "tar.exe") -czf $skillBundle -C $skillRoot .
  if($LASTEXITCODE -ne 0){ throw "Fake skill archive creation failed" }

  $installerDir = Join-Path $releaseRoot "installers"
  New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
  Copy-Item -Force (Join-Path $ProjectRoot "install\uninstall-core.ps1") (Join-Path $installerDir "uninstall-core.ps1")

  $artifacts = @()
  foreach($relative in @(
    "packages/$appName-win-x64.zip",
    "skill/redbeacon-skill.tar.gz",
    "installers/uninstall-core.ps1"
  )){
    $localPath = Join-Path $releaseRoot ($relative.Replace('/', '\'))
    $url = "http://127.0.0.1:8765/projects/redbeacon/$Channel/releases/$FixtureVersion/$relative"
    $artifacts += @{
      path = $relative
      size = (Get-Item -LiteralPath $localPath).Length
      sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $localPath).Hash.ToLowerInvariant()
      url = $url
      download_urls = @($url)
    }
  }
  $manifest = @{
    schema = 1
    project = "redbeacon"
    channel = $Channel
    version = "$FixtureVersion"
    created_at = "2026-07-17T00:00:00Z"
    commit = "installer-smoke"
    artifacts = $artifacts
  } | ConvertTo-Json -Depth 8
  New-Item -ItemType Directory -Force -Path $channelRoot | Out-Null
  [System.IO.File]::WriteAllText((Join-Path $channelRoot "latest.json"), $manifest, [System.Text.UTF8Encoding]::new($false))
}

function Channel-Spec([string]$Channel) {
  if($Channel -eq "test"){
    return @{
      AppName = "RedBeacon_test"; CmdName = "redbeacon-test"; SkillFile = "redbeacon-test.md"
      SkillBase = "redbeacon-test"; SkillDir = Join-Path $HOME ".claude\commands-redbeacon-test"
      RuntimeFolder = ".redbeacon_test"; TokenFolder = ".bytestaff_test"
    }
  }
  return @{
    AppName = "RedBeacon"; CmdName = "redbeacon"; SkillFile = "redbeacon.md"
    SkillBase = "redbeacon"; SkillDir = Join-Path $HOME ".claude\commands"
    RuntimeFolder = ".redbeacon"; TokenFolder = ".bytestaff"
  }
}

function Channel-ShortcutPaths([string]$Channel) {
  $spec = Channel-Spec $Channel
  return @(
    (Join-Path $fakeHome "Desktop\$($spec.AppName).lnk"),
    (Join-Path $fakeAppData "Microsoft\Windows\Start Menu\Programs\$($spec.AppName).lnk")
  )
}

function Business-Database([string]$Channel) {
  $folder = if($Channel -eq "test"){ ".redbeacon_test" } else { ".redbeacon" }
  return Join-Path $HOME "$folder\data\redbeacon.db"
}

function Seed-BusinessDatabase([string]$Channel) {
  $db = Business-Database $Channel
  New-Item -ItemType Directory -Force -Path (Split-Path $db) | Out-Null
  [System.IO.File]::WriteAllText($db, "account-data-$Channel", [System.Text.UTF8Encoding]::new($false))
}

function Assert-BusinessDatabase([string]$Channel) {
  $db = Business-Database $Channel
  if(-not (Test-Path $db)){ throw "$Channel account database disappeared" }
  if(([System.IO.File]::ReadAllText($db)) -ne "account-data-$Channel"){
    throw "$Channel account database changed during install/update"
  }
}

function Assert-DatabaseSnapshot([string]$Channel) {
  $folder = if($Channel -eq "test"){ ".redbeacon_test" } else { ".redbeacon" }
  $root = Join-Path $HOME "$folder\backups\pre-update"
  $snapshots = @(Get-ChildItem -Path $root -Filter "redbeacon.db" -File -Recurse -ErrorAction SilentlyContinue)
  if($snapshots.Count -eq 0){ throw "$Channel update did not save a database snapshot" }
  if(([System.IO.File]::ReadAllText($snapshots[-1].FullName)) -ne "account-data-$Channel"){
    throw "$Channel pre-update database snapshot has the wrong content"
  }
}

function Assert-Installed([string]$Channel) {
  $spec = Channel-Spec $Channel
  $dest = Join-Path $fakeLocalAppData "Programs\$($spec.AppName)"
  $shim = Join-Path $HOME ".local\bin\$($spec.CmdName).cmd"
  $claudeSkill = Join-Path $spec.SkillDir $spec.SkillFile
  $assistantSkills = @(
    (Join-Path $HOME ".codex\skills\$($spec.SkillBase)\SKILL.md"),
    (Join-Path $HOME ".openclaw\skills\$($spec.SkillBase)\SKILL.md"),
    (Join-Path $HOME ".hermes\skills\$($spec.SkillBase)\SKILL.md"),
    (Join-Path $HOME ".workbuddy\skills\$($spec.SkillBase)\SKILL.md")
  )
  foreach($path in @($dest, $shim, $claudeSkill) + $assistantSkills + (Channel-ShortcutPaths $Channel)){
    if(-not (Test-Path $path)){ throw "$Channel install did not create $path" }
  }
  foreach($skill in $assistantSkills){
    $text = Get-Content -Raw -Encoding UTF8 -Path $skill
    if($text -notmatch "(?m)^name:\s*$([regex]::Escape($spec.SkillBase))\s*$"){
      throw "$Channel assistant skill frontmatter has the wrong name: $skill"
    }
  }
}

function Assert-Uninstalled([string]$Channel) {
  $spec = Channel-Spec $Channel
  $paths = @(
    (Join-Path $fakeLocalAppData "Programs\$($spec.AppName)"),
    (Join-Path $HOME ".local\bin\$($spec.CmdName).cmd"),
    (Join-Path $spec.SkillDir $spec.SkillFile),
    (Join-Path $HOME ".codex\skills\$($spec.SkillBase)\SKILL.md"),
    (Join-Path $HOME ".openclaw\skills\$($spec.SkillBase)\SKILL.md"),
    (Join-Path $HOME ".hermes\skills\$($spec.SkillBase)\SKILL.md"),
    (Join-Path $HOME ".workbuddy\skills\$($spec.SkillBase)\SKILL.md")
  )
  $paths += Channel-ShortcutPaths $Channel
  foreach($path in $paths){ if(Test-Path $path){ throw "$Channel uninstall did not remove $path" } }
}

function Set-HostileWrapperEnvironment([string]$TargetChannel, [string]$Alias) {
  $opposite = if($TargetChannel -eq "test"){ "stable" } else { "test" }
  $foreignRoot = Join-Path $work "foreign-environment"
  $pathVariables = @(
    "REDBEACON_UPDATE_WORKDIR", "REDBEACON_DATA_DIR", "REDBEACON_LOG_DIR",
    "REDBEACON_SKILL_DIR", "REDBEACON_CODEX_SKILL_DIR", "REDBEACON_OPENCLAW_SKILL_DIR",
    "REDBEACON_HERMES_SKILL_DIR", "REDBEACON_WORKBUDDY_SKILL_DIR",
    "REDBEACON_PLAYWRIGHT_DIR", "REDBEACON_CLOAKBROWSER_DIR",
    "PLAYWRIGHT_BROWSERS_PATH", "CLOAKBROWSER_CACHE_DIR", "BYTESTAFF_HOME",
    "REDBEACON_INSTALL_MANIFEST_FILE"
  )
  $executionPathVariables = @(
    "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "TMPDIR", "PSMODULEPATH"
  )
  $values = @{
    "REDBEACON_CHANNEL" = $Alias
    "REDBEACON_BUILD_CHANNEL" = $Alias
    "REDBEACON_UPDATE_URL" = "$smokeOrigin/projects/redbeacon/$opposite/latest.json"
    "REDBEACON_OSS" = "$smokeOrigin/projects/redbeacon/$opposite"
    "REDBEACON_PLAYWRIGHT_DOWNLOAD_URL" = "$smokeOrigin/forged/playwright.zip"
    "REDBEACON_CLOAKBROWSER_DOWNLOAD_URL" = "$smokeOrigin/forged/cloakbrowser.zip"
    "REDBEACON_INSTALLER_TEST_MODE" = "1"
    "CLOAKBROWSER_VERSION" = "forged-version"
    "CLOAKBROWSER_SKIP_CHECKSUM" = "1"
    "REDBEACON_OUT" = "forged-output-mode"
    "PATH" = "$($script:HostileBin);C:\caller-path-must-not-run"
    "REDBEACON_HIJACK_MARKER" = $script:ExecutionHijackMarker
  }
  foreach($name in $pathVariables){
    $path = Join-Path $foreignRoot $name.ToLowerInvariant()
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    $sentinel = Join-Path $path "sentinel.txt"
    $content = "foreign-$name"
    [System.IO.File]::WriteAllText($sentinel, $content, [System.Text.UTF8Encoding]::new($false))
    $script:ForeignSentinels[$sentinel] = $content
    $script:ForeignDirectoryExpected[$path] = @($sentinel)
    $values[$name] = $path
  }
  foreach($name in $executionPathVariables){
    $path = Join-Path $foreignRoot ("caller-" + $name.ToLowerInvariant())
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    $sentinel = Join-Path $path "sentinel.txt"
    $content = "caller-$name"
    [System.IO.File]::WriteAllText($sentinel, $content, [System.Text.UTF8Encoding]::new($false))
    $script:ForeignSentinels[$sentinel] = $content
    $expected = @($sentinel)
    if($name -eq "LOCALAPPDATA"){
      # Windows PowerShell 5.1 creates this empty host-owned cache hierarchy
      # whenever LOCALAPPDATA changes, before the wrapper can sanitize it.
      $microsoft = Join-Path $path "Microsoft"
      $windows = Join-Path $microsoft "Windows"
      $caches = Join-Path $windows "Caches"
      New-Item -ItemType Directory -Force -Path $caches | Out-Null
      $expected += @($microsoft, $windows, $caches)
    }
    $script:ForeignDirectoryExpected[$path] = @($expected)
    $values[$name] = $path
  }
  $binaryRoot = Join-Path $foreignRoot "cloakbrowser_binary"
  New-Item -ItemType Directory -Force -Path $binaryRoot | Out-Null
  $binaryPath = Join-Path $binaryRoot "forged-browser.exe"
  [System.IO.File]::WriteAllText($binaryPath, "foreign-binary", [System.Text.UTF8Encoding]::new($false))
  $script:ForeignSentinels[$binaryPath] = "foreign-binary"
  $script:ForeignDirectoryExpected[$binaryRoot] = @($binaryPath)
  $values["CLOAKBROWSER_BINARY_PATH"] = $binaryPath
  foreach($entry in $values.GetEnumerator()){
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
  }
  $snapshot = @{}
  foreach($name in $hostileEnvironmentNames){
    $snapshot[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
  }
  if($null -eq $script:ForeignBefore){
    $script:ForeignBefore = Get-TreeObservation @($script:ForeignDirectoryExpected.Keys)
  }
  return $snapshot
}

function Assert-EnvironmentSnapshot($Snapshot, [string]$Label) {
  foreach($name in $hostileEnvironmentNames){
    $actual = [Environment]::GetEnvironmentVariable($name, "Process")
    if($actual -cne $Snapshot[$name]){ throw "$Label changed hostile caller environment variable $name" }
  }
  $actualEnvironment = @{}
  foreach($name in $hostileEnvironmentNames){ $actualEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process") }
  $script:CallerBefore += Get-EnvironmentDigest $Snapshot
  $script:CallerAfter += Get-EnvironmentDigest $actualEnvironment
}

function Assert-ForeignSentinels() {
  foreach($entry in $script:ForeignSentinels.GetEnumerator()){
    if(-not (Test-Path -LiteralPath $entry.Key -PathType Leaf)){ throw "Foreign path sentinel was deleted: $($entry.Key)" }
    if([System.IO.File]::ReadAllText($entry.Key) -cne $entry.Value){ throw "Foreign path sentinel was changed: $($entry.Key)" }
  }
  foreach($entry in $script:ForeignDirectoryExpected.GetEnumerator()){
    $actual = @(Get-ChildItem -LiteralPath $entry.Key -Force -Recurse -ErrorAction SilentlyContinue |
      ForEach-Object { $_.FullName } | Sort-Object)
    $expected = @($entry.Value | Sort-Object)
    if(($actual -join "`n") -cne ($expected -join "`n")){
      throw "Caller-owned directory content changed: $($entry.Key); expected=$($expected -join '|'); actual=$($actual -join '|')"
    }
  }
  if(Test-Path -LiteralPath $script:ExecutionHijackMarker){
    throw "Caller-controlled executable or PowerShell function was invoked"
  }
}

function Channel-Root([string]$Channel) {
  $spec = Channel-Spec $Channel
  return Join-Path $HOME $spec.RuntimeFolder
}

function Seed-ChannelState([string]$Channel) {
  $spec = Channel-Spec $Channel
  $runtimeRoot = Channel-Root $Channel
  $tokenRoot = Join-Path $HOME $spec.TokenFolder
  $files = @{
    (Join-Path $runtimeRoot "owner-sentinel.txt") = "runtime-$Channel"
    (Join-Path $runtimeRoot "browser\owner-sentinel.txt") = "browser-$Channel"
    (Join-Path $tokenRoot "owner-sentinel.txt") = "token-$Channel"
  }
  foreach($entry in $files.GetEnumerator()){
    New-Item -ItemType Directory -Force -Path (Split-Path $entry.Key) | Out-Null
    [System.IO.File]::WriteAllText($entry.Key, $entry.Value, [System.Text.UTF8Encoding]::new($false))
  }
}

function Assert-ChannelPersistentState([string]$Channel, [bool]$ExpectBrowser = $true) {
  $spec = Channel-Spec $Channel
  $runtimeRoot = Channel-Root $Channel
  $checks = @{
    (Join-Path $runtimeRoot "owner-sentinel.txt") = "runtime-$Channel"
    (Join-Path $HOME "$($spec.TokenFolder)\owner-sentinel.txt") = "token-$Channel"
  }
  if($ExpectBrowser){ $checks[(Join-Path $runtimeRoot "browser\owner-sentinel.txt")] = "browser-$Channel" }
  foreach($entry in $checks.GetEnumerator()){
    if(-not (Test-Path -LiteralPath $entry.Key -PathType Leaf)){ throw "$Channel state sentinel disappeared: $($entry.Key)" }
    if([System.IO.File]::ReadAllText($entry.Key) -cne $entry.Value){ throw "$Channel state sentinel changed: $($entry.Key)" }
  }
}

function Invoke-PublicWrapper([string]$ScriptName) {
  & $smokeWrappers[$ScriptName]
}

function Invoke-WrapperWithCommandShadows([string]$WrapperPath) {
  $driver = Join-Path $work ("shadow-driver-" + [guid]::NewGuid().ToString("N") + ".ps1")
  $wrapperLiteral = ConvertTo-PowerShellSingleQuotedLiteral $WrapperPath
  $markerLiteral = ConvertTo-PowerShellSingleQuotedLiteral $script:ExecutionHijackMarker
  $driverEnvironment = @{}
  $environmentLines = @()
  foreach($name in $hostileEnvironmentNames){
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    $driverEnvironment[$name] = $value
    $nameLiteral = ConvertTo-PowerShellSingleQuotedLiteral $name
    $valueLiteral = ConvertTo-PowerShellSingleQuotedLiteral ([string]$value)
    $environmentLines += "[Environment]::SetEnvironmentVariable($nameLiteral, $valueLiteral, 'Process')"
  }
  $environmentSetup = $environmentLines -join "`n"
  $driverText = @"
`$ErrorActionPreference = "Stop"
$environmentSetup
function Write-HijackMarker([string]`$Name){
  [System.IO.File]::AppendAllText($markerLiteral, `$Name + "`n")
  throw "Caller-controlled PowerShell command shadow ran: `$Name"
}
function global:Invoke-WebRequest { Write-HijackMarker "Invoke-WebRequest" }
function global:Get-FileHash { Write-HijackMarker "Get-FileHash" }
function global:ConvertFrom-Json { Write-HijackMarker "ConvertFrom-Json" }
try {
  & $wrapperLiteral
  if(`$LASTEXITCODE -ne 0){ exit `$LASTEXITCODE }
}
catch {
  [Console]::Error.WriteLine(`$_.Exception.Message)
  exit 1
}
"@
  [System.IO.File]::WriteAllText($driver, $driverText, [System.Text.UTF8Encoding]::new($false))
  $powerShellExe = [System.IO.Path]::Combine(
    [Environment]::SystemDirectory, "WindowsPowerShell", "v1.0", "powershell.exe"
  )
  $shadowHostRoot = Join-Path $work "shadow-host"
  $shadowHostHome = Join-Path $shadowHostRoot "home"
  $shadowHostLocal = Join-Path $shadowHostRoot "localappdata"
  $shadowHostRoaming = Join-Path $shadowHostRoot "appdata"
  $shadowHostTemp = Join-Path $shadowHostRoot "temp"
  foreach($path in @($shadowHostHome, $shadowHostLocal, $shadowHostRoaming, $shadowHostTemp)){
    [void][System.IO.Directory]::CreateDirectory($path)
  }
  $launchValues = @{
    "HOME" = $shadowHostHome
    "USERPROFILE" = $shadowHostHome
    "LOCALAPPDATA" = $shadowHostLocal
    "APPDATA" = $shadowHostRoaming
    "TEMP" = $shadowHostTemp
    "TMP" = $shadowHostTemp
    "TMPDIR" = $shadowHostTemp
    "PATH" = $originalProcessPath
    "PSMODULEPATH" = $originalHostileEnvironment["PSModulePath"]
  }
  foreach($entry in $launchValues.GetEnumerator()){
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
  }
  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & $powerShellExe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $driver 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousPreference
    foreach($entry in $driverEnvironment.GetEnumerator()){
      [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }
    try { [System.IO.File]::Delete($driver) } catch {}
  }
  if($exitCode -ne 0){
    throw "Wrapper failed under caller PowerShell command shadows: $($output -join [Environment]::NewLine)"
  }
}

function Assert-WrappersResistCommandShadows() {
  foreach($case in @(
    @{ Script = "install.ps1"; Channel = "stable"; Alias = "test"; Installed = $true },
    @{ Script = "install-test.ps1"; Channel = "test"; Alias = "stable"; Installed = $true },
    @{ Script = "uninstall.ps1"; Channel = "stable"; Alias = "test"; Installed = $false },
    @{ Script = "uninstall-test.ps1"; Channel = "test"; Alias = "stable"; Installed = $false }
  )){
    $snapshot = Set-HostileWrapperEnvironment $case.Channel $case.Alias
    $env:REDBEACON_FORCE_INSTALL = "1"
    $env:REDBEACON_PURGE = "0"
    Invoke-WrapperWithCommandShadows $smokeWrappers[$case.Script]
    Assert-EnvironmentSnapshot $snapshot "$($case.Script) command-shadow probe"
    Assert-ForeignSentinels
    if($case.Installed){ Assert-Installed $case.Channel } else { Assert-Uninstalled $case.Channel }
  }
  Remove-Item Env:\REDBEACON_FORCE_INSTALL -ErrorAction SilentlyContinue
  Write-Host "Windows wrappers ignore caller PowerShell command shadows"
}

function Install-ThroughWrapper([string]$Channel, [string]$Alias, [bool]$Force = $true) {
  $scriptName = if($Channel -eq "test"){ "install-test.ps1" } else { "install.ps1" }
  $snapshot = Set-HostileWrapperEnvironment $Channel $Alias
  if($Force){ $env:REDBEACON_FORCE_INSTALL = "1" }
  else { Remove-Item Env:\REDBEACON_FORCE_INSTALL -ErrorAction SilentlyContinue }
  $global:LASTEXITCODE = 0
  Invoke-PublicWrapper $scriptName
  if($LASTEXITCODE -ne 0){ throw "$Channel installer returned exit code $LASTEXITCODE" }
  Assert-EnvironmentSnapshot $snapshot "$Channel installer"
  Remove-Item Env:\REDBEACON_FORCE_INSTALL -ErrorAction SilentlyContinue
  Assert-ForeignSentinels
  Assert-Installed $Channel
}

function Uninstall-ThroughWrapper([string]$Channel, [string]$Alias) {
  $scriptName = if($Channel -eq "test"){ "uninstall-test.ps1" } else { "uninstall.ps1" }
  $snapshot = Set-HostileWrapperEnvironment $Channel $Alias
  $env:REDBEACON_PURGE = "0"
  $global:LASTEXITCODE = 0
  Invoke-PublicWrapper $scriptName
  if($LASTEXITCODE -ne 0){ throw "$Channel uninstaller returned exit code $LASTEXITCODE" }
  Assert-EnvironmentSnapshot $snapshot "$Channel uninstaller"
  Assert-ForeignSentinels
  Assert-Uninstalled $Channel
}

function Get-ServerRequestPaths() {
  if(-not [System.IO.File]::Exists($serverRequestLog)){ return @() }
  $logStream = [System.IO.File]::Open(
    $serverRequestLog,
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read,
    [System.IO.FileShare]::ReadWrite
  )
  try {
    $logReader = [System.IO.StreamReader]::new($logStream, [System.Text.Encoding]::UTF8)
    try { $serverLog = $logReader.ReadToEnd() } finally { $logReader.Dispose() }
  }
  finally { $logStream.Dispose() }
  return @(
    [regex]::Matches($serverLog, '"GET ([^ ]+) HTTP/') |
      ForEach-Object { $_.Groups[1].Value }
  )
}

function Invoke-ObservedPublicWrapper([string]$ScriptName) {
  # Register the asynchronous EventArrived queue before execution. Start() and
  # WaitForNextEvent() create different WMI subscriptions; mixing them loses
  # short-lived children that finish before the synchronous subscription starts.
  $query = [System.Management.WqlEventQuery]::new(
    "SELECT * FROM Win32_ProcessStartTrace"
  )
  $watcher = [System.Management.ManagementEventWatcher]::new($query)
  $sourceIdentifier = "RedBeaconInstallerSmoke-" + [guid]::NewGuid().ToString("N")
  $secondaryPowerShell = @()
  $previousPreference = $ErrorActionPreference
  Register-ObjectEvent -InputObject $watcher -EventName EventArrived -SourceIdentifier $sourceIdentifier | Out-Null
  try {
    $watcher.Start()
    $ErrorActionPreference = "Continue"
    $global:LASTEXITCODE = 0
    try {
      $captured = @(& $smokeWrappers[$ScriptName] *>&1)
      $exitCode = $LASTEXITCODE
    }
    finally {
      $ErrorActionPreference = $previousPreference
      # Drain the same queue, including delayed delivery. A bounded quiet tail
      # never invents a child; the actual PID is retained as raw evidence.
      $deadline = [DateTime]::UtcNow.AddSeconds(15)
      while($true){
        $event = Wait-Event -SourceIdentifier $sourceIdentifier -Timeout 2
        if($null -eq $event){ break }
        try {
          $started = $event.SourceEventArgs.NewEvent
          $image = ([string]$started.ProcessName).ToLowerInvariant()
          if(
            [int]$started.ParentProcessID -eq $PID -and
            @("powershell.exe", "pwsh.exe") -contains $image
          ){
            $secondaryPowerShell += [pscustomobject]@{
              pid = [int]$started.ProcessID
              command = $image
            }
          }
        }
        finally { Remove-Event -EventIdentifier $event.EventIdentifier -ErrorAction Stop }
        if([DateTime]::UtcNow -gt $deadline){ throw "Process event queue did not drain within its observation deadline" }
      }
    }
  }
  finally {
    $ErrorActionPreference = $previousPreference
    try { $watcher.Stop() }
    finally {
      $watcher.Dispose()
      Unregister-Event -SourceIdentifier $sourceIdentifier -ErrorAction SilentlyContinue
      Remove-Event -SourceIdentifier $sourceIdentifier -ErrorAction SilentlyContinue
    }
  }
  return [pscustomobject]@{
    Captured = @($captured)
    ExitCode = $exitCode
    SecondaryPowerShell = @($secondaryPowerShell)
  }
}

function Invoke-ObservedEntrypoint([string]$ObservedChannel, [string]$Operation) {
  $suffix = if($ObservedChannel -eq "test"){ "-test" } else { "" }
  $scriptName = "$Operation$suffix.ps1"
  $opposite = if($ObservedChannel -eq "test"){ "stable" } else { "test" }
  $snapshot = Set-HostileWrapperEnvironment $ObservedChannel $opposite
  if($Operation -eq "install"){
    $env:REDBEACON_FORCE_INSTALL = "1"
    Remove-Item Env:\REDBEACON_PURGE -ErrorAction SilentlyContinue
  } else {
    $env:REDBEACON_PURGE = "0"
    Remove-Item Env:\REDBEACON_FORCE_INSTALL -ErrorAction SilentlyContinue
  }
  $requestCountBefore = @(Get-ServerRequestPaths).Count
  $execution = Invoke-ObservedPublicWrapper $scriptName
  $captured = @($execution.Captured)
  $exitCode = $execution.ExitCode
  foreach($item in $captured){ [Console]::Out.WriteLine([string]$item) }
  if($exitCode -ne 0){ throw "$scriptName final observation returned exit code $exitCode" }
  Assert-EnvironmentSnapshot $snapshot "$scriptName final observation"
  Assert-ForeignSentinels
  if($Operation -eq "install"){
    Assert-Installed $ObservedChannel
  } else {
    Assert-Uninstalled $ObservedChannel
  }
  $marker = "BYTESTAFF_SMOKE_CORE_CHANNEL=$ObservedChannel"
  $markerLines = @($captured | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ -ceq $marker })
  if($markerLines.Count -ne 1){ throw "$scriptName did not expose exactly one effective channel" }

  Start-Sleep -Milliseconds 200
  $allRequests = @(Get-ServerRequestPaths)
  $observedRequests = @()
  if($allRequests.Count -gt $requestCountBefore){
    $observedRequests = @(
      $allRequests[$requestCountBefore..($allRequests.Count - 1)]
    )
  }
  $manifestRequest = "/projects/redbeacon/$ObservedChannel/latest.json"
  if($observedRequests -cnotcontains $manifestRequest){
    throw "$scriptName did not request its fixed manifest path"
  }
  $internalHelper = $null
  if($Operation -eq "install"){
    $forbiddenCoreRequests = @($observedRequests | Where-Object { $_ -like "*install-core*" })
    if($forbiddenCoreRequests.Count -ne 0){
      throw "$scriptName requested the removed installer core: $($forbiddenCoreRequests -join ', ')"
    }
    if($execution.SecondaryPowerShell.Count -ne 0){
      throw "$scriptName started a second PowerShell installer process"
    }
    $executionModel = "single-stage-public-entrypoint"
  } else {
    $helperName = "uninstall-core.ps1"
    $helperRequest = "/projects/redbeacon/$ObservedChannel/releases/9.9.9/installers/$helperName"
    if($observedRequests -cnotcontains $helperRequest){
      throw "$scriptName did not request its fixed uninstaller helper"
    }
    if($execution.SecondaryPowerShell.Count -ne 1){
      throw "$scriptName did not start exactly one verified helper PowerShell; observed $($execution.SecondaryPowerShell.Count)"
    }
    $executionModel = "public-entrypoint-with-internal-helper"
    $internalHelper = [pscustomobject][ordered]@{
      path = "install/$helperName"
      sha256 = ([string]$coreHashes["install\$helperName"]).ToLowerInvariant()
      request_path = $helperRequest
    }
  }
  $entrypointKey = "install\$scriptName"
  return [pscustomobject][ordered]@{
    channel = $ObservedChannel
    operation = $Operation
    entrypoint_path = "install/$scriptName"
    entrypoint_sha256 = ([string]$publicWrapperHashes[$entrypointKey]).ToLowerInvariant()
    canonical_manifest_url = "$centralOrigin/projects/redbeacon/$ObservedChannel/latest.json"
    manifest_request_path = $manifestRequest
    observed_request_paths = @($observedRequests)
    effective_channel = $ObservedChannel
    effective_channel_marker = $marker
    execution_model = $executionModel
    secondary_shell_observed_count = $execution.SecondaryPowerShell.Count
    secondary_shells = @($execution.SecondaryPowerShell)
    internal_helper = $internalHelper
  }
}

function Get-TextDigest([string]$Text) {
  $hasher = [System.Security.Cryptography.SHA256]::Create()
  try {
    return ([BitConverter]::ToString($hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Text)))).Replace("-", "").ToLowerInvariant()
  } finally { $hasher.Dispose() }
}

function Get-EnvironmentDigest($Values) {
  $rows = @($Values.Keys | Sort-Object | ForEach-Object {
    [ordered]@{ name = $_; value = $Values[$_] } | ConvertTo-Json -Compress
  })
  return Get-TextDigest ($rows -join "`n")
}

function Get-TreeObservation([string[]]$Paths) {
  $rows = @()
  foreach($path in @($Paths | Sort-Object -Unique)){
    if(-not (Test-Path -LiteralPath $path)){ throw "Snapshot path is missing: $path" }
    $items = @(Get-Item -LiteralPath $path -Force)
    if($items[0].PSIsContainer){ $items += @(Get-ChildItem -LiteralPath $path -Force -Recurse) }
    foreach($item in @($items | Sort-Object FullName)){
      $digest = if($item.PSIsContainer){ "directory" } else { (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
      $rows += ($item.FullName.Substring($work.Length) + "=" + $digest)
    }
  }
  return [pscustomobject]@{ Count = $rows.Count; Sha256 = Get-TextDigest ($rows -join "`n") }
}

function Channel-ObservedPaths([string]$ObservedChannel) {
  $spec = Channel-Spec $ObservedChannel
  return @(
    (Join-Path $fakeHome $spec.RuntimeFolder), (Join-Path $fakeHome $spec.TokenFolder),
    (Join-Path $fakeLocalAppData "Programs\$($spec.AppName)"),
    (Join-Path $spec.SkillDir $spec.SkillFile),
    (Join-Path $fakeHome ".local\bin\$($spec.CmdName).cmd")
  ) + @(foreach($hostName in @("codex", "openclaw", "hermes", "workbuddy")){
    Join-Path $fakeHome ".$hostName\skills\$($spec.SkillBase)"
  }) + @(Channel-ShortcutPaths $ObservedChannel)
}

function Add-RejectionEvidence([string]$ScriptName, [string]$ProbeName, $Probe, [string]$Diagnostic) {
  $script:RejectionEvidence += [pscustomobject][ordered]@{
    wrapper = $ScriptName; probe = $ProbeName
    observed_exit_code = [int]$Probe.ExitCode; observed_exception = [bool]$Probe.Thrown
    diagnostic = $Diagnostic; raw_output = $Probe.Output
    raw_output_sha256 = Get-TextDigest $Probe.Output
  }
}

function Get-InstalledVersion([string]$ObservedChannel) {
  $spec = Channel-Spec $ObservedChannel
  $cliName = if($ObservedChannel -eq "test"){ "redbeacon-test-cli.exe" } else { "redbeacon-cli.exe" }
  $cli = Join-Path $fakeLocalAppData "Programs\$($spec.AppName)\$cliName"
  $output = & $cli --version
  if($LASTEXITCODE -ne 0){ throw "Cannot read installed $ObservedChannel version" }
  return (($output | Out-String).Trim() -split '\s+')[-1]
}

function Invoke-ObservedAlias([string]$ObservedChannel, [string]$Alias) {
  $snapshot = Set-HostileWrapperEnvironment $ObservedChannel $Alias
  $env:REDBEACON_FORCE_INSTALL = "1"
  $name = if($ObservedChannel -eq "test"){ "install-test.ps1" } else { "install.ps1" }
  $global:LASTEXITCODE = 0
  $output = @(Invoke-PublicWrapper $name)
  if($LASTEXITCODE -ne 0){ throw "$name alias probe failed" }
  Assert-EnvironmentSnapshot $snapshot "$name/$Alias"
  Assert-Installed $ObservedChannel
  $marker = "BYTESTAFF_SMOKE_CORE_CHANNEL=$ObservedChannel"
  if(@($output | Where-Object { ([string]$_).Trim() -ceq $marker }).Count -ne 1){
    throw "$name/$Alias has no unique effective-channel marker"
  }
  return [ordered]@{
    target_channel = $ObservedChannel; ambient_alias = $Alias
    effective_core_channel = $ObservedChannel; effective_core_marker = $marker
    observed_installed_version = Get-InstalledVersion $ObservedChannel
  }
}

function Assert-TransactionRollbackEvidence() {
  $db = Business-Database "stable"
  $databaseBefore = (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash.ToLowerInvariant()
  $baselineVersion = Get-InstalledVersion "stable"
  $protectedPaths = @(Channel-ObservedPaths "stable" | Where-Object { $_ -notlike "*\.redbeacon" })
  $before = Get-TreeObservation $protectedPaths
  foreach($case in @(
    @{ Probe = "invalid-bundle-entry-rollback"; Version = "9.9.10"; Failure = "bundle_entry"; Diagnostic = "card renderer" },
    @{ Probe = "pre-replacement-rollback"; Version = "9.9.11"; Failure = "stage"; Diagnostic = "injected setup failure" },
    @{ Probe = "post-placement-rollback"; Version = "9.9.12"; Failure = "placed"; Diagnostic = "injected setup failure" },
    @{ Probe = "post-skills-rollback"; Version = "9.9.13"; Failure = "post_skills"; Diagnostic = "post-skills failure" }
  )){
    New-FakeChannel "stable" $case.Version $case.Failure
    $snapshot = Set-HostileWrapperEnvironment "stable" "test"
    $env:REDBEACON_FORCE_INSTALL = "1"
    $probe = Invoke-RejectionProbe "install.ps1"
    if(-not $probe.Failed -or $probe.Output -notlike "*$($case.Diagnostic)*"){
      throw "$($case.Probe) did not reach its expected failure: $($probe.Output)"
    }
    Assert-EnvironmentSnapshot $snapshot $case.Probe
    Assert-BusinessDatabase "stable"
    $after = Get-TreeObservation $protectedPaths
    if($before.Sha256 -ne $after.Sha256){ throw "$($case.Probe) did not restore the old client, launchers and five-host skills" }
    $script:TransactionEvidence += [ordered]@{
      probe = $case.Probe; expected_version = $baselineVersion
      observed_version = Get-InstalledVersion "stable"
      observed_exit_code = [int]$probe.ExitCode; observed_exception = [bool]$probe.Thrown
      database_before_sha256 = $databaseBefore
      database_sha256 = (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash.ToLowerInvariant()
    }
  }
  New-FakeChannel "stable" "9.9.14"
  Install-ThroughWrapper "stable" "test" $true
  Assert-BusinessDatabase "stable"
  Assert-DatabaseSnapshot "stable"
  $latestSnapshot = Get-ChildItem -LiteralPath (Join-Path $fakeHome ".redbeacon\backups\pre-update") -Filter redbeacon.db -File -Recurse | Sort-Object FullName | Select-Object -Last 1
  $script:TransactionEvidence += [ordered]@{
    probe = "committed-update-database-snapshot"; expected_version = "9.9.14"
    observed_version = Get-InstalledVersion "stable"; observed_exit_code = 0; observed_exception = $false
    database_before_sha256 = $databaseBefore
    database_sha256 = (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash.ToLowerInvariant()
    snapshot_sha256 = (Get-FileHash -LiteralPath $latestSnapshot.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  }
  New-FakeChannel "stable"
}

function Write-InstallerTransactionReport($Observations, $ObservedEvidence) {
  $payload = [ordered]@{
    schema = "redbeacon-installer-transaction-smoke-report/v1"
    project = "redbeacon"
    build_run_id = $BuildRunId
    root_commit = $RootCommit
    cli_commit = $CliCommit
    version = $Version
    platform = "windows"
    channel = $Channel
    entrypoint_observations = @($Observations)
    observed_evidence = $ObservedEvidence
  }
  $parent = [System.IO.Path]::GetDirectoryName($ReportPath)
  [System.IO.Directory]::CreateDirectory($parent) | Out-Null
  $raw = [System.Text.UTF8Encoding]::new($false).GetBytes(
    ($payload | ConvertTo-Json -Depth 12 -Compress) + "`n"
  )
  $stream = [System.IO.File]::Open(
    $ReportPath,
    [System.IO.FileMode]::CreateNew,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::None
  )
  try {
    $stream.Write($raw, 0, $raw.Length)
    $stream.Flush()
  }
  finally {
    $stream.Dispose()
  }
}

function Invoke-RejectionProbe([string]$ScriptName) {
  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $global:LASTEXITCODE = 0
  $captured = @()
  $thrown = $false
  try { $captured = @(Invoke-PublicWrapper $ScriptName *>&1) }
  catch {
    $thrown = $true
    $captured += $_
  }
  finally { $ErrorActionPreference = $previousPreference }
  $exitCode = $LASTEXITCODE
  $output = ($captured | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
  return [pscustomobject]@{
    Failed = ($thrown -or $exitCode -ne 0)
    ExitCode = $exitCode
    Output = $output
    Thrown = $thrown
  }
}

function Assert-WrapperRejectsOppositeManifest([string]$ScriptName, [string]$Channel) {
  $opposite = if($Channel -eq "test"){ "stable" } else { "test" }
  $manifestPath = Join-Path $fake "projects\redbeacon\$Channel\latest.json"
  $oppositePath = Join-Path $fake "projects\redbeacon\$opposite\latest.json"
  $originalManifest = [System.IO.File]::ReadAllText($manifestPath)
  $snapshot = Set-HostileWrapperEnvironment $Channel $opposite
  $rejected = $false
  try {
    [System.IO.File]::WriteAllText(
      $manifestPath,
      [System.IO.File]::ReadAllText($oppositePath),
      [System.Text.UTF8Encoding]::new($false)
    )
    $probe = Invoke-RejectionProbe $ScriptName
    $rejected = ($probe.Failed -and $probe.Output -like "*does not match RedBeacon $Channel*")
  }
  finally {
    [System.IO.File]::WriteAllText($manifestPath, $originalManifest, [System.Text.UTF8Encoding]::new($false))
  }
  if(-not $rejected){ throw "$ScriptName accepted canonical bytes for the opposite channel" }
  Assert-EnvironmentSnapshot $snapshot "$ScriptName opposite-manifest failure"
  Assert-ForeignSentinels
  Add-RejectionEvidence $ScriptName "opposite-channel-manifest" $probe "does not match RedBeacon $Channel"
}

function Assert-WrapperRejectsWrongCoreUrl([string]$ScriptName, [string]$Channel, [string]$CoreName) {
  $manifestPath = Join-Path $fake "projects\redbeacon\$Channel\latest.json"
  $originalManifest = [System.IO.File]::ReadAllText($manifestPath)
  $opposite = if($Channel -eq "test"){ "stable" } else { "test" }
  $snapshot = Set-HostileWrapperEnvironment $Channel $opposite
  $rejected = $false
  try {
    $manifest = $originalManifest | ConvertFrom-Json
    $entry = @($manifest.artifacts | Where-Object { ([string]$_.path) -eq "installers/$CoreName" })
    if($entry.Count -ne 1){ throw "Smoke manifest has no $CoreName" }
    $entry[0].url = "$smokeOrigin/projects/redbeacon/$opposite/releases/9.9.9/installers/$CoreName"
    [System.IO.File]::WriteAllText(
      $manifestPath,
      ($manifest | ConvertTo-Json -Depth 8),
      [System.Text.UTF8Encoding]::new($false)
    )
    $probe = Invoke-RejectionProbe $ScriptName
    $rejected = ($probe.Failed -and $probe.Output -like "*core URL does not match*")
  }
  finally {
    [System.IO.File]::WriteAllText($manifestPath, $originalManifest, [System.Text.UTF8Encoding]::new($false))
  }
  if(-not $rejected){ throw "$ScriptName accepted a non-canonical core URL" }
  Assert-EnvironmentSnapshot $snapshot "$ScriptName wrong-URL failure"
  Assert-ForeignSentinels
  Add-RejectionEvidence $ScriptName "forged-core-url" $probe "core URL does not match"
}

function Assert-WrapperRejectsTamperedCore([string]$ScriptName, [string]$Channel, [string]$CoreName) {
  $corePath = Join-Path $fake "projects\redbeacon\$Channel\releases\9.9.9\installers\$CoreName"
  $originalCore = [System.IO.File]::ReadAllBytes($corePath)
  $opposite = if($Channel -eq "test"){ "stable" } else { "test" }
  $snapshot = Set-HostileWrapperEnvironment $Channel $opposite
  $rejected = $false
  try {
    $tampered = New-Object byte[] ($originalCore.Length + 1)
    [Array]::Copy($originalCore, $tampered, $originalCore.Length)
    $tampered[$tampered.Length - 1] = 10
    [System.IO.File]::WriteAllBytes($corePath, $tampered)
    $probe = Invoke-RejectionProbe $ScriptName
    $rejected = ($probe.Failed -and $probe.Output -like "*core size mismatch*")
  }
  finally {
    [System.IO.File]::WriteAllBytes($corePath, $originalCore)
  }
  if(-not $rejected){ throw "$ScriptName executed a core whose bytes do not match the manifest" }
  Assert-EnvironmentSnapshot $snapshot "$ScriptName tampered-core failure"
  Assert-ForeignSentinels
  Add-RejectionEvidence $ScriptName "tampered-core" $probe "core size mismatch"
}

function New-ProcessProbeExecutable() {
  $probeRoot = Join-Path $work "process-probes"
  New-Item -ItemType Directory -Force -Path $probeRoot | Out-Null
  $source = Join-Path $probeRoot "ProcessProbe.cs"
  $template = Join-Path $probeRoot "ProcessProbe.exe"
  $text = @"
using System;
using System.Threading;
public static class ProcessProbe {
  public static int Main() { while (true) Thread.Sleep(1000); }
}
"@
  [System.IO.File]::WriteAllText($source, $text, [System.Text.UTF8Encoding]::new($false))
  $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
  & $csc /nologo /target:exe "/out:$template" $source
  if($LASTEXITCODE -ne 0){ throw "Process probe compilation failed" }
  return $template
}

function Start-NamedProcessProbes([string]$Template, [string[]]$Names) {
  $result = @{}
  foreach($name in $Names){
    if(Get-Process -Name $name -ErrorAction SilentlyContinue){ throw "Process isolation probe name is already in use: $name" }
    $path = Join-Path (Split-Path $Template) "$name.exe"
    Copy-Item -LiteralPath $Template -Destination $path -Force
    $result[$name] = Start-Process -FilePath $path -PassThru -WindowStyle Hidden
  }
  Start-Sleep -Milliseconds 800
  return $result
}

function Assert-ProbeStopped($Process, [string]$Label) {
  $Process.Refresh()
  if(-not $Process.HasExited){ throw "$Label was not stopped by exact production process cleanup" }
}

function Assert-ProbeRunning($Process, [string]$Label) {
  $Process.Refresh()
  if($Process.HasExited){ throw "$Label was incorrectly stopped by another channel" }
}

function Stop-AllProbes($Processes) {
  foreach($process in $Processes.Values){
    try { $process.Refresh(); if(-not $process.HasExited){ Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } } catch {}
  }
}

function Assert-InstallerProductionProcessIsolation([string]$Template) {
  $tokens = $null
  $errors = $null
  $ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $ProjectRoot "install\install.ps1"), [ref]$tokens, [ref]$errors
  )
  $stopAst = $ast.Find({
    param($node)
    return ($node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq "Stop-RunningRedBeacon")
  }, $true)
  if(-not $stopAst){ throw "install.ps1 has no Stop-RunningRedBeacon function" }
  Invoke-Expression $stopAst.Extent.Text
  function Say($m){ Write-Host "==> $m" -ForegroundColor Cyan }
  $allNames = @("RbInstall", "rb-install-cli", "RbInstall_test", "rb-install-test-cli")
  foreach($channel in @("stable", "test")){
    $processes = Start-NamedProcessProbes $Template $allNames
    try {
      $RedBeaconInstallerExecutionMode = "production"
      if($channel -eq "stable"){
        $AppName = "RbInstall"
        $CliName = "rb-install-cli"
      } else {
        $AppName = "RbInstall_test"
        $CliName = "rb-install-test-cli"
      }
      Stop-RunningRedBeacon
      Start-Sleep -Milliseconds 800
      if($channel -eq "stable"){
        Assert-ProbeStopped $processes["RbInstall"] "installer stable desktop"
        Assert-ProbeStopped $processes["rb-install-cli"] "installer stable CLI"
        Assert-ProbeRunning $processes["RbInstall_test"] "installer test desktop"
        Assert-ProbeRunning $processes["rb-install-test-cli"] "installer test CLI"
      } else {
        Assert-ProbeStopped $processes["RbInstall_test"] "installer test desktop"
        Assert-ProbeStopped $processes["rb-install-test-cli"] "installer test CLI"
        Assert-ProbeRunning $processes["RbInstall"] "installer stable desktop"
        Assert-ProbeRunning $processes["rb-install-cli"] "installer stable CLI"
      }
    }
    finally { Stop-AllProbes $processes }
  }
}

function Assert-ProductionProcessIsolation() {
  $template = New-ProcessProbeExecutable
  Assert-InstallerProductionProcessIsolation $template
  $allNames = @("RedBeacon", "redbeacon-cli", "RedBeacon_test", "redbeacon-test-cli")
  foreach($channel in @("stable", "test")){
    $processes = Start-NamedProcessProbes $template $allNames
    $opposite = if($channel -eq "test"){ "stable" } else { "test" }
    $snapshot = Set-HostileWrapperEnvironment $channel $opposite
    $env:REDBEACON_PURGE = "0"
    try {
      $scriptName = if($channel -eq "test"){ "uninstall-test.ps1" } else { "uninstall.ps1" }
      $global:LASTEXITCODE = 0
      & $productionTestWrappers[$scriptName]
      if($LASTEXITCODE -ne 0){ throw "$channel production uninstaller returned exit code $LASTEXITCODE" }
      Start-Sleep -Milliseconds 800
      if($channel -eq "stable"){
        Assert-ProbeStopped $processes["RedBeacon"] "stable desktop"
        Assert-ProbeStopped $processes["redbeacon-cli"] "stable CLI"
        Assert-ProbeRunning $processes["RedBeacon_test"] "test desktop"
        Assert-ProbeRunning $processes["redbeacon-test-cli"] "test CLI"
      } else {
        Assert-ProbeStopped $processes["RedBeacon_test"] "test desktop"
        Assert-ProbeStopped $processes["redbeacon-test-cli"] "test CLI"
        Assert-ProbeRunning $processes["RedBeacon"] "stable desktop"
        Assert-ProbeRunning $processes["redbeacon-cli"] "stable CLI"
      }
      $targetName = if($channel -eq "stable"){ "RedBeacon" } else { "RedBeacon_test" }
      $otherName = if($channel -eq "stable"){ "RedBeacon_test" } else { "RedBeacon" }
      $script:ProcessEvidence += [pscustomobject]@{
        target_channel = $channel; target_process = $targetName
        target_exit_code = $processes[$targetName].ExitCode
        opposite_process = $otherName
        opposite_process_observed_running = (-not $processes[$otherName].HasExited)
      }
      Assert-EnvironmentSnapshot $snapshot "$channel production uninstaller"
      Assert-ForeignSentinels
    }
    finally { Stop-AllProbes $processes }
  }
  Write-Host "Windows production process cleanup is channel-exact"
}

$script:RejectionEvidence = @()
$script:TransactionEvidence = @()
$script:ProcessEvidence = @()
$script:CallerBefore = @()
$script:CallerAfter = @()
$script:ForeignBefore = $null
$script:ForeignSentinels = @{}
$script:ForeignDirectoryExpected = @{}

$server = $null
try {
  Set-Variable -Name HOME -Value $fakeHome -Force
  $env:USERPROFILE = $fakeHome
  $env:LOCALAPPDATA = $fakeLocalAppData
  $env:APPDATA = $fakeAppData
  $env:TEMP = Join-Path $work "temp"
  $env:CI = "true"
  $env:REDBEACON_NO_PAUSE = "1"
  New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

  New-ExecutionHijacks
  New-SmokeWrappers
  foreach($relative in $publicWrappers){
    Assert-PublicWrapperRejectsArguments (Split-Path $relative -Leaf)
  }
  Assert-PublicWrapperSourcesUnchanged

  New-FakeChannel "stable"
  New-FakeChannel "test"
  $server = Start-Process -FilePath $PythonExe -ArgumentList @("-m", "http.server", "8765", "--directory", $fake) -PassThru -WindowStyle Hidden -RedirectStandardError $serverRequestLog
  $ready = $false
  foreach($i in 1..30){
    try {
      Invoke-WebRequest -Uri "http://127.0.0.1:8765/projects/redbeacon/stable/latest.json" -UseBasicParsing -TimeoutSec 2 | Out-Null
      $ready = $true
      break
    } catch { Start-Sleep -Milliseconds 500 }
  }
  if(-not $ready){ throw "Fake OSS server did not start" }

  Assert-WrappersResistCommandShadows
  Assert-ProductionProcessIsolation

  foreach($case in @(
    @{ Script = "install.ps1"; Channel = "stable" },
    @{ Script = "uninstall.ps1"; Channel = "stable" },
    @{ Script = "install-test.ps1"; Channel = "test" },
    @{ Script = "uninstall-test.ps1"; Channel = "test" }
  )){
    Assert-WrapperRejectsOppositeManifest $case.Script $case.Channel
    if($case.Script.StartsWith("uninstall")){
      Assert-WrapperRejectsWrongCoreUrl $case.Script $case.Channel "uninstall-core.ps1"
      Assert-WrapperRejectsTamperedCore $case.Script $case.Channel "uninstall-core.ps1"
    }
  }

  Seed-ChannelState "stable"
  Seed-ChannelState "test"
  Install-ThroughWrapper "stable" "test" $true
  Assert-Uninstalled "test"
  Assert-ChannelPersistentState "stable" $true
  Assert-ChannelPersistentState "test" $true
  Install-ThroughWrapper "stable" "testing" $false
  Install-ThroughWrapper "stable" "beta" $false
  Seed-BusinessDatabase "stable"
  Assert-TransactionRollbackEvidence
  Install-ThroughWrapper "stable" "test" $true
  Assert-BusinessDatabase "stable"
  Assert-DatabaseSnapshot "stable"
  Assert-ChannelPersistentState "test" $true

  Install-ThroughWrapper "test" "stable" $true
  Install-ThroughWrapper "test" "production" $false
  Seed-BusinessDatabase "test"
  Install-ThroughWrapper "test" "prod" $true
  Assert-BusinessDatabase "test"
  Assert-DatabaseSnapshot "test"
  Assert-Installed "stable"
  Assert-Installed "test"
  Assert-ChannelPersistentState "stable" $true
  Assert-ChannelPersistentState "test" $true

  $oppositeBefore = Get-TreeObservation (Channel-ObservedPaths "test")
  Uninstall-ThroughWrapper "stable" "beta"
  $oppositeAfter = Get-TreeObservation (Channel-ObservedPaths "test")
  Assert-BusinessDatabase "stable"
  Assert-ChannelPersistentState "stable" $false
  Assert-ChannelPersistentState "test" $true
  Assert-Installed "test"
  Seed-ChannelState "stable"
  Install-ThroughWrapper "stable" "testing" $true
  Assert-Installed "test"
  Assert-ChannelPersistentState "test" $true
  Uninstall-ThroughWrapper "test" "stable"
  Assert-BusinessDatabase "test"
  Assert-ChannelPersistentState "test" $false
  Assert-ChannelPersistentState "stable" $true
  Assert-Installed "stable"
  Uninstall-ThroughWrapper "stable" "test"
  Assert-BusinessDatabase "stable"
  Assert-ChannelPersistentState "stable" $false
  Assert-ChannelPersistentState "test" $false
  Assert-ForeignSentinels
  Assert-PublicWrapperSourcesUnchanged
  if([Environment]::GetEnvironmentVariable("Path", "User") -ne $originalPersistentUserPath){
    throw "Windows installer transaction smoke mutated the real persistent user PATH"
  }
  $aliasRuns = @()
  foreach($aliasChannel in @("stable", "test")){
    foreach($alias in @("testing", "beta")){
      $aliasRuns += Invoke-ObservedAlias $aliasChannel $alias
    }
  }
  $observations = @()
  foreach($observedChannel in @("stable", "test")){
    foreach($operation in @("install", "uninstall")){
      $observations += Invoke-ObservedEntrypoint $observedChannel $operation
    }
  }
  Assert-ForeignSentinels
  Assert-PublicWrapperSourcesUnchanged
  $foreignAfter = Get-TreeObservation @($script:ForeignDirectoryExpected.Keys)
  $observedEvidence = [ordered]@{
    alias_runs = @($aliasRuns)
    rejection_runs = @($script:RejectionEvidence)
    state_snapshots = @(
      [ordered]@{ scope = "caller-controlled-paths"; item_count = $script:ForeignBefore.Count; before_sha256 = $script:ForeignBefore.Sha256; after_sha256 = $foreignAfter.Sha256 },
      [ordered]@{ scope = "opposite-test-state-during-stable-uninstall"; item_count = $oppositeBefore.Count; before_sha256 = $oppositeBefore.Sha256; after_sha256 = $oppositeAfter.Sha256 }
    )
    process_isolation = @($script:ProcessEvidence)
    transaction_checks = @($script:TransactionEvidence)
    caller_environment = [ordered]@{
      before_sha256 = Get-TextDigest ($script:CallerBefore -join "`n")
      after_sha256 = Get-TextDigest ($script:CallerAfter -join "`n")
    }
    execution_hijack = [ordered]@{
      probes = @("caller-path-binaries", "powershell-command-shadows")
      protected_before_sha256 = $script:ForeignBefore.Sha256
      protected_after_sha256 = $foreignAfter.Sha256
      marker_observed_count = [int](Test-Path -LiteralPath $script:ExecutionHijackMarker)
    }
  }
  Write-InstallerTransactionReport $observations $observedEvidence
  Write-Host "Windows installer transaction smoke passed"
  Write-Host "Raw installer transaction smoke report: $ReportPath"
}
finally {
  if($server -and -not $server.HasExited){ Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
  foreach($dir in $shortcutDirs){
    foreach($name in @("RedBeacon.lnk", "RedBeacon_test.lnk")){
      Remove-Item -Force (Join-Path $dir $name) -ErrorAction SilentlyContinue
      $backup = Join-Path $shortcutBackup ($dir.GetHashCode().ToString() + "-" + $name)
      if(Test-Path $backup){ Copy-Item -Force $backup (Join-Path $dir $name) }
    }
  }
  Set-Variable -Name HOME -Value $originalHome -Force
  $env:USERPROFILE = $originalUserProfile
  $env:LOCALAPPDATA = $originalLocalAppData
  $env:APPDATA = $originalAppData
  $env:TEMP = $originalTemp
  [Environment]::SetEnvironmentVariable("Path", $originalPersistentUserPath, "User")
  if($null -eq $originalCi){ Remove-Item Env:\CI -ErrorAction SilentlyContinue } else { $env:CI = $originalCi }
  if($null -eq $originalNoPause){ Remove-Item Env:\REDBEACON_NO_PAUSE -ErrorAction SilentlyContinue } else { $env:REDBEACON_NO_PAUSE = $originalNoPause }
  if($null -eq $originalPurge){ Remove-Item Env:\REDBEACON_PURGE -ErrorAction SilentlyContinue } else { $env:REDBEACON_PURGE = $originalPurge }
  if($null -eq $originalForceInstall){ Remove-Item Env:\REDBEACON_FORCE_INSTALL -ErrorAction SilentlyContinue } else { $env:REDBEACON_FORCE_INSTALL = $originalForceInstall }
  $env:Path = $originalProcessPath
  foreach($name in $hostileEnvironmentNames){
    [Environment]::SetEnvironmentVariable($name, $originalHostileEnvironment[$name], "Process")
  }
  Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
