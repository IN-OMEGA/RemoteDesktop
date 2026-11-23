# Manual launch without scanning — 2.3.1

Library and Protection offer **Skip scan and play…** for local repacks. It works for games of any size, including when the scanner cannot inspect a large active file. The normal Scan and play action keeps its existing checks.

Each manual launch opens a confirmation identifying the game and explaining that no scan or file verification will run. Existing static scan findings and Windows scan reports are disclosed in that confirmation. **I understand — play without scanning** authorizes only this launch. Cancel, closing the dialog or repeated clicks do not launch extra processes.

If the same game's local scan is active, confirmation cancels that scan and waits for its worker to finish before launching. Hashing now checks cancellation between 1 MiB chunks. A cancellation after the worker finished but before its UI callback also prevents its automatic verified launch. An unrelated download or operation is not cancelled by this feature.

The manual path checks that the selected launcher exists, is an EXE/BAT/CMD inside the selected game folder, then uses the existing launch helper that avoids inheriting administrator privileges. It does not scan, hash, revalidate snapshots or save a verified cache entry. Existing reports are preserved. A successful manual launch is labelled **UNVERIFIED · SCAN SKIPPED** for this session. A later manual scan replaces that display with its actual verdict. No size-based safe verdict or persistent antivirus exception is created.

Future portable update backups are stored in `.nexus-updates/previous.exe` beside the application, instead of placing another EXE in the main folder. The previous published updater may leave its old `.update-backup` file once when updating to this version.

Validation: 69 unit tests plus the native confirmation probe cover Cancel, window close, repeat requests/clicks, unavailable targets, standard-user EXE/batch dispatch, preservation of reports, absence of scanning/hashing during override and cancellation before launch. All game launch calls in these checks are mocked. Download cancellation and rapid navigation probes also pass.
