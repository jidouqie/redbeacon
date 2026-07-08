# ------------------------------------------------------------------------------
# RedBeacon installer (Windows). Run in PowerShell:
#     irm https://bytestaff.jiomig.com/install.ps1 | iex
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

$OSS = if($env:REDBEACON_OSS){ $env:REDBEACON_OSS } else { "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com" }
$SkillDest = if($env:REDBEACON_SKILL_DIR){ $env:REDBEACON_SKILL_DIR } else { "$HOME\.claude\commands" }
$Plat = "win-x64"
$Url  = "$OSS/app/RedBeacon-$Plat.zip"
$Dest = "$env:LOCALAPPDATA\Programs\RedBeacon"
$BinDir = "$HOME\.local\bin"
$cliExe = Join-Path $Dest "redbeacon-cli.exe"
$tmp = New-Item -ItemType Directory -Force -Path (Join-Path $env:TEMP ("rb_" + [guid]::NewGuid()))

try {
  # 1) Fast no-op for repeat installs: fetch only the tiny manifest, then skip
  # the large bundle when the installed client is already current.
  $latest = ""
  try {
    $manifest = Invoke-RestMethod -Uri "$OSS/latest.json" -UseBasicParsing -TimeoutSec 20
    $latest = [string]$manifest.version
  } catch {}
  $current = ""
  if(Test-Path $cliExe){
    try { $current = ((& $cliExe --version 2>$null) -split "\s+")[-1] } catch {}
  }
  if(-not $env:REDBEACON_FORCE_INSTALL -and $latest -and $current -eq $latest){
    Say "RedBeacon $current is already installed. Skipping bundle download."
    Say 'To reinstall anyway: $env:REDBEACON_FORCE_INSTALL=1; irm https://bytestaff.jiomig.com/install.ps1 | iex'
    return
  }

  # 2) download the bundle (OSS is fast in China; retry a few times)
  Say "[1/3] Downloading RedBeacon ($Plat) ..."
  $zip = Join-Path $tmp "rb.zip"; $ok = $false
  foreach($t in 1..3){
    try { Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing -TimeoutSec 600; $ok = $true; break }
    catch { Warn "  download attempt $t failed, retrying..."; Start-Sleep -Seconds 2 }
  }
  if(-not $ok){ Die "Could not download $Url -- check your network and re-run." }

  # 3) extract + place + wire the `redbeacon` command
  Say "[2/3] Installing ..."
  $ex = Join-Path $tmp "x"
  Expand-Archive -Path $zip -DestinationPath $ex -Force
  if(Test-Path $Dest){ Remove-Item -Recurse -Force $Dest }
  New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
  Move-Item (Join-Path $ex "RedBeacon") $Dest

  # `redbeacon` command = a .cmd shim on PATH that calls the bundled redbeacon-cli.exe
  New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
  Set-Content -Path (Join-Path $BinDir "redbeacon.cmd") -Encoding ASCII -Value @("@echo off", "`"$cliExe`" %*")
  # add ~/.local/bin to the user PATH if it isn't there yet
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if($userPath -notlike "*$BinDir*"){
    [Environment]::SetEnvironmentVariable("Path", "$BinDir;$userPath", "User")
    $env:Path = "$BinDir;$env:Path"
  }

  # 4) desktop + start-menu shortcuts -> the windowed RedBeacon.exe
  $guiExe = Join-Path $Dest "RedBeacon.exe"
  $iconFile = Join-Path $Dest "_internal\assets\RedBeacon.ico"
  if(-not (Test-Path $iconFile)){ $iconFile = $guiExe }
  $sh = New-Object -ComObject WScript.Shell
  foreach($d in @([Environment]::GetFolderPath("Desktop"),
                  (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))){
    $lnk = $sh.CreateShortcut((Join-Path $d "RedBeacon.lnk"))
    $lnk.TargetPath = $guiExe
    $lnk.WorkingDirectory = $Dest
    $lnk.IconLocation = "$iconFile,0"
    $lnk.Description = "RedBeacon - Xiaohongshu operations digital worker"
    $lnk.Save()
  }

  # 5) skills -> AI assistant command dir (from OSS; non-blocking)
  Say "[3/3] Fetching skills ..."
  $skok = $false
  foreach($t in 1..3){
    try {
      $star = Join-Path $tmp "skill.tar.gz"
      Invoke-WebRequest -Uri "$OSS/skill/redbeacon-skill.tar.gz" -OutFile $star -UseBasicParsing -TimeoutSec 90
      tar -xzf $star -C $tmp
      $skok = $true; break
    } catch { Warn "  skills fetch failed, retrying..." }
  }
  if($skok){
    $src = Get-ChildItem -Path $tmp -Recurse -Directory | Where-Object { $_.FullName -match "\.claude[\\/]commands$" } | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $SkillDest | Out-Null
    if($src){ Copy-Item -Force (Join-Path $src.FullName "*.md") $SkillDest }
    try { & $cliExe config set skill_install_dir $SkillDest | Out-Null } catch {}
  } else { Warn "  skills not fetched this time (app unaffected); re-run this command later to add them." }

  Write-Host ""
  Say "RedBeacon installed."
  Write-Host "  - Double-click:  Desktop / Start Menu -> RedBeacon"
  Write-Host "  - Or via CLI:    redbeacon   (open a NEW terminal first so PATH refreshes; with an AI assistant: /redbeacon)"
  Write-Host "  (The browser engine downloads on first run -- give it a minute the first time.)"
}
finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
