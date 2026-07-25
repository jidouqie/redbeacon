# Legacy updater bridge

These three files are a one-time compatibility bridge for stable RedBeacon
clients whose frozen updater still reads the retired
`bytestaff-redbeacon` OSS root.

- `latest.json` uses the manifest shape understood by RedBeacon 0.1.73.
- `install.ps1` and `install.sh` delegate to the permanent website installer.
- `smoke.ps1` reproduces the Windows 0.1.73 discovery and delegation checks
  without installing or replacing the client.
- The manifest is uploaded last, after both delegates are publicly verified.
- Normal releases must not update these files or use the retired bucket. Once a
  bridged client installs the current package, all later checks and updates use
  the central canonical manifest and the global publication Skill.

The legacy remote objects must be backed up before replacement. This directory
contains no credentials and no upload or publication orchestration.
