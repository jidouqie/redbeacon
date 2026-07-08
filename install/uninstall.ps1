# ------------------------------------------------------------------------------
# RedBeacon uninstaller (Windows). Run in PowerShell:
#     irm https://bytestaff.jiomig.com/uninstall.ps1 | iex
#
# Removes the software bundle, update leftovers, CLI shim, shortcuts, skills,
# and browser cache.
# Your BUSINESS DATA is KEPT by default:
#     ~/.redbeacon   (accounts / cookies / generated content / local DB)
#     ~/.bytestaff   (platform login / device token)
# To also wipe that data, run:
#     $env:REDBEACON_PURGE=1; irm https://bytestaff.jiomig.com/uninstall.ps1 | iex
# All output is ASCII-only on purpose (avoids garbled text / iex decode issues).
# ------------------------------------------------------------------------------
$ErrorActionPreference = "Continue"
function Say($m){ Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "!! $m" -ForegroundColor Yellow }

$Purge = $env:REDBEACON_PURGE
$Dest = "$env:LOCALAPPDATA\Programs\RedBeacon"
$BinDir = "$HOME\.local\bin"
$SkillDest = if($env:REDBEACON_SKILL_DIR){ $env:REDBEACON_SKILL_DIR } else { "$HOME\.claude\commands" }

Say "Stopping RedBeacon..."
foreach($name in @("RedBeacon", "redbeacon-cli")){
  Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

Say "Removing RedBeacon app and CLI..."
Remove-Item -Recurse -Force $Dest -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$Dest.previous-update" -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $BinDir "redbeacon.cmd") -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $BinDir "redbeacon-app.cmd") -ErrorAction SilentlyContinue

Say "Removing update staging files..."
Remove-Item -Recurse -Force "$HOME\.redbeacon\data\updates" -ErrorAction SilentlyContinue
if($env:REDBEACON_UPDATE_WORKDIR){
  Remove-Item -Recurse -Force $env:REDBEACON_UPDATE_WORKDIR -ErrorAction SilentlyContinue
}

# Legacy uv-tool install leftovers (kept for users who installed older builds).
$uv = Get-Command uv -ErrorAction SilentlyContinue
if($uv){
  try { & $uv.Source tool uninstall redbeacon | Out-Null } catch {}
}
Remove-Item -Recurse -Force "$HOME\.local\share\uv\tools\redbeacon" -ErrorAction SilentlyContinue

Say "Removing shortcuts..."
$shortcutDirs = @(
  [Environment]::GetFolderPath("Desktop"),
  (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs")
)
foreach($d in $shortcutDirs){
  Remove-Item -Force (Join-Path $d "RedBeacon.lnk") -ErrorAction SilentlyContinue
}

Say "Removing skills..."
Remove-Item -Force (Join-Path $SkillDest "redbeacon*.md") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$HOME\.codex\skills\redbeacon*" -ErrorAction SilentlyContinue

Say "Removing browser engine cache..."
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\ms-playwright" -ErrorAction SilentlyContinue

if($Purge){
  Say "PURGE: removing your RedBeacon data (~/.redbeacon, ~/.bytestaff)..."
  Remove-Item -Recurse -Force "$HOME\.redbeacon" -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force "$HOME\.bytestaff" -ErrorAction SilentlyContinue
} else {
  Warn "Kept your data: ~/.redbeacon (accounts/content) + ~/.bytestaff (login)."
  Warn 'To wipe it too: $env:REDBEACON_PURGE=1; irm https://bytestaff.jiomig.com/uninstall.ps1 | iex'
}

Say "RedBeacon uninstalled."
