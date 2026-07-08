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
$Channel = if($env:REDBEACON_CHANNEL){ $env:REDBEACON_CHANNEL.ToLowerInvariant() } else { "stable" }
if(@("test", "testing", "beta") -contains $Channel){ $Channel = "test" } else { $Channel = "stable" }
if($Channel -eq "test"){
  $AppName = "RedBeacon_test"
  $CmdName = "redbeacon-test"
  $CliName = "redbeacon-test-cli"
  $DataHome = "$HOME\.redbeacon_test"
  $TokenHome = "$HOME\.bytestaff_test"
  $DefaultSkillDest = "$HOME\.claude\commands-redbeacon-test"
  $CodexSkillDir = "$HOME\.codex\skills-redbeacon-test"
} else {
  $AppName = "RedBeacon"
  $CmdName = "redbeacon"
  $CliName = "redbeacon-cli"
  $DataHome = "$HOME\.redbeacon"
  $TokenHome = "$HOME\.bytestaff"
  $DefaultSkillDest = "$HOME\.claude\commands"
  $CodexSkillDir = "$HOME\.codex\skills"
}
$Dest = "$env:LOCALAPPDATA\Programs\$AppName"
$BinDir = "$HOME\.local\bin"
$SkillDest = if($env:REDBEACON_SKILL_DIR){ $env:REDBEACON_SKILL_DIR } else { $DefaultSkillDest }

Say "Stopping $AppName..."
foreach($name in @($AppName, $CliName)){
  Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

Say "Removing $AppName app and CLI..."
Remove-Item -Recurse -Force $Dest -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$Dest.previous-update" -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $BinDir "$CmdName.cmd") -ErrorAction SilentlyContinue
if($Channel -eq "stable"){
  Remove-Item -Force (Join-Path $BinDir "redbeacon-app.cmd") -ErrorAction SilentlyContinue
}

Say "Removing update staging files..."
Remove-Item -Recurse -Force "$DataHome\data\updates" -ErrorAction SilentlyContinue
if($env:REDBEACON_UPDATE_WORKDIR){
  Remove-Item -Recurse -Force $env:REDBEACON_UPDATE_WORKDIR -ErrorAction SilentlyContinue
}

# Legacy uv-tool install leftovers (kept for users who installed older builds).
$uv = Get-Command uv -ErrorAction SilentlyContinue
if($Channel -eq "stable" -and $uv){
  try { & $uv.Source tool uninstall redbeacon | Out-Null } catch {}
}
if($Channel -eq "stable"){
  Remove-Item -Recurse -Force "$HOME\.local\share\uv\tools\redbeacon" -ErrorAction SilentlyContinue
}

Say "Removing shortcuts..."
$shortcutDirs = @(
  [Environment]::GetFolderPath("Desktop"),
  (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs")
)
foreach($d in $shortcutDirs){
  Remove-Item -Force (Join-Path $d "$AppName.lnk") -ErrorAction SilentlyContinue
}

Say "Removing skills..."
Remove-Item -Force (Join-Path $SkillDest "redbeacon*.md") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$CodexSkillDir\redbeacon*" -ErrorAction SilentlyContinue

Say "Removing browser engine cache..."
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\ms-playwright" -ErrorAction SilentlyContinue

if($Purge){
  Say "PURGE: removing your $AppName data ($DataHome, $TokenHome)..."
  Remove-Item -Recurse -Force $DataHome -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $TokenHome -ErrorAction SilentlyContinue
} else {
  Warn "Kept your data: $DataHome (accounts/content) + $TokenHome (login)."
  Warn "To wipe it too: `$env:REDBEACON_CHANNEL='$Channel'; `$env:REDBEACON_PURGE=1; irm https://bytestaff.jiomig.com/uninstall.ps1 | iex"
}

Say "$AppName uninstalled."
