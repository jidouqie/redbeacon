# ------------------------------------------------------------------------------
# RedBeacon installer (Windows). Run in PowerShell:
#     Fetch the current installer URL from the central RedBeacon manifest.
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
function Start-InstalledApp([string]$GuiPath, [string]$WorkingDirectory){
  if($env:REDBEACON_INSTALLER_TEST_MODE -eq "1" -or $env:REDBEACON_SKIP_APP_LAUNCH -eq "1"){ return }
  if(-not (Test-Path -LiteralPath $GuiPath)){
    Warn "$AppName installed successfully, but the desktop executable was not found for automatic launch."
    return
  }
  try {
    Start-Process -FilePath $GuiPath -WorkingDirectory $WorkingDirectory | Out-Null
    Say "$AppName is starting."
  }
  catch {
    Warn "$AppName installed successfully, but automatic launch failed. Open it from the Desktop or Start Menu."
  }
}
function Test-LocalInstallerTestUrl([Uri]$Uri){
  return ($env:REDBEACON_INSTALLER_TEST_MODE -eq "1" -and
          $Uri.Scheme -eq "http" -and $Uri.Host -eq "127.0.0.1")
}
function Assert-ReleaseUrl([string]$Url, [string]$Label){
  try { $uri = [Uri]$Url } catch { Die "$Label URL is invalid." }
  $safeHttps = ($uri.Scheme -eq "https" -and -not $uri.UserInfo -and -not $uri.Query -and -not $uri.Fragment)
  if(-not $safeHttps -and -not (Test-LocalInstallerTestUrl $uri)){ Die "$Label URL is unsafe." }
  return $uri
}
function Get-ReleaseArtifact($Manifest, [string]$Path){
  if(-not $Manifest -or -not $Manifest.artifacts){ Die "Release manifest has no artifacts." }
  $matches = @($Manifest.artifacts | Where-Object { ([string]$_.path) -eq $Path })
  if($matches.Count -ne 1){ Die "Release manifest does not contain exactly one $Path artifact." }
  $artifact = $matches[0]
  $size = [Int64]$artifact.size
  $hash = ([string]$artifact.sha256).ToLowerInvariant()
  $ossUrl = [string]$artifact.url
  if($size -le 0 -or $hash -notmatch '^[0-9a-f]{64}$'){ Die "Artifact metadata is invalid: $Path" }
  Assert-ReleaseUrl $ossUrl "Artifact $Path" | Out-Null
  return $artifact
}
function Test-ArtifactFile([string]$Path, $Artifact){
  if(-not (Test-Path -LiteralPath $Path)){ return $false }
  if((Get-Item -LiteralPath $Path).Length -ne [Int64]$Artifact.size){ return $false }
  return ((Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() -eq ([string]$Artifact.sha256).ToLowerInvariant())
}
function Download-NodeArtifact([string]$Url, [string]$OutFile, $Artifact){
  $request = [System.Net.HttpWebRequest]::Create([Uri]$Url)
  $request.Method = "GET"
  $request.AllowAutoRedirect = $false
  $request.Timeout = 3000
  $request.ReadWriteTimeout = 8000
  $request.AddRange(0)
  $response = $null
  $input = $null
  $output = $null
  try {
    $response = [System.Net.HttpWebResponse]$request.GetResponse()
    if([int]$response.StatusCode -ne 206){ throw "node returned HTTP $([int]$response.StatusCode)" }
    $expectedRange = "bytes 0-$([Int64]$Artifact.size - 1)/$([Int64]$Artifact.size)"
    if(([string]$response.Headers["Content-Range"]).ToLowerInvariant() -ne $expectedRange){ throw "node returned invalid Content-Range" }
    $input = $response.GetResponseStream()
    if($input.CanTimeout){ $input.ReadTimeout = 8000 }
    $output = [System.IO.File]::Open($OutFile, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $buffer = New-Object byte[] (512 * 1024)
    $total = [Int64]0
    $first = $true
    while(($read = $input.Read($buffer, 0, $buffer.Length)) -gt 0){
      if($first -and $input.CanTimeout){ $input.ReadTimeout = 15000; $first = $false }
      $total += $read
      if($total -gt [Int64]$Artifact.size){ throw "node returned too many bytes" }
      $output.Write($buffer, 0, $read)
      $pct = [Math]::Min(100, [int](100 * $total / [Int64]$Artifact.size))
      Write-Progress -Activity "Downloading RedBeacon" -Status "$pct% from download node" -PercentComplete $pct
    }
  }
  finally {
    if($output){ $output.Dispose() }
    if($input){ $input.Dispose() }
    if($response){ $response.Dispose() }
    Write-Progress -Activity "Downloading RedBeacon" -Completed
  }
  if(-not (Test-ArtifactFile $OutFile $Artifact)){ throw "node artifact checksum mismatch" }
}
function Download-ReleaseArtifact($Artifact, [string]$OutFile){
  Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
  $ossUrl = [string]$Artifact.url
  $candidates = @()
  if($Artifact.download_urls){
    foreach($candidate in @($Artifact.download_urls)){
      $value = [string]$candidate
      if($value -and $candidates -notcontains $value){ $candidates += $value }
    }
  }
  if($candidates -notcontains $ossUrl){ $candidates += $ossUrl }
  $nodeUrl = @($candidates | Where-Object { $_ -ne $ossUrl } | Select-Object -First 1)
  if($nodeUrl.Count -eq 1){
    try {
      Assert-ReleaseUrl $nodeUrl[0] "Download node" | Out-Null
      Download-NodeArtifact $nodeUrl[0] $OutFile $Artifact
      return "node"
    }
    catch {
      Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
      Warn "  download node unavailable; switching to central OSS"
    }
  }
  foreach($attempt in 1..3){
    try {
      Invoke-WebRequest -Uri $ossUrl -OutFile $OutFile -UseBasicParsing -TimeoutSec 600
      if(-not (Test-ArtifactFile $OutFile $Artifact)){ throw "central OSS artifact checksum mismatch" }
      return "oss"
    }
    catch {
      Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
      if($attempt -lt 3){ Warn "  central OSS attempt $attempt failed, retrying..."; Start-Sleep -Seconds 2 }
    }
  }
  Die "Could not download $([string]$Artifact.path) from the download node or central OSS."
}
function Test-ManagedSkillName([string]$Stem){
  if($Channel -eq "test"){ return $Stem.StartsWith("redbeacon-test") }
  return $Stem.StartsWith("redbeacon") -and -not $Stem.StartsWith("redbeacon-test")
}
function Get-AssistantSkillRoots(){
  return @(
    [pscustomobject]@{ Name = "codex"; Path = if($env:REDBEACON_CODEX_SKILL_DIR){ $env:REDBEACON_CODEX_SKILL_DIR } else { Join-Path $HOME ".codex\skills" } },
    [pscustomobject]@{ Name = "openclaw"; Path = if($env:REDBEACON_OPENCLAW_SKILL_DIR){ $env:REDBEACON_OPENCLAW_SKILL_DIR } else { Join-Path $HOME ".openclaw\skills" } },
    [pscustomobject]@{ Name = "hermes"; Path = if($env:REDBEACON_HERMES_SKILL_DIR){ $env:REDBEACON_HERMES_SKILL_DIR } else { Join-Path $HOME ".hermes\skills" } },
    [pscustomobject]@{ Name = "workbuddy"; Path = if($env:REDBEACON_WORKBUDDY_SKILL_DIR){ $env:REDBEACON_WORKBUDDY_SKILL_DIR } else { Join-Path $HOME ".workbuddy\skills" } }
  )
}
function Install-PortableSkills($SrcDir){
  if(-not $SrcDir){ return }
  $sourceFolders = @(Get-ChildItem -Path $SrcDir -Filter "redbeacon*" -Directory -ErrorAction SilentlyContinue |
    Where-Object { (Test-ManagedSkillName $_.Name) -and (Test-Path (Join-Path $_.FullName "SKILL.md")) })
  foreach($assistant in Get-AssistantSkillRoots){
    New-Item -ItemType Directory -Force -Path $assistant.Path | Out-Null
    foreach($folder in $sourceFolders){
      Copy-Item -Path $folder.FullName -Destination $assistant.Path -Recurse -Force
    }
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
  $oldManifestFile = $env:REDBEACON_INSTALL_MANIFEST_FILE
  $runtimeEnv = Push-RuntimeEnvironment
  $env:REDBEACON_OUT = "compact"
  if($script:ReleaseManifestFile){ $env:REDBEACON_INSTALL_MANIFEST_FILE = $script:ReleaseManifestFile }
  try {
    & $CliPath setup
    if($LASTEXITCODE -ne 0){ Die "Browser engine setup failed. Re-run the installer after checking network/proxy." }
  } finally {
    if($null -eq $oldOut){ Remove-Item Env:\REDBEACON_OUT -ErrorAction SilentlyContinue } else { $env:REDBEACON_OUT = $oldOut }
    if($null -eq $oldManifestFile){ Remove-Item Env:\REDBEACON_INSTALL_MANIFEST_FILE -ErrorAction SilentlyContinue } else { $env:REDBEACON_INSTALL_MANIFEST_FILE = $oldManifestFile }
    Pop-RuntimeEnvironment $runtimeEnv
  }
  Say "Browser engine is ready."
}
$script:PreparedSkillSrc = $null
$script:PreparedPortableSkillSrc = $null
function Prepare-Skills($TempDir){
  Say "Preparing the matching skill bundle ..."
  $skok = $false
  $skillStage = Join-Path $TempDir "skill-stage"
  Remove-Item -Recurse -Force $skillStage -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $skillStage | Out-Null
  foreach($t in 1..3){
    try {
      $star = Join-Path $TempDir "skill.tar.gz"
      Download-ReleaseArtifact $SkillArtifact $star | Out-Null
      Remove-Item -Recurse -Force $skillStage -ErrorAction SilentlyContinue
      New-Item -ItemType Directory -Force -Path $skillStage | Out-Null
      tar -xzf $star -C $skillStage
      if($LASTEXITCODE -ne 0){ throw "skill archive extraction failed" }
      $skok = $true; break
    } catch { Warn "  skills fetch failed, retrying..." }
  }
  if(-not $skok){ Die "Could not prepare the matching skill bundle. The existing installation was not changed." }
  $src = Get-ChildItem -Path $skillStage -Recurse -Directory | Where-Object { $_.FullName -match "\.claude[\\/]commands$" } | Select-Object -First 1
  $portable = Get-ChildItem -Path $skillStage -Recurse -Directory | Where-Object { $_.Name -eq "agent-skills" } | Select-Object -First 1
  if(-not $src){ Die "Skill bundle is incomplete. The existing installation was not changed." }
  if(-not $portable){ Die "Skill bundle has no portable Agent Skills. The existing installation was not changed." }
  if(-not (Get-ChildItem -Path $src.FullName -Filter "redbeacon*.md" -ErrorAction SilentlyContinue)){
    Die "Skill bundle contains no RedBeacon skills. The existing installation was not changed."
  }
  if(-not (Get-ChildItem -Path $portable.FullName -Filter "redbeacon*" -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "SKILL.md") })){
    Die "Skill bundle contains no portable RedBeacon skills. The existing installation was not changed."
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
  $script:PreparedPortableSkillSrc = $portable.FullName
}
$script:SkillTransactionActive = $false
$script:SkillBackupRoot = $null
function Get-ManagedClaudeSkills(){
  if(-not (Test-Path $SkillDest)){ return @() }
  return @(Get-ChildItem -Path $SkillDest -Filter "redbeacon*.md" -File -ErrorAction SilentlyContinue |
    Where-Object { Test-ManagedSkillName $_.BaseName })
}
function Get-ManagedPortableSkills($Root){
  if(-not (Test-Path $Root)){ return @() }
  return @(Get-ChildItem -Path $Root -Filter "redbeacon*" -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-ManagedSkillName $_.Name })
}
function Remove-ManagedSkills(){
  Get-ManagedClaudeSkills | Remove-Item -Force
  foreach($assistant in Get-AssistantSkillRoots){
    Get-ManagedPortableSkills $assistant.Path | Remove-Item -Recurse -Force
  }
}
function Begin-SkillTransaction($TempDir){
  if($script:SkillTransactionActive){ return }
  $script:SkillBackupRoot = Join-Path $TempDir "skill-backup"
  Remove-Item -Recurse -Force $script:SkillBackupRoot -ErrorAction SilentlyContinue
  $claudeBackup = Join-Path $script:SkillBackupRoot "claude"
  New-Item -ItemType Directory -Force -Path $claudeBackup | Out-Null
  Get-ManagedClaudeSkills | Copy-Item -Destination $claudeBackup -Force
  foreach($assistant in Get-AssistantSkillRoots){
    $backup = Join-Path $script:SkillBackupRoot $assistant.Name
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    Get-ManagedPortableSkills $assistant.Path | Copy-Item -Destination $backup -Recurse -Force
  }
  $script:SkillTransactionActive = $true
}
function Restore-Skills(){
  if(-not $script:SkillTransactionActive){ return }
  try {
    Remove-ManagedSkills
    New-Item -ItemType Directory -Force -Path $SkillDest | Out-Null
    Get-ChildItem -Path (Join-Path $script:SkillBackupRoot "claude") -File -ErrorAction SilentlyContinue |
      Copy-Item -Destination $SkillDest -Force
    foreach($assistant in Get-AssistantSkillRoots){
      New-Item -ItemType Directory -Force -Path $assistant.Path | Out-Null
      Get-ChildItem -Path (Join-Path $script:SkillBackupRoot $assistant.Name) -Directory -ErrorAction SilentlyContinue |
        Copy-Item -Destination $assistant.Path -Recurse -Force
    }
  } catch {}
  $script:SkillTransactionActive = $false
}
function Commit-Skills(){
  $script:SkillTransactionActive = $false
  if($script:SkillBackupRoot){ Remove-Item -Recurse -Force $script:SkillBackupRoot -ErrorAction SilentlyContinue }
}
function Install-Skills($CliPath, $TempDir){
  if(-not $script:PreparedSkillSrc -or -not (Test-Path $script:PreparedSkillSrc) -or
     -not $script:PreparedPortableSkillSrc -or -not (Test-Path $script:PreparedPortableSkillSrc)){
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
  Install-PortableSkills $script:PreparedPortableSkillSrc
  $sourceSkills | ForEach-Object {
    if(-not (Test-Path (Join-Path $SkillDest $_.Name))){ Die "Claude-style skill verification failed: $($_.BaseName)" }
    $sourceHash = (Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash
    $destHash = (Get-FileHash -Algorithm SHA256 -Path (Join-Path $SkillDest $_.Name)).Hash
    if($sourceHash -ne $destHash){ Die "Claude-style skill content verification failed: $($_.BaseName)" }
    $portableSource = Join-Path $script:PreparedPortableSkillSrc "$($_.BaseName)\SKILL.md"
    if(-not (Test-Path $portableSource)){ Die "Portable skill source is missing: $($_.BaseName)" }
    $portableHash = (Get-FileHash -Algorithm SHA256 -Path $portableSource).Hash
    foreach($assistant in Get-AssistantSkillRoots){
      $target = Join-Path $assistant.Path "$($_.BaseName)\SKILL.md"
      if(-not (Test-Path $target)){ Die "$($assistant.Name) skill verification failed: $($_.BaseName)" }
      if((Get-FileHash -Algorithm SHA256 -Path $target).Hash -ne $portableHash){
        Die "$($assistant.Name) skill content verification failed: $($_.BaseName)"
      }
    }
  }
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

function Backup-BusinessDatabase(){
  $db = Join-Path $RuntimeDataDir "redbeacon.db"
  if(-not (Test-Path -LiteralPath $db)){ return }

  $backupRoot = Join-Path $RuntimeRoot "backups\pre-update"
  $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssfff") + "-$PID"
  $target = Join-Path $backupRoot $stamp
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  foreach($name in @("redbeacon.db", "redbeacon.db-wal", "redbeacon.db-shm")){
    $source = Join-Path $RuntimeDataDir $name
    if(Test-Path -LiteralPath $source){ Copy-Item -LiteralPath $source -Destination $target -Force }
  }
  [System.IO.File]::WriteAllText(
    (Join-Path $target "snapshot.txt"),
    "channel=$Channel`nversion=$latest`n",
    [System.Text.UTF8Encoding]::new($false)
  )
  @(Get-ChildItem -LiteralPath $backupRoot -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -Skip 5) |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  Say "Saved a pre-update account database snapshot: $target"
  return $target
}

function Verify-BusinessDatabaseUpgrade($CliPath, $SnapshotDir){
  if(-not $SnapshotDir){ return }
  $verifyData = Join-Path $tmp ("database-upgrade-" + [guid]::NewGuid())
  New-Item -ItemType Directory -Force -Path $verifyData | Out-Null
  foreach($name in @("redbeacon.db", "redbeacon.db-wal", "redbeacon.db-shm")){
    $source = Join-Path $SnapshotDir $name
    if(Test-Path -LiteralPath $source){ Copy-Item -LiteralPath $source -Destination $verifyData -Force }
  }
  $runtimeEnv = Push-RuntimeEnvironment
  try {
    $env:REDBEACON_DESKTOP_SMOKE = "1"
    $env:REDBEACON_DESKTOP_SMOKE_DATA_DIR = $verifyData
    $result = ((& $CliPath 2>&1) | Out-String)
    if($LASTEXITCODE -ne 0 -or $result -notmatch "RedBeacon desktop smoke ok"){
      Die "The new client cannot safely upgrade a copy of your account database: $result"
    }
  }
  finally {
    Pop-RuntimeEnvironment $runtimeEnv
    Remove-Item -Recurse -Force $verifyData -ErrorAction SilentlyContinue
  }
  Say "Account database upgrade verification passed on an isolated copy."
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
    "REDBEACON_DESKTOP_SMOKE", "REDBEACON_DESKTOP_SMOKE_DATA_DIR"
  )
  $old = @{}
  foreach($key in $keys){
    $old[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
  }
  foreach($entry in $values.GetEnumerator()){
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
  }
  foreach($key in @(
    "CLOAKBROWSER_BINARY_PATH", "CLOAKBROWSER_VERSION", "CLOAKBROWSER_SKIP_CHECKSUM",
    "REDBEACON_DESKTOP_SMOKE", "REDBEACON_DESKTOP_SMOKE_DATA_DIR"
  )){
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
    $env:REDBEACON_DESKTOP_SMOKE_DATA_DIR = Join-Path $verifyRoot "data"
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

$Channel = if($env:REDBEACON_CHANNEL){ $env:REDBEACON_CHANNEL.ToLowerInvariant() } else { "stable" }
if(@("test", "testing", "beta") -contains $Channel){ $Channel = "test" } else { $Channel = "stable" }
if($Channel -eq "test"){
  $AppName = "RedBeacon_test"
  $CmdName = "redbeacon-test"
  $CliName = "redbeacon-test-cli"
  $DefaultSkillDest = "$HOME\.claude\commands-redbeacon-test"
  $RuntimeRoot = "$HOME\.redbeacon_test"
} else {
  $AppName = "RedBeacon"
  $CmdName = "redbeacon"
  $CliName = "redbeacon-cli"
  $DefaultSkillDest = "$HOME\.claude\commands"
  $RuntimeRoot = "$HOME\.redbeacon"
}
$CentralOrigin = "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
$ManifestUrl = if($env:REDBEACON_UPDATE_URL){ $env:REDBEACON_UPDATE_URL } else { "$CentralOrigin/projects/redbeacon/$Channel/latest.json" }
$SkillDest = if($env:REDBEACON_SKILL_DIR){ $env:REDBEACON_SKILL_DIR } else { $DefaultSkillDest }
$RuntimeDataDir = Join-Path $RuntimeRoot "data"
$RuntimePlaywrightDir = Join-Path $RuntimeRoot "browser\ms-playwright"
$RuntimeCloakDir = Join-Path $RuntimeRoot "browser\cloakbrowser"
$Plat = "win-x64"
$Dest = "$env:LOCALAPPDATA\Programs\$AppName"
$BinDir = "$HOME\.local\bin"
$cliExe = Join-Path $Dest "$CliName.exe"
$tmp = New-Item -ItemType Directory -Force -Path (Join-Path $env:TEMP ("rb_" + [guid]::NewGuid()))

try {
  # 1) Fast no-op for repeat installs: fetch only the tiny manifest, then skip
  # the large bundle when the installed client is already current.
  Assert-ReleaseUrl $ManifestUrl "Release manifest" | Out-Null
  $manifest = Invoke-RestMethod -Uri $ManifestUrl -UseBasicParsing -TimeoutSec 20
  $script:ReleaseManifestFile = Join-Path $tmp "latest.json"
  $manifestJson = $manifest | ConvertTo-Json -Depth 100 -Compress
  [System.IO.File]::WriteAllText($script:ReleaseManifestFile, $manifestJson, [System.Text.UTF8Encoding]::new($false))
  if(([string]$manifest.project) -ne "redbeacon" -or ([string]$manifest.channel) -ne $Channel){
    Die "Release manifest does not match RedBeacon $Channel."
  }
  $latest = [string]$manifest.version
  if($latest -notmatch '^\d+\.\d+\.\d+$'){ Die "Release manifest has no valid version." }
  $AppArtifact = Get-ReleaseArtifact $manifest "packages/$AppName-$Plat.zip"
  $SkillArtifact = Get-ReleaseArtifact $manifest "skill/redbeacon-skill.tar.gz"
  $SkillVersion = $latest
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
      Say "To reinstall anyway, set REDBEACON_FORCE_INSTALL=1 and run the current central installer again."
      Start-InstalledApp (Join-Path $Dest "$AppName.exe") $Dest
      return
    }
  }

  # 2) download the bundle through one node attempt, then immutable OSS fallback
  Say "[1/4] Downloading $AppName ($Plat) ..."
  $zip = Join-Path $tmp "rb.zip"
  Download-ReleaseArtifact $AppArtifact $zip | Out-Null

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
  $dataBackup = Backup-BusinessDatabase
  Verify-BusinessDatabaseUpgrade $stagedCli $dataBackup
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
      New-Item -ItemType Directory -Force -Path $d | Out-Null
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
  Start-InstalledApp (Join-Path $Dest "$AppName.exe") $Dest
}
finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
