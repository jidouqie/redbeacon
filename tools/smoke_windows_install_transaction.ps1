param(
  [string]$ProjectRoot = ".",
  [string]$PythonExe = "python.exe"
)

# Local Windows installer smoke. Everything except temporary shortcuts is
# redirected under one disposable home; pre-existing shortcuts are restored.
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$PythonExe = [System.IO.Path]::GetFullPath($PythonExe)
if(-not (Test-Path $PythonExe)){ throw "Python executable not found: $PythonExe" }

$scripts = @(
  "install\install.ps1",
  "install\install-test.ps1",
  "install\uninstall.ps1",
  "install\uninstall-test.ps1"
)
foreach($relative in $scripts){
  $path = Join-Path $ProjectRoot $relative
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors) | Out-Null
  if($errors -and $errors.Count -gt 0){
    throw "$relative has PowerShell parser errors: $($errors | Out-String)"
  }
  Write-Host "PowerShell syntax ok: $relative"
}

$work = Join-Path $env:TEMP ("redbeacon_installer_smoke_" + [guid]::NewGuid())
$fake = Join-Path $work "fake-oss"
$build = Join-Path $work "fake-build"
$fakeHome = Join-Path $work "home"
$fakeLocalAppData = Join-Path $work "localappdata"
$fakeAppData = Join-Path $work "appdata"
New-Item -ItemType Directory -Force -Path $fake, $build, $fakeHome, $fakeLocalAppData, $fakeAppData | Out-Null

$originalHome = $HOME
$originalUserProfile = $env:USERPROFILE
$originalLocalAppData = $env:LOCALAPPDATA
$originalAppData = $env:APPDATA
$originalTemp = $env:TEMP
$originalCi = $env:CI
$originalNoPause = $env:REDBEACON_NO_PAUSE
$originalPurge = $env:REDBEACON_PURGE
$originalUpdateUrl = $env:REDBEACON_UPDATE_URL
$originalInstallerTestMode = $env:REDBEACON_INSTALLER_TEST_MODE
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

