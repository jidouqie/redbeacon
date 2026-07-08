# ------------------------------------------------------------------------------
# RedBeacon installer (Windows). Run in PowerShell:
#     irm https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install.ps1 | iex
#
# Installs a SELF-CONTAINED bundle (Python + all deps + Playwright driver already
# inside). No uv / no pip / no compiling -- just download + unzip + place.
# Gives you both a double-click desktop app AND the `redbeacon` command.
# The browser engine (Chromium) downloads on first run via a China mirror.
# All output is ASCII-only on purpose (avoids garbled text / iex decode issues).
# ------------------------------------------------------------------------------
$ErrorActionPreference = "Stop"
function Say($m){ Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "!! $m" -ForegroundColor Yellow }
function Die($m){ Write-Host "xx $m" -ForegroundColor Red; exit 1 }
function Write-CodexSkills($SrcDir){
  if(-not $SrcDir){ return }
  $codexDir = Join-Path $HOME ".codex\skills"
  try { New-Item -ItemType Directory -Force -Path $codexDir | Out-Null } catch { return }
  Get-ChildItem -Path $SrcDir -Filter "redbeacon*.md" -ErrorAction SilentlyContinue | ForEach-Object {
    $stem = $_.BaseName
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
    [System.IO.File]::WriteAllText((Join-Path $folder "SKILL.md"), $skill, [System.Text.UTF8Encoding]::new($false))
  }
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
} else {
  $AppName = "RedBeacon"
  $CmdName = "redbeacon"
  $CliName = "redbeacon-cli"
  $AppPrefix = "app"
  $ManifestName = "latest.json"
  $SkillPrefix = "skill"
  $DefaultSkillDest = "$HOME\.claude\commands"
}
$SkillDest = if($env:REDBEACON_SKILL_DIR){ $env:REDBEACON_SKILL_DIR } else { $DefaultSkillDest }
$Plat = "win-x64"
$Url  = "$OSS/$AppPrefix/$AppName-$Plat.zip"
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
  } catch {}
  $current = ""
  if(Test-Path $cliExe){
    try { $current = ((& $cliExe --version 2>$null) -split "\s+")[-1] } catch {}
  }
  if(-not $env:REDBEACON_FORCE_INSTALL -and $latest -and $current -eq $latest){
    Say "$AppName $current is already installed. Skipping bundle download."
    Say "To reinstall anyway: `$env:REDBEACON_CHANNEL='$Channel'; `$env:REDBEACON_FORCE_INSTALL=1; irm $OSS/install.ps1 | iex"
    return
  }

  # 2) download the bundle (OSS is fast in China; retry a few times)
  Say "[1/3] Downloading $AppName ($Plat) ..."
  $zip = Join-Path $tmp "rb.zip"; $ok = $false
  foreach($t in 1..3){
    try { Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing -TimeoutSec 600; $ok = $true; break }
    catch { Warn "  download attempt $t failed, retrying..."; Start-Sleep -Seconds 2 }
  }
  if(-not $ok){ Die "Could not download $Url -- check your network and re-run." }
  if($sha){
    $got = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLowerInvariant()
    if($got -ne $sha){ Die "Package checksum mismatch. Please re-run later." }
  } else {
    Warn "  package checksum missing in $ManifestName; installing without checksum verification."
  }

  # 3) extract + place + wire the `redbeacon` command
  Say "[2/3] Installing ..."
  $ex = Join-Path $tmp "x"
  Expand-Archive -Path $zip -DestinationPath $ex -Force
  if(Test-Path $Dest){ Remove-Item -Recurse -Force $Dest }
  New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
  Move-Item (Join-Path $ex $AppName) $Dest

  # command shim on PATH calls the bundled console exe.
  New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
  Set-Content -Path (Join-Path $BinDir "$CmdName.cmd") -Encoding ASCII -Value @("@echo off", "`"$cliExe`" %*")
  # add ~/.local/bin to the user PATH if it isn't there yet
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if($userPath -notlike "*$BinDir*"){
    [Environment]::SetEnvironmentVariable("Path", "$BinDir;$userPath", "User")
    $env:Path = "$BinDir;$env:Path"
  }

  # 4) desktop + start-menu shortcuts -> the windowed RedBeacon.exe
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

  # 5) skills -> AI assistant command dir (from OSS; non-blocking)
  Say "[3/3] Fetching skills ..."
  $skok = $false
  foreach($t in 1..3){
    try {
      $star = Join-Path $tmp "skill.tar.gz"
      Invoke-WebRequest -Uri "$OSS/$SkillPrefix/redbeacon-skill.tar.gz" -OutFile $star -UseBasicParsing -TimeoutSec 90
      tar -xzf $star -C $tmp
      $skok = $true; break
    } catch { Warn "  skills fetch failed, retrying..." }
  }
  if($skok){
    $src = Get-ChildItem -Path $tmp -Recurse -Directory | Where-Object { $_.FullName -match "\.claude[\\/]commands$" } | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $SkillDest | Out-Null
    if($src){ Copy-Item -Force (Join-Path $src.FullName "*.md") $SkillDest }
    if($src){ Write-CodexSkills $src.FullName }
    try { & $cliExe config set skill_install_dir $SkillDest | Out-Null } catch {}
  } else { Warn "  skills not fetched this time (app unaffected); re-run this command later to add them." }

  Write-Host ""
  Say "$AppName installed."
  Write-Host "  - Double-click:  Desktop / Start Menu -> $AppName"
  Write-Host "  - Or via CLI:    $CmdName   (open a NEW terminal first so PATH refreshes)"
  Write-Host "  (The browser engine downloads on first run -- give it a minute the first time.)"
}
finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
