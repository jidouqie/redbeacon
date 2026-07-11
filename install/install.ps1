# ------------------------------------------------------------------------------
# RedBeacon installer (Windows). Run in PowerShell:
#     irm https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install.ps1 | iex
#
# Installs a SELF-CONTAINED bundle (Python + all deps + Playwright driver already
# inside). No uv / no pip / no compiling -- just download + unzip + place.
# Gives you both a double-click desktop app AND the `redbeacon` command.
# The browser engine (Chromium) is prepared during install via mirrors.
# All output is ASCII-only on purpose (avoids garbled text / iex decode issues).
# ------------------------------------------------------------------------------
$ErrorActionPreference = "Stop"
function Say($m){ Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "!! $m" -ForegroundColor Yellow }
function Pause-OnFailure(){
  if($env:CI -eq "true" -or $env:GITHUB_ACTIONS -eq "true" -or $env:REDBEACON_NO_PAUSE -eq "1"){ return }
  try { Read-Host "Press Enter to close this window" | Out-Null } catch {}
}
trap {
  if(Get-Command Restore-Skills -ErrorAction SilentlyContinue){ Restore-Skills }
  Write-Host ""
  Write-Host "xx RedBeacon install failed. Details:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  if($_.ScriptStackTrace){ Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray }
  Pause-OnFailure
  exit 1
}
function Die($m){ throw $m }
function Test-ManagedSkillName([string]$Stem){
  if($Channel -eq "test"){ return $Stem.StartsWith("redbeacon-test") }
  return $Stem.StartsWith("redbeacon") -and -not $Stem.StartsWith("redbeacon-test")
}
function Write-CodexSkills($SrcDir){
  if(-not $SrcDir){ return }
  $codexDir = Join-Path $HOME ".codex\skills"
  New-Item -ItemType Directory -Force -Path $codexDir | Out-Null
  Get-ChildItem -Path $SrcDir -Filter "redbeacon*.md" -ErrorAction SilentlyContinue | ForEach-Object {
    $stem = $_.BaseName
    if(-not (Test-ManagedSkillName $stem)){ return }
    $text = Get-Content -Raw -Encoding UTF8 -Path $_.FullName
    $desc = "RedBeacon ability: $stem"
    if($text -match "(?m)^description:\s*(.+)$"){
      $desc = $Matches[1].Trim().Trim('"').Trim("'")
    }
    $body = $text
    if($body.StartsWith("---")){
      $m = [regex]::Match($body, "(?s)^---\r?\n.*?\r?\n---\r?\n?")
      if($m.Success){ $body = $body.Substring($m.Length) }
    }
    $esc = $desc.Replace('\', '\\').Replace('"', '\"')
    $folder = Join-Path $codexDir $stem
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $skill = "---`nname: $stem`ndescription: `"$esc`"`nmetadata:`n  short-description: `"$esc`"`n---`n`n$body"
    $target = Join-Path $folder "SKILL.md"
    $staged = "$target.new.$PID"
    [System.IO.File]::WriteAllText($staged, $skill, [System.Text.UTF8Encoding]::new($false))
    Move-Item -Force $staged $target
  }
}
function Run-BrowserSetup($CliPath){
  if(-not (Test-Path $CliPath)){ Die "CLI executable not found for browser setup: $CliPath" }
  if($env:REDBEACON_SKIP_BROWSER_SETUP -eq "1" -and ($env:CI -eq "true" -or $env:GITHUB_ACTIONS -eq "true")){
    Warn "  browser engine setup skipped by REDBEACON_SKIP_BROWSER_SETUP=1"
    return
  }
  Say "[3/4] Preparing browser engine (this can take a while on first install) ..."
  $oldOut = $env:REDBEACON_OUT
  $runtimeEnv = Push-RuntimeEnvironment
  $env:REDBEACON_OUT = "compact"
  try {
    & $CliPath setup
    if($LASTEXITCODE -ne 0){ Die "Browser engine setup failed. Re-run the installer after checking network/proxy." }
  } finally {
    if($null -eq $oldOut){ Remove-Item Env:\REDBEACON_OUT -ErrorAction SilentlyContinue } else { $env:REDBEACON_OUT = $oldOut }
    Pop-RuntimeEnvironment $runtimeEnv
  }
  Say "Browser engine is ready."
}
$script:PreparedSkillSrc = $null
function Prepare-Skills($TempDir){
  Say "Preparing the matching skill bundle ..."
  $skok = $false
  $skillStage = Join-Path $TempDir "skill-stage"
  Remove-Item -Recurse -Force $skillStage -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $skillStage | Out-Null
  foreach($t in 1..3){
    try {
      $star = Join-Path $TempDir "skill.tar.gz"
      Invoke-WebRequest -Uri $SkillUrl -OutFile $star -UseBasicParsing -TimeoutSec 90
      if($SkillSha){
        $skillGot = (Get-FileHash -Algorithm SHA256 -Path $star).Hash.ToLowerInvariant()
        if($skillGot -ne $SkillSha){ throw "skill checksum mismatch" }
      }
      Remove-Item -Recurse -Force $skillStage -ErrorAction SilentlyContinue
      New-Item -ItemType Directory -Force -Path $skillStage | Out-Null
      tar -xzf $star -C $skillStage
      if($LASTEXITCODE -ne 0){ throw "skill archive extraction failed" }
      $skok = $true; break
    } catch { Warn "  skills fetch failed, retrying..." }
  }
  if(-not $skok){ Die "Could not prepare the matching skill bundle. The existing installation was not changed." }
  $src = Get-ChildItem -Path $skillStage -Recurse -Directory | Where-Object { $_.FullName -match "\.claude[\\/]commands$" } | Select-Object -First 1
  if(-not $src){ Die "Skill bundle is incomplete. The existing installation was not changed." }
  if(-not (Get-ChildItem -Path $src.FullName -Filter "redbeacon*.md" -ErrorAction SilentlyContinue)){
    Die "Skill bundle contains no RedBeacon skills. The existing installation was not changed."
  }
  if($SkillVersion){
    $metaPath = Get-ChildItem -Path $skillStage -Recurse -Filter "redbeacon-skill-manifest.json" -File | Select-Object -First 1
    if(-not $metaPath){ Die "Skill bundle has no release metadata. The existing installation was not changed." }
    try { $skillMeta = Get-Content -Raw -Encoding UTF8 -Path $metaPath.FullName | ConvertFrom-Json }
    catch { Die "Skill bundle release metadata is invalid. The existing installation was not changed." }
    if(([string]$skillMeta.version) -ne $SkillVersion -or ([string]$skillMeta.channel) -ne $Channel){
      Die "Skill bundle version/channel does not match the client manifest. The existing installation was not changed."
    }
  }
  $script:PreparedSkillSrc = $src.FullName
}
$script:SkillTransactionActive = $false
$script:SkillBackupRoot = $null
function Get-ManagedClaudeSkills(){
  if(-not (Test-Path $SkillDest)){ return @() }
  return @(Get-ChildItem -Path $SkillDest -Filter "redbeacon*.md" -File -ErrorAction SilentlyContinue |
    Where-Object { Test-ManagedSkillName $_.BaseName })
}
function Get-ManagedCodexSkills(){
  $codexDir = Join-Path $HOME ".codex\skills"
  if(-not (Test-Path $codexDir)){ return @() }
  return @(Get-ChildItem -Path $codexDir -Filter "redbeacon*" -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-ManagedSkillName $_.Name })
}
function Remove-ManagedSkills(){
  Get-ManagedClaudeSkills | Remove-Item -Force
  Get-ManagedCodexSkills | Remove-Item -Recurse -Force
}
function Begin-SkillTransaction($TempDir){
  if($script:SkillTransactionActive){ return }
  $script:SkillBackupRoot = Join-Path $TempDir "skill-backup"
  Remove-Item -Recurse -Force $script:SkillBackupRoot -ErrorAction SilentlyContinue
  $claudeBackup = Join-Path $script:SkillBackupRoot "claude"
  $codexBackup = Join-Path $script:SkillBackupRoot "codex"
  New-Item -ItemType Directory -Force -Path $claudeBackup, $codexBackup | Out-Null
  Get-ManagedClaudeSkills | Copy-Item -Destination $claudeBackup -Force
  Get-ManagedCodexSkills | Copy-Item -Destination $codexBackup -Recurse -Force
  $script:SkillTransactionActive = $true
}
function Restore-Skills(){
  if(-not $script:SkillTransactionActive){ return }
  try {
    Remove-ManagedSkills
    New-Item -ItemType Directory -Force -Path $SkillDest, (Join-Path $HOME ".codex\skills") | Out-Null
    Get-ChildItem -Path (Join-Path $script:SkillBackupRoot "claude") -File -ErrorAction SilentlyContinue |
      Copy-Item -Destination $SkillDest -Force
    Get-ChildItem -Path (Join-Path $script:SkillBackupRoot "codex") -Directory -ErrorAction SilentlyContinue |
      Copy-Item -Destination (Join-Path $HOME ".codex\skills") -Recurse -Force
  } catch {}
  $script:SkillTransactionActive = $false
}
function Commit-Skills(){
  $script:SkillTransactionActive = $false
  if($script:SkillBackupRoot){ Remove-Item -Recurse -Force $script:SkillBackupRoot -ErrorAction SilentlyContinue }
}
function Install-Skills($CliPath, $TempDir){
  if(-not $script:PreparedSkillSrc -or -not (Test-Path $script:PreparedSkillSrc)){
    Die "Prepared skill bundle is unavailable."
  }
  Say "Installing the matching skills ..."
  Begin-SkillTransaction $TempDir
  Remove-ManagedSkills
  New-Item -ItemType Directory -Force -Path $SkillDest | Out-Null
  $sourceSkills = @(Get-ChildItem -Path $script:PreparedSkillSrc -Filter "redbeacon*.md" -File |
    Where-Object { Test-ManagedSkillName $_.BaseName })
  if($sourceSkills.Count -eq 0){ Die "Prepared skill bundle has no files for channel $Channel." }
  $sourceSkills | Copy-Item -Force -Destination $SkillDest
  Write-CodexSkills $script:PreparedSkillSrc
  $sourceSkills | ForEach-Object {
    if(-not (Test-Path (Join-Path $SkillDest $_.Name))){ Die "Claude-style skill verification failed: $($_.BaseName)" }
    if(-not (Test-Path (Join-Path $HOME ".codex\skills\$($_.BaseName)\SKILL.md"))){ Die "Codex skill verification failed: $($_.BaseName)" }
    $sourceHash = (Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash
    $destHash = (Get-FileHash -Algorithm SHA256 -Path (Join-Path $SkillDest $_.Name)).Hash
    if($sourceHash -ne $destHash){ Die "Claude-style skill content verification failed: $($_.BaseName)" }
  }
  try { & $CliPath config set skill_install_dir $SkillDest | Out-Null } catch {}
}
function Stop-RunningRedBeacon(){
  Say "Stopping running $AppName processes ..."
  $names = @($AppName, $CliName)
  $deadline = (Get-Date).AddSeconds(15)
  while((Get-Date) -lt $deadline){
    $procs = @(Get-Process -Name $names -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $PID })
    if($procs.Count -eq 0){ return }
    $procs | Stop-Process -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 700
  }
  $procs = @(Get-Process -Name $names -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $PID })
  if($procs.Count -gt 0){
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
  }
}

function Push-RuntimeEnvironment(){
  $values = @{
    "REDBEACON_CHANNEL" = $Channel
    "REDBEACON_DATA_DIR" = $RuntimeDataDir
    "REDBEACON_PLAYWRIGHT_DIR" = $RuntimePlaywrightDir
    "REDBEACON_CLOAKBROWSER_DIR" = $RuntimeCloakDir
    "PLAYWRIGHT_BROWSERS_PATH" = $RuntimePlaywrightDir
    "CLOAKBROWSER_CACHE_DIR" = $RuntimeCloakDir
    "CLOAKBROWSER_AUTO_UPDATE" = "false"
  }
  $keys = @($values.Keys) + @(
    "CLOAKBROWSER_BINARY_PATH", "CLOAKBROWSER_VERSION", "CLOAKBROWSER_SKIP_CHECKSUM",
    "REDBEACON_DESKTOP_SMOKE"
  )
  $old = @{}
  foreach($key in $keys){
    $old[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
  }
  foreach($entry in $values.GetEnumerator()){
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
  }
  foreach($key in @("CLOAKBROWSER_BINARY_PATH", "CLOAKBROWSER_VERSION", "CLOAKBROWSER_SKIP_CHECKSUM", "REDBEACON_DESKTOP_SMOKE")){
    [Environment]::SetEnvironmentVariable($key, $null, "Process")
  }
  return $old
}

function Pop-RuntimeEnvironment($Old){
  foreach($entry in $Old.GetEnumerator()){
    [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
  }
}

function Verify-Bundle($CliPath, $RendererPath, $ExpectedVersion){
  if(-not (Test-Path $CliPath)){ Die "Bundle verification cannot start the CLI: $CliPath" }
  if(-not (Test-Path $RendererPath)){ Die "Bundle verification cannot start the card renderer: $RendererPath" }
  $verifyRoot = Join-Path $tmp ("bundle-verify-" + [guid]::NewGuid())
  $cards = Join-Path $verifyRoot "cards"
  New-Item -ItemType Directory -Force -Path $cards | Out-Null
  $runtimeEnv = Push-RuntimeEnvironment
  try {
    $versionText = ((& $CliPath --version 2>&1) | Out-String).Trim()
    $versionExit = $LASTEXITCODE
    if($versionExit -ne 0){ Die "The new client failed its version check: $versionText" }
    $parts = @($versionText -split "\s+" | Where-Object { $_ })
    $actualVersion = if($parts.Count -gt 0){ $parts[-1] } else { "" }
    if($ExpectedVersion -and $actualVersion -ne $ExpectedVersion){
      Die "Downloaded client version $actualVersion does not match manifest version $ExpectedVersion."
    }

    $env:REDBEACON_DESKTOP_SMOKE = "1"
    $desktopSmoke = ((& $CliPath 2>&1) | Out-String)
    $desktopExit = $LASTEXITCODE
    Remove-Item Env:\REDBEACON_DESKTOP_SMOKE -ErrorAction SilentlyContinue
    if($desktopExit -ne 0){ Die "The new client failed desktop initialization: $desktopSmoke" }
    if($desktopSmoke -notmatch "RedBeacon desktop smoke ok"){
      Die "The new client did not reach the desktop-ready marker."
    }

    $note = Join-Path $verifyRoot "note.md"
    $noteBody = "---`ntitle: Install Verification`nemoji: test`n---`n`n# Runtime verification`n`nThis card verifies the packaged renderer and exact browser revision."
    [System.IO.File]::WriteAllText($note, $noteBody, [System.Text.UTF8Encoding]::new($false))
    $renderText = ((& $RendererPath $note --output-dir $cards --style default 2>&1) | Out-String)
    $renderExit = $LASTEXITCODE
    if($renderExit -ne 0){ Die "The new client failed its offline card-render verification: $renderText" }
    if(-not (Test-Path (Join-Path $cards "cover.png"))){ Die "The new renderer did not create a cover image." }
    if(-not (Get-ChildItem -Path $cards -Filter "card_*.png" -File -ErrorAction SilentlyContinue)){
      Die "The new renderer did not create a body card image."
    }
  }
  finally {
    Pop-RuntimeEnvironment $runtimeEnv
    Remove-Item -Recurse -Force $verifyRoot -ErrorAction SilentlyContinue
  }
  Say "New client runtime verification passed."
}

$OSS = if($env:REDBEACON_OSS){ $env:REDBEACON_OSS } else { "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com" }
$Channel = if($env:REDBEACON_CHANNEL){ $env:REDBEACON_CHANNEL.ToLowerInvariant() } else { "stable" }
if(@("test", "testing", "beta") -contains $Channel){ $Channel = "test" } else { $Channel = "stable" }
if($Channel -eq "test"){
  $AppName = "RedBeacon_test"
  $CmdName = "redbeacon-test"
  $CliName = "redbeacon-test-cli"
  $AppPrefix = "app/test"
  $ManifestName = "latest-test.json"
  $SkillPrefix = "skill-test"
  $DefaultSkillDest = "$HOME\.claude\commands-redbeacon-test"
  $RuntimeRoot = "$HOME\.redbeacon_test"
} else {
  $AppName = "RedBeacon"
  $CmdName = "redbeacon"
  $CliName = "redbeacon-cli"
  $AppPrefix = "app"
  $ManifestName = "latest.json"
  $SkillPrefix = "skill"
  $DefaultSkillDest = "$HOME\.claude\commands"
  $RuntimeRoot = "$HOME\.redbeacon"
}
$SkillDest = if($env:REDBEACON_SKILL_DIR){ $env:REDBEACON_SKILL_DIR } else { $DefaultSkillDest }
$RuntimeDataDir = Join-Path $RuntimeRoot "data"
$RuntimePlaywrightDir = Join-Path $RuntimeRoot "browser\ms-playwright"
$RuntimeCloakDir = Join-Path $RuntimeRoot "browser\cloakbrowser"
$Plat = "win-x64"
$LegacyUrl = "$OSS/$AppPrefix/$AppName-$Plat.zip"
$Url  = $LegacyUrl # fallback for manifests published before versioned packages
$SkillUrl = "$OSS/$SkillPrefix/redbeacon-skill.tar.gz"
$SkillSha = ""
$SkillVersion = ""
$Dest = "$env:LOCALAPPDATA\Programs\$AppName"
$BinDir = "$HOME\.local\bin"
$cliExe = Join-Path $Dest "$CliName.exe"
$tmp = New-Item -ItemType Directory -Force -Path (Join-Path $env:TEMP ("rb_" + [guid]::NewGuid()))

try {
  # 1) Fast no-op for repeat installs: fetch only the tiny manifest, then skip
  # the large bundle when the installed client is already current.
  $latest = ""
  $sha = ""
  try {
    $manifest = Invoke-RestMethod -Uri "$OSS/$ManifestName" -UseBasicParsing -TimeoutSec 20
    $latest = [string]$manifest.version
    if($manifest.app_sha256){
      $prop = $manifest.app_sha256.PSObject.Properties[$Plat]
      if($prop){ $sha = ([string]$prop.Value).ToLowerInvariant() }
    }
    if($manifest.skill_bundle_url){ $SkillUrl = [string]$manifest.skill_bundle_url }
    if($manifest.skill_sha256){ $SkillSha = ([string]$manifest.skill_sha256).ToLowerInvariant() }
    if($manifest.skill_version){ $SkillVersion = [string]$manifest.skill_version }
  } catch {}
  if($latest -and $manifest.app){ $Url = "$OSS/$AppPrefix/releases/$latest/$AppName-$Plat.zip" }
  $current = ""
  if(Test-Path $cliExe){
    try { $current = ((& $cliExe --version 2>$null) -split "\s+")[-1] } catch {}
  }
  if(-not $env:REDBEACON_FORCE_INSTALL -and $latest -and $current -eq $latest){
    Prepare-Skills $tmp
    $installedRenderer = Join-Path $Dest "RedBeaconRenderer.exe"
    $healthy = $true
    try {
      Run-BrowserSetup $cliExe
      Verify-Bundle $cliExe $installedRenderer $latest
    } catch {
      Warn "The installed copy reports the latest version but failed health verification; downloading a clean bundle."
      $healthy = $false
    }
    if($healthy){
      Say "$AppName $current is already installed and healthy. Skipping bundle download."
      # Re-running the installer repairs missing/outdated skills without pulling
      # the large desktop bundle again.
      Install-Skills $cliExe $tmp
      Commit-Skills
      Say "To reinstall anyway: `$env:REDBEACON_CHANNEL='$Channel'; `$env:REDBEACON_FORCE_INSTALL=1; irm $OSS/install.ps1 | iex"
      return
    }
  }

  # 2) download the bundle (OSS is fast in China; retry a few times)
  Say "[1/4] Downloading $AppName ($Plat) ..."
  $zip = Join-Path $tmp "rb.zip"; $ok = $false
  foreach($t in 1..3){
    try { Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing -TimeoutSec 600; $ok = $true; break }
    catch { Warn "  download attempt $t failed, retrying..."; Start-Sleep -Seconds 2 }
  }
  if(-not $ok -and $Url -ne $LegacyUrl){
    Warn "  versioned package unavailable; trying the compatible package URL..."
    foreach($t in 1..3){
      try { Invoke-WebRequest -Uri $LegacyUrl -OutFile $zip -UseBasicParsing -TimeoutSec 600; $ok = $true; $Url = $LegacyUrl; break }
      catch { Warn "  compatible download attempt $t failed, retrying..."; Start-Sleep -Seconds 2 }
    }
  }
  if(-not $ok){ Die "Could not download $Url -- check your network and re-run." }
  if($sha){
    $got = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLowerInvariant()
    if($got -ne $sha){ Die "Package checksum mismatch. Please re-run later." }
  } else {
    Warn "  package checksum missing in $ManifestName; installing without checksum verification."
  }

  # 3) extract + place + wire the `redbeacon` command
  Say "[2/4] Installing ..."
  $ex = Join-Path $tmp "x"
  Expand-Archive -Path $zip -DestinationPath $ex -Force
  $stagedRoot = Join-Path $ex $AppName
  $stagedCli = Join-Path $stagedRoot "$CliName.exe"
  $stagedRenderer = Join-Path $stagedRoot "RedBeaconRenderer.exe"
  if(-not (Test-Path $stagedRoot)){ Die "Downloaded bundle does not contain $AppName." }
  if(-not (Test-Path $stagedCli)){ Die "Downloaded bundle does not contain $CliName.exe." }

  # Prepare every version-coupled runtime with the NEW CLI before touching the
  # existing installation. A failed dependency or skill download leaves the old
  # client intact and usable.
  Say "[2/4] Preparing and verifying new-version dependencies before replacement ..."
  Run-BrowserSetup $stagedCli
  Verify-Bundle $stagedCli $stagedRenderer $latest
  Prepare-Skills $tmp
  Stop-RunningRedBeacon
  $backup = "$Dest.redbeacon-rollback"
  Remove-Item -Recurse -Force $backup -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
  $placed = $false
  $hadExisting = Test-Path $Dest
  try {
    if(Test-Path $Dest){ Move-Item $Dest $backup }
    Move-Item $stagedRoot $Dest
    $placed = $true

    # Verify the placed bundle sees the exact runtimes prepared by staged CLI.
    Run-BrowserSetup $cliExe

    # 6) skills -> AI assistant command dir (prepared before replacement)
    Install-Skills $cliExe $tmp

    # Verify the complete final-path installation after app, dependencies and
    # skills have all switched. Any failure below restores every old piece.
    Verify-Bundle $cliExe (Join-Path $Dest "RedBeaconRenderer.exe") $latest

    # User-visible launchers are the final commit point.
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    Set-Content -Path (Join-Path $BinDir "$CmdName.cmd") -Encoding ASCII -Value @("@echo off", "`"$cliExe`" %*")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if($userPath -notlike "*$BinDir*"){
      [Environment]::SetEnvironmentVariable("Path", "$BinDir;$userPath", "User")
      $env:Path = "$BinDir;$env:Path"
    }

    $guiExe = Join-Path $Dest "$AppName.exe"
    $iconFile = Join-Path $Dest "_internal\assets\RedBeacon.ico"
    if(-not (Test-Path $iconFile)){ $iconFile = $guiExe }
    $sh = New-Object -ComObject WScript.Shell
    foreach($d in @([Environment]::GetFolderPath("Desktop"),
                    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))){
      $lnk = $sh.CreateShortcut((Join-Path $d "$AppName.lnk"))
      $lnk.TargetPath = $guiExe
      $lnk.WorkingDirectory = $Dest
      $lnk.IconLocation = "$iconFile,0"
      $lnk.Description = "$AppName - Xiaohongshu operations digital worker"
      $lnk.Save()
    }

    Remove-Item -Recurse -Force $backup -ErrorAction SilentlyContinue
    Commit-Skills
  }
  catch {
    Restore-Skills
    if($placed -and (Test-Path $Dest)){ Remove-Item -Recurse -Force $Dest -ErrorAction SilentlyContinue }
    if(Test-Path $backup){ Move-Item $backup $Dest -Force }
    if(-not $hadExisting){
      Remove-Item -Force (Join-Path $BinDir "$CmdName.cmd") -ErrorAction SilentlyContinue
      foreach($d in @([Environment]::GetFolderPath("Desktop"),
                      (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))){
        Remove-Item -Force (Join-Path $d "$AppName.lnk") -ErrorAction SilentlyContinue
      }
    }
    throw
  }

  Write-Host ""
  Say "$AppName installed."
  Write-Host "  - Double-click:  Desktop / Start Menu -> $AppName"
  Write-Host "  - Or via CLI:    $CmdName   (open a NEW terminal first so PATH refreshes)"
  Write-Host "  (The browser engine was prepared during install.)"
}
finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
