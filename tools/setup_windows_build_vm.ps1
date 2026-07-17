param(
  [Parameter(Mandatory=$true)][string]$PublicKey,
  [string]$BuildUser = "diaojiawang",
  [string]$AllowedSshSource = "10.211.55.2"
)

# Run once in an elevated Windows PowerShell 5.1 window.
$ErrorActionPreference = "Stop"
$UvVersion = "0.8.15"
$ToolsDir = "C:\RedBeaconBuildTools"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
  throw "Run this script from an elevated PowerShell window."
}
if(-not (Get-LocalUser -Name $BuildUser -ErrorAction SilentlyContinue)){
  throw "Build user does not exist: $BuildUser"
}
$adminMembers = @(Get-LocalGroupMember -SID "S-1-5-32-544" -ErrorAction Stop)
if(-not ($adminMembers.Name | Where-Object { $_ -match "\\$([regex]::Escape($BuildUser))$" })){
  throw "Build user must be a local administrator for administrators_authorized_keys: $BuildUser"
}
if($PublicKey -notmatch '^ssh-(ed25519|rsa)\s+'){
  throw "PublicKey must be an OpenSSH public key."
}

$capability = Get-WindowsCapability -Online -Name "OpenSSH.Server~~~~0.0.1.0"
if($capability.State -ne "Installed"){
  Add-WindowsCapability -Online -Name "OpenSSH.Server~~~~0.0.1.0" | Out-Null
}
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd

$firewall = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
if(-not $firewall){
  New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" `
    -Enabled True -Profile Any -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 `
    -RemoteAddress $AllowedSshSource | Out-Null
} else {
  Set-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -Enabled True -Profile Any | Out-Null
  Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" | Get-NetFirewallAddressFilter | `
    Set-NetFirewallAddressFilter -RemoteAddress $AllowedSshSource | Out-Null
}

$sshDir = Join-Path $env:ProgramData "ssh"
$authorizedKeys = Join-Path $sshDir "administrators_authorized_keys"
New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
$existing = @()
if(Test-Path $authorizedKeys){ $existing = @(Get-Content -Encoding ASCII $authorizedKeys) }
if($existing -notcontains $PublicKey){
  $existing += $PublicKey
  [System.IO.File]::WriteAllLines($authorizedKeys, $existing, [System.Text.Encoding]::ASCII)
}
& icacls.exe $authorizedKeys /inheritance:r | Out-Null
& icacls.exe $authorizedKeys /grant "*S-1-5-18:F" "*S-1-5-32-544:F" | Out-Null
if($LASTEXITCODE -ne 0){ throw "Failed to secure administrators_authorized_keys" }

New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
$uvExe = Join-Path $ToolsDir "uv.exe"
$actualUv = ""
if(Test-Path $uvExe){
  $actualUv = ((& $uvExe --version) -split '\s+')[1]
}
if($actualUv -ne $UvVersion){
  $download = Join-Path $env:TEMP "uv-x86_64-$UvVersion.zip"
  $expanded = Join-Path $env:TEMP "uv-x86_64-$UvVersion"
  Remove-Item -Recurse -Force $expanded -ErrorAction SilentlyContinue
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest `
    -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" `
    -OutFile $download -UseBasicParsing
  Expand-Archive -Path $download -DestinationPath $expanded -Force
  $downloadedUv = Get-ChildItem -Path $expanded -Recurse -Filter "uv.exe" | Select-Object -First 1
  if(-not $downloadedUv){ throw "Downloaded uv archive did not contain uv.exe" }
  Copy-Item -Force $downloadedUv.FullName $uvExe
}

$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$parts = @($machinePath -split ';' | Where-Object { $_ })
if($parts -notcontains $ToolsDir){
  [Environment]::SetEnvironmentVariable("Path", (($parts + $ToolsDir) -join ';'), "Machine")
}
$env:Path = "$ToolsDir;$env:Path"
$installedUv = ((& $uvExe --version) -split '\s+')[1]
if($installedUv -ne $UvVersion){ throw "uv installation failed: expected $UvVersion, got $installedUv" }

# Keep the VM available during long browser downloads and PyInstaller builds.
& powercfg.exe /change standby-timeout-ac 0
Restart-Service sshd

$sshd = Join-Path $env:WINDIR "System32\OpenSSH\sshd.exe"
if(Test-Path $sshd){
  & $sshd -t
  if($LASTEXITCODE -ne 0){ throw "OpenSSH server configuration is invalid" }
}
$ips = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
  $_.IPAddress -notlike "127.*" -and $_.AddressState -eq "Preferred"
} | Select-Object -ExpandProperty IPAddress)

Write-Host "WINDOWS_BUILD_USER=$BuildUser"
Write-Host "WINDOWS_BUILD_IP=$($ips -join ',')"
Write-Host "SSH_ALLOWED_SOURCE=$AllowedSshSource"
Write-Host "UV_VERSION=$installedUv"
Write-Host "SSH_READY=true"