function New-FakeChannel([string]$Channel) {
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
      if (args.Length > 0 && args[0] == "--version") { Console.WriteLine("redbeacon 9.9.9"); return 0; }
      if (args.Length > 0 && args[0] == "setup") {
        var home = Environment.GetEnvironmentVariable("USERPROFILE");
        var root = Path.Combine(home, "$runtimeFolder");
        if (Environment.GetEnvironmentVariable("REDBEACON_DATA_DIR") != Path.Combine(root, "data")) return 34;
        if (Environment.GetEnvironmentVariable("PLAYWRIGHT_BROWSERS_PATH") != Path.Combine(root, "browser", "ms-playwright")) return 35;
        if (Environment.GetEnvironmentVariable("CLOAKBROWSER_CACHE_DIR") != Path.Combine(root, "browser", "cloakbrowser")) return 36;
        Console.WriteLine("{\"ok\":true}"); return 0;
      }
      if (Environment.GetEnvironmentVariable("REDBEACON_DESKTOP_SMOKE") == "1") {
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

  $channelRoot = Join-Path $fake "projects\redbeacon\$Channel"
  $releaseRoot = Join-Path $channelRoot "releases\9.9.9"
  $zipDir = Join-Path $releaseRoot "packages"
  New-Item -ItemType Directory -Force -Path $zipDir | Out-Null
  $zip = Join-Path $zipDir "$appName-win-x64.zip"
  Compress-Archive -Path $appDir -DestinationPath $zip -Force

  $skillRoot = Join-Path $build "skill-$Channel"
  $commands = Join-Path $skillRoot ".claude\commands"
  New-Item -ItemType Directory -Force -Path $commands | Out-Null
  $skillText = "---`ndescription: smoke $Channel`n---`n# smoke`n$skillCommand checkin"
  [System.IO.File]::WriteAllText((Join-Path $commands $skillFile), $skillText, [System.Text.UTF8Encoding]::new($false))
  $skillDir = Join-Path $releaseRoot "skill"
  New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
  $skillBundle = Join-Path $skillDir "redbeacon-skill.tar.gz"
  & tar.exe -czf $skillBundle -C $skillRoot .
  if($LASTEXITCODE -ne 0){ throw "Fake skill archive creation failed" }

  $installerDir = Join-Path $releaseRoot "installers"
  New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
  Copy-Item -Force (Join-Path $ProjectRoot "install\install.ps1") (Join-Path $installerDir "install.ps1")
  Copy-Item -Force (Join-Path $ProjectRoot "install\uninstall.ps1") (Join-Path $installerDir "uninstall.ps1")

  $artifacts = @()
  foreach($relative in @(
    "packages/$appName-win-x64.zip",
    "skill/redbeacon-skill.tar.gz",
    "installers/install.ps1",
    "installers/uninstall.ps1"
  )){
    $localPath = Join-Path $releaseRoot ($relative.Replace('/', '\'))
    $url = "http://127.0.0.1:8765/projects/redbeacon/$Channel/releases/9.9.9/$relative"
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
    version = "9.9.9"
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
      SkillBase = "redbeacon-test"; SkillDir = Join-Path $work "skills-test"
    }
  }
  return @{
    AppName = "RedBeacon"; CmdName = "redbeacon"; SkillFile = "redbeacon.md"
    SkillBase = "redbeacon"; SkillDir = Join-Path $work "skills-stable"
  }
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
  $dest = Join-Path $env:LOCALAPPDATA "Programs\$($spec.AppName)"
  $shim = Join-Path $HOME ".local\bin\$($spec.CmdName).cmd"
  $claudeSkill = Join-Path $spec.SkillDir $spec.SkillFile
  $codexSkill = Join-Path $HOME ".codex\skills\$($spec.SkillBase)\SKILL.md"
  foreach($path in @($dest, $shim, $claudeSkill, $codexSkill)){
    if(-not (Test-Path $path)){ throw "$Channel install did not create $path" }
  }
  $codexText = Get-Content -Raw -Encoding UTF8 -Path $codexSkill
  if($codexText -notmatch "(?m)^name:\s*$([regex]::Escape($spec.SkillBase))\s*$"){
    throw "$Channel Codex skill frontmatter has the wrong name"
  }
}

function Assert-Uninstalled([string]$Channel) {
  $spec = Channel-Spec $Channel
  $paths = @(
    (Join-Path $env:LOCALAPPDATA "Programs\$($spec.AppName)"),
    (Join-Path $HOME ".local\bin\$($spec.CmdName).cmd"),
    (Join-Path $spec.SkillDir $spec.SkillFile),
    (Join-Path $HOME ".codex\skills\$($spec.SkillBase)\SKILL.md")
  )
  foreach($path in $paths){ if(Test-Path $path){ throw "$Channel uninstall did not remove $path" } }
}

function Install-Channel([string]$Channel) {
  $spec = Channel-Spec $Channel
  $env:REDBEACON_UPDATE_URL = "http://127.0.0.1:8765/projects/redbeacon/$Channel/latest.json"
  $env:REDBEACON_INSTALLER_TEST_MODE = "1"
  $env:REDBEACON_CHANNEL = $Channel
  $env:REDBEACON_FORCE_INSTALL = "1"
  $env:REDBEACON_SKILL_DIR = $spec.SkillDir
  & (Join-Path $ProjectRoot "install\install.ps1")
  if($LASTEXITCODE -ne 0){ throw "$Channel installer failed" }
  Remove-Item Env:\REDBEACON_FORCE_INSTALL -ErrorAction SilentlyContinue
  Assert-Installed $Channel
}

function Install-TestThroughWrapper([bool]$Force = $true) {
  $spec = Channel-Spec "test"
  $env:REDBEACON_UPDATE_URL = "http://127.0.0.1:8765/projects/redbeacon/test/latest.json"
  $env:REDBEACON_INSTALLER_TEST_MODE = "1"
  $env:REDBEACON_CHANNEL = "stable"
  if($Force){ $env:REDBEACON_FORCE_INSTALL = "1" }
  else { Remove-Item Env:\REDBEACON_FORCE_INSTALL -ErrorAction SilentlyContinue }
  $env:REDBEACON_SKILL_DIR = $spec.SkillDir
  & (Join-Path $ProjectRoot "install\install-test.ps1")
  if($LASTEXITCODE -ne 0){ throw "test wrapper installer failed" }
  if($env:REDBEACON_CHANNEL -ne "stable"){ throw "test installer leaked REDBEACON_CHANNEL into PowerShell" }
  Remove-Item Env:\REDBEACON_FORCE_INSTALL -ErrorAction SilentlyContinue
  Assert-Installed "test"
}

function Uninstall-Channel([string]$Channel) {
  $spec = Channel-Spec $Channel
  $env:REDBEACON_CHANNEL = $Channel
  $env:REDBEACON_PURGE = "0"
  $env:REDBEACON_SKILL_DIR = $spec.SkillDir
  & (Join-Path $ProjectRoot "install\uninstall.ps1")
  if($LASTEXITCODE -ne 0){ throw "$Channel uninstaller failed" }
  Assert-Uninstalled $Channel
}

function Uninstall-TestThroughWrapper() {
  $spec = Channel-Spec "test"
  $env:REDBEACON_UPDATE_URL = "http://127.0.0.1:8765/projects/redbeacon/test/latest.json"
  $env:REDBEACON_INSTALLER_TEST_MODE = "1"
  $env:REDBEACON_CHANNEL = "stable"
  $env:REDBEACON_PURGE = "0"
  $env:REDBEACON_SKILL_DIR = $spec.SkillDir
  & (Join-Path $ProjectRoot "install\uninstall-test.ps1")
  if($LASTEXITCODE -ne 0){ throw "test wrapper uninstaller failed" }
  if($env:REDBEACON_CHANNEL -ne "stable"){ throw "test uninstaller leaked REDBEACON_CHANNEL into PowerShell" }
  Assert-Uninstalled "test"
}

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

  New-FakeChannel "stable"
  New-FakeChannel "test"
  Copy-Item -Force (Join-Path $ProjectRoot "install\install.ps1") (Join-Path $fake "install.ps1")
  Copy-Item -Force (Join-Path $ProjectRoot "install\uninstall.ps1") (Join-Path $fake "uninstall.ps1")
  $server = Start-Process -FilePath $PythonExe -ArgumentList @("-m", "http.server", "8765", "--directory", $fake) -PassThru -WindowStyle Hidden
  $ready = $false
  foreach($i in 1..30){
    try {
      Invoke-WebRequest -Uri "http://127.0.0.1:8765/projects/redbeacon/stable/latest.json" -UseBasicParsing -TimeoutSec 2 | Out-Null
      $ready = $true
      break
    } catch { Start-Sleep -Milliseconds 500 }
  }
  if(-not $ready){ throw "Fake OSS server did not start" }

  Install-Channel "stable"
  Seed-BusinessDatabase "stable"
  Install-Channel "stable"
  Assert-BusinessDatabase "stable"
  Assert-DatabaseSnapshot "stable"
  Install-TestThroughWrapper
  Install-TestThroughWrapper $false
  Seed-BusinessDatabase "test"
  Install-Channel "test"
  Assert-BusinessDatabase "test"
  Assert-DatabaseSnapshot "test"
  Assert-Installed "stable"
  Assert-Installed "test"
  Uninstall-TestThroughWrapper
  Assert-BusinessDatabase "test"
  Assert-Installed "stable"
  Uninstall-Channel "stable"
  Assert-BusinessDatabase "stable"
  Write-Host "Windows installer transaction smoke passed"
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
  if($null -eq $originalCi){ Remove-Item Env:\CI -ErrorAction SilentlyContinue } else { $env:CI = $originalCi }
  if($null -eq $originalNoPause){ Remove-Item Env:\REDBEACON_NO_PAUSE -ErrorAction SilentlyContinue } else { $env:REDBEACON_NO_PAUSE = $originalNoPause }
  if($null -eq $originalPurge){ Remove-Item Env:\REDBEACON_PURGE -ErrorAction SilentlyContinue } else { $env:REDBEACON_PURGE = $originalPurge }
  if($null -eq $originalUpdateUrl){ Remove-Item Env:\REDBEACON_UPDATE_URL -ErrorAction SilentlyContinue } else { $env:REDBEACON_UPDATE_URL = $originalUpdateUrl }
  if($null -eq $originalInstallerTestMode){ Remove-Item Env:\REDBEACON_INSTALLER_TEST_MODE -ErrorAction SilentlyContinue } else { $env:REDBEACON_INSTALLER_TEST_MODE = $originalInstallerTestMode }
  Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
