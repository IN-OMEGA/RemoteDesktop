# Visible fast updates — 2.4.0

The previous updater checked six seconds after startup, then every four hours. It only changed a footer label and installed on normal exit without reopening the application. Publishing a release did not change an already-running older process. The observed user window was running 2.3.0 and displayed an earlier successful “up to date” check even though 2.3.1 was publicly available.

The GuestManager implementation was inspected locally (`exe/updater.py`, `exe/update_ui.py`, `exe/ui.py`). Its visible required-update dialog and explicit restart flow informed this implementation. Nexus Repacks continues using its dedicated GitHub repository; it does not depend on GuestManager's backend or live event stream.

Starting with 2.4.0, checks begin after 700 ms and repeat every five seconds while the app is running. This is polling, not a real-time push guarantee: internet availability and GitHub publication propagation still affect delivery. No GitHub API credentials are included in the EXE. The public signed channel is `https://raw.githubusercontent.com/IN-OMEGA/NexusRepacks-Updates/main/nexus-update.json`. Cache-busting URLs and no-cache request headers reduce stale responses. The original release endpoint remains a fallback, including when the raw channel reports an older version.

A verified newer manifest queues **Update required** on the Tk thread before the large download starts. The dialog opens during other operations, shows download progress and offers **Update & restart** once the EXE has passed exact size, signature and hash checks. Closing the dialog does not dismiss the update requirement; Quit exits the application. Errors offer Retry. Previously known newer releases are not dismissed by an older signed response.

Update & restart pauses a current download or cancels a local scan, waits for the worker to stop, then stages the transfer's source, folder, Referer and output filename in local application data. After process exit, the hidden helper rechecks the hash, atomically replaces the portable EXE and relaunches it with `--updated`. The new version restores a paused transfer and opens Downloads; Resume is a user action and does not redownload automatically. Partially downloaded files are retained. Install backups remain in `.nexus-updates/previous.exe`.

`update-state.json` records the running version, latest checked version, phase and timestamp. Failures are also written to `update-check.log`; the installer writes `updates/install.log`. These files live in `%LOCALAPPDATA%/NexusRepacks`.

An already-running 2.3.0/2.3.1 process cannot acquire this new polling interval in memory. Close and reopen the replaced EXE once, or use the older footer's manual check and then exit. Once 2.4.0 is running, subsequent updates use the fast visible flow.
