# Nexus Repacks 2.2 — portable updates

The built-in interface is now English. Downloads use a compact two-column dashboard, with a source panel, transfer statistics, pause/resume controls and links to the three requested repack websites. Links open in the default browser; they are not safety endorsements.

The dedicated public distribution repository is https://github.com/IN-OMEGA/NexusRepacks-Updates . Only the application EXE and signed update manifest are published there. Source code, games, local settings and the signing key stay on this PC.

## For recipients

Distribute the new `Nexus Repacks.exe` once. Older copies from before 2.2 have no updater and must be replaced once. Future versions check at launch (after 6 seconds) and every 4 hours while running. The footer also offers a manual check. Internet access is required to check and download updates.

A newer release downloads in the background. Nexus verifies its Ed25519 signature, exact size and SHA-256. The footer says the version is ready. On a normal exit, a hidden helper waits for Nexus to close, verifies the hash again, then atomically replaces the portable EXE. The new version opens next time. No reinstall is required. The EXE's folder must be writable.

An interrupted or corrupted download never replaces the EXE. The old EXE is kept as `Nexus Repacks.exe.update-backup` after replacement. Launch checks never interrupt downloads or games. The updater does not modify the game library, saved games or `%LOCALAPPDATA%/NexusRepacks` user data. Logs are `update-check.log` and `updates/install.log` in that data folder.

## Publishing the next version

From `C:\Users\Me\Documents\GitHub\RemoteDesktop`, after making source changes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release_nexus_update.ps1 -Version 2.2.1
```

Choose a version newer than the current one each time. This checks GitHub access, updates APP_VERSION, runs the tests, builds the EXE, signs the manifest, uploads both files into a draft release and publishes it as Latest only after verification. Authentication uses Git Credential Manager or GH_TOKEN/GITHUB_TOKEN from the environment. No credentials are included in the EXE.

If publication fails after the version was changed, resolve the error and resume the individual build/sign/publish steps below rather than incrementing again unnecessarily.

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm NexusRepacks.spec
.\.venv\Scripts\python.exe scripts/prepare_nexus_update.py
.\.venv\Scripts\python.exe scripts/publish_nexus_update.py --publish
```

You can also upload `dist/nexus-update-release/Nexus-Repacks.exe` and `nexus-update.json` manually to GitHub, using the exact tag printed by the preparation script, e.g. `nexus-v2.2.1`. Publish as a public, non-prerelease, Latest release. The EXE reads the fixed HTTPS URL `https://github.com/IN-OMEGA/NexusRepacks-Updates/releases/latest/download/nexus-update.json` as described in [GitHub's release link documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases).

Back up `%LOCALAPPDATA%/NexusRepacksPublisher/signing-key.pem` privately. Keep the same key for future updates; existing copies trust its public key. Never upload or share this private file. Only the public key is embedded in `nexus_repacks/update_config.json`.

## Scanning large games

File size is never treated as proof of safety. Games of 5–10 GB or more are still scanned. Code too large to inspect, encrypted archives and inspection limits are reported as incomplete/needs review rather than falsely marked safe. Existing verified-file caching remains available; the size threshold does not bypass detection.

## Validation

56 automated tests cover scanning, link inspection, progress parsing and the new updater. The updater tests include modified signatures, downgrade rejection, truncated/oversized downloads, hash mismatches, actual Windows atomic replacement and preservation of the original when verification fails. The native dashboard probe checks transfer state, cancellation, resume, all three links and both window sizes. Local HTTP/aria2 integration checks confirm the exact downloaded hash, explicit download confirmation and partial-file preservation on cancellation. No game or downloaded program is executed by these checks.
