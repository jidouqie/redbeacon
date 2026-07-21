# ------------------------------------------------------------------------------
# RedBeacon uninstaller (Windows). Run in PowerShell:
#     Fetch installers/uninstall.ps1 from the current central manifest and run it.
#
# Removes the software bundle, update leftovers, CLI shim, shortcuts, skills,
# and browser cache.
# Your BUSINESS DATA is KEPT by default:
#     ~/.redbeacon   (accounts / cookies / generated content / local DB)
#     ~/.bytestaff   (platform login / device token)
# To also wipe that data, run:
#     Run that central uninstaller with REDBEACON_PURGE=1 to remove local data.
# All output is ASCII-only on purpose (avoids garbled text / iex decode issues).
# ------------------------------------------------------------------------------
$ErrorActionPreference = "Continue"
function Say($m){ Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "!! $m" -ForegroundColor Yellow }
function Test-Truthy($Value){
  if($null -eq $Value){ return $false }
  return @("1", "true", "yes", "on") -contains ([string]$Value).Trim().ToLowerInvariant()
}
function Pause-OnFailure(){
  if($env:CI -eq "true" -or $env:GITHUB_ACTIONS -eq "true" -or $env:REDBEACON_NO_PAUSE -eq "1"){ return }
  try { Read-Host "Press Enter to close this window" | Out-Null } catch {}
}
trap {
  Write-Host ""
  Write-Host "xx RedBeacon uninstall failed. Details:" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  if($_.ScriptStackTrace){ Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray }
  Pause-OnFailure
  continue
}

$Purge = Test-Truthy $env:REDBEACON_PURGE
$Channel = if($env:REDBEACON_CHANNEL){ $env:REDBEACON_CHANNEL.ToLowerInvariant() } else { "stable" }
if(@("test", "testing", "beta") -contains $Channel){ $Channel = "test" } else { $Channel = "stable" }
if($Channel -eq "test"){
  $AppName = "RedBeacon_test"
  $CmdName = "redbeacon-test"
  $CliName = "redbeacon-test-cli"
  $DataHome = "$HOME\.redbeacon_test"
  $TokenHome = "$HOME\.bytestaff_test"
  $DefaultSkillDest = "$HOME\.claude\commands-redbeacon-test"
  $CodexSkillGlob = "redbeacon-test*"
} else {
  $AppName = "RedBeacon"
  $CmdName = "redbeacon"
  $CliName = "redbeacon-cli"
  $DataHome = "$HOME\.redbeacon"
  $TokenHome = "$HOME\.bytestaff"
  $DefaultSkillDest = "$HOME\.claude\commands"
  $CodexSkillGlob = "redbeacon*"
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
  try { & $uv.Source tool uninstall redbeacon 2>$null | Out-Null } catch {}
  # A missing legacy uv tool is expected and must not make an otherwise
  # successful uninstall look failed to a caller that checks LASTEXITCODE.
  $global:LASTEXITCODE = 0
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
$assistantSkillDirs = @(
  $(if($env:REDBEACON_CODEX_SKILL_DIR){ $env:REDBEACON_CODEX_SKILL_DIR } else { "$HOME\.codex\skills" }),
  $(if($env:REDBEACON_OPENCLAW_SKILL_DIR){ $env:REDBEACON_OPENCLAW_SKILL_DIR } else { "$HOME\.openclaw\skills" }),
  $(if($env:REDBEACON_HERMES_SKILL_DIR){ $env:REDBEACON_HERMES_SKILL_DIR } else { "$HOME\.hermes\skills" }),
  $(if($env:REDBEACON_WORKBUDDY_SKILL_DIR){ $env:REDBEACON_WORKBUDDY_SKILL_DIR } else { "$HOME\.workbuddy\skills" })
)
foreach($skillDir in $assistantSkillDirs){
  if(Test-Path $skillDir){
    Get-ChildItem -Path $skillDir -Directory -Filter $CodexSkillGlob -ErrorAction SilentlyContinue |
      Where-Object { $Channel -eq "test" -or $_.Name -notlike "redbeacon-test*" } |
      Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Say "Removing browser engine cache..."
Remove-Item -Recurse -Force "$DataHome\browser" -ErrorAction SilentlyContinue

if($Purge){
  Say "PURGE: removing your $AppName data ($DataHome, $TokenHome)..."
  Remove-Item -Recurse -Force $DataHome -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $TokenHome -ErrorAction SilentlyContinue
} else {
  Warn "Kept your data: $DataHome (accounts/content) + $TokenHome (login)."
  Warn "To wipe it too, set REDBEACON_PURGE=1 and run the current central uninstaller again."
}

Say "$AppName uninstalled."
