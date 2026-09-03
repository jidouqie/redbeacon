# RedBeacon stable installer bootstrap (Windows).
# BYTESTAFF_CHANNEL_IDENTITY: stable
# BYTESTAFF_CANONICAL_MANIFEST_URL: https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/stable/latest.json
# BYTESTAFF_FIXED_CHANNEL_ARGUMENT: stable
# BYTESTAFF_AMBIENT_CHANNEL_OVERRIDES: forbidden
param()

$ErrorActionPreference = "Stop"
if($args.Count -ne 0){ throw "This installer accepts no arguments." }

function Get-TrustedWindowsEnvironment(){
  $userProfile = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
  $localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
  $appData = [Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData)
  $systemDirectory = [Environment]::SystemDirectory
  foreach($entry in @(
    @("User profile", $userProfile), @("Local application data", $localAppData),
    @("Application data", $appData), @("Windows system directory", $systemDirectory)
  )){
    if([string]::IsNullOrWhiteSpace($entry[1]) -or -not [IO.Path]::IsPathRooted($entry[1])){
      throw "$($entry[0]) could not be resolved from Windows known folders."
    }
  }
  $windowsDirectory = [IO.Directory]::GetParent($systemDirectory).FullName
  $powerShellDirectory = [IO.Path]::Combine($systemDirectory, "WindowsPowerShell", "v1.0")
  $powerShellExe = [IO.Path]::Combine($powerShellDirectory, "powershell.exe")
  if(-not [IO.File]::Exists($powerShellExe)){ throw "Trusted Windows PowerShell was not found." }
  $tempRoot = [IO.Path]::Combine($localAppData, "Temp")
  [void][IO.Directory]::CreateDirectory($tempRoot)
  return [pscustomobject]@{
    UserProfile = $userProfile; LocalAppData = $localAppData; AppData = $appData
    TempRoot = $tempRoot; PowerShellExe = $powerShellExe
    Path = "$systemDirectory;$windowsDirectory;$powerShellDirectory"
    PSModulePath = [IO.Path]::Combine($powerShellDirectory, "Modules")
  }
}

function Push-TrustedWindowsEnvironment($Trusted){
  $values = @{
    "HOME" = $Trusted.UserProfile
    "USERPROFILE" = $Trusted.UserProfile
    "LOCALAPPDATA" = $Trusted.LocalAppData
    "APPDATA" = $Trusted.AppData
    "PATH" = $Trusted.Path
    "TEMP" = $Trusted.TempRoot
    "TMP" = $Trusted.TempRoot
    "TMPDIR" = $Trusted.TempRoot
    "PSMODULEPATH" = $Trusted.PSModulePath
  }
  $keys = @($values.Keys) + @(
  )
  $old = @{}
  foreach($key in $keys){
    $old[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
  }
  foreach($entry in $values.GetEnumerator()){
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
  }
  return $old
}

function Pop-TrustedWindowsEnvironment($Old){
  foreach($entry in $Old.GetEnumerator()){
    [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
  }
}

function Assert-StableWrapperUrl([string]$Url, [string]$Label){
  try { $uri = [Uri]$Url } catch { throw "$Label URL is invalid." }
  $plain = (-not $uri.UserInfo -and -not $uri.Query -and -not $uri.Fragment)
  $owned = $Url.StartsWith($script:ReleaseOrigin + "/", [System.StringComparison]::Ordinal)
  if(-not $plain -or -not $owned){ throw "$Label URL is unsafe." }
  return $uri
}

function Read-StrictUtf8File([string]$Path, [string]$Label){
  try {
    return [System.Text.UTF8Encoding]::new($false, $true).GetString([System.IO.File]::ReadAllBytes($Path))
  }
  catch { throw "$Label is not valid UTF-8." }
}

function Get-StableCoreArtifact($Manifest, [string]$Version, [string]$CoreName){
  $artifactPath = "installers/$CoreName"
  $matches = @()
  foreach($candidate in @($Manifest.artifacts)){
    if(([string]$candidate.path) -ceq $artifactPath){ $matches += $candidate }
  }
  if($matches.Count -ne 1){ throw "RedBeacon stable $CoreName is missing from the central manifest." }
  $entry = $matches[0]
  try { $size = [Int64]$entry.size } catch { throw "Installer core size is invalid." }
  $sha = ([string]$entry.sha256).ToLowerInvariant()
  if($size -le 0 -or $sha -notmatch '^[0-9a-f]{64}$'){ throw "Installer core metadata is invalid." }
  $url = [string]$entry.url
  $coreUri = Assert-StableWrapperUrl $url "Installer core"
  $expectedUrl = "$($script:ReleaseOrigin)/projects/redbeacon/stable/releases/$Version/installers/$CoreName"
  if($url -cne $expectedUrl){ throw "Installer core URL does not match the stable release." }
  return [pscustomobject]@{ Url = $url; Size = $size; Sha256 = $sha }
}

function Read-VerifiedStableCore($Artifact, [string]$Path){
  Microsoft.PowerShell.Utility\Invoke-WebRequest -Uri $Artifact.Url -OutFile $Path -UseBasicParsing -TimeoutSec 60 | Microsoft.PowerShell.Core\Out-Null
  if(([IO.FileInfo]::new($Path)).Length -ne [Int64]$Artifact.Size){ throw "Installer core size mismatch." }
  $actual = (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
  if($actual -ne $Artifact.Sha256){ throw "Installer core checksum mismatch." }
  $text = (Read-StrictUtf8File $Path "Installer core").TrimStart([char]0xFEFF)
  if([string]::IsNullOrWhiteSpace($text)){ throw "Installer core is empty." }
  return $text
}

$script:ReleaseOrigin = "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
$manifestUrl = "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/stable/latest.json"
$trusted = Get-TrustedWindowsEnvironment
$oldEnvironment = Push-TrustedWindowsEnvironment $trusted
$tmp = $null
try {
  $tmp = [IO.Path]::Combine($trusted.TempRoot, "rb_stable_bootstrap_" + [guid]::NewGuid().ToString("N"))
  [void][IO.Directory]::CreateDirectory($tmp)
  [void](Assert-StableWrapperUrl $manifestUrl "Manifest")
  $manifestFile = [IO.Path]::Combine($tmp, "latest.json")
  Microsoft.PowerShell.Utility\Invoke-WebRequest -Uri $manifestUrl -OutFile $manifestFile -UseBasicParsing -TimeoutSec 20 | Microsoft.PowerShell.Core\Out-Null
  try { $manifest = Microsoft.PowerShell.Utility\ConvertFrom-Json -InputObject (Read-StrictUtf8File $manifestFile "Release manifest") }
  catch { throw "Release manifest is not valid UTF-8 JSON." }
  $version = [string]$manifest.version
  if(([string]$manifest.schema) -ne "1" -or ([string]$manifest.project) -ne "redbeacon" -or ([string]$manifest.channel) -ne "stable" -or $version -notmatch '^\d+\.\d+\.\d+$'){
    throw "Release manifest does not match RedBeacon stable."
  }
  $artifact = Get-StableCoreArtifact $manifest $version "install-core.ps1"
  $coreFile = [IO.Path]::Combine($tmp, "install-core.ps1")
  [void](Read-VerifiedStableCore $artifact $coreFile)
  & $trusted.PowerShellExe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $coreFile -RedBeaconInstallerChannel "stable" -RedBeaconInstallerManifestFile $manifestFile -RedBeaconInstallerReleaseOrigin $script:ReleaseOrigin -RedBeaconInstallerExecutionMode "production"
  if($LASTEXITCODE -ne 0){ throw "RedBeacon stable installer core failed with exit code $LASTEXITCODE." }
}
finally {
  try { if($tmp -and [IO.Directory]::Exists($tmp)){ [IO.Directory]::Delete($tmp, $true) } } catch {}
  Pop-TrustedWindowsEnvironment $oldEnvironment
}
