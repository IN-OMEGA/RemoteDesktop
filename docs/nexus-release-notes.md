Checks for signed updates at startup and every five seconds instead of every four hours. Uses a lightweight signed publication channel, cache-busting requests and a release endpoint fallback.

A newer release immediately shows an “Update required” window, including while a transfer is running. The update downloads automatically with visible progress. “Update & restart” installs the verified EXE and reopens Nexus. The notice offers retry on failure and does not report a failed check as “up to date”.

An active download is paused before restarting. Partial files remain on disk, and the new version restores the transfer with a Resume button. Game files, scan reports and the library are preserved. The existing catalog and manual scan override remain available after updating.

Versions already running with the previous four-hour schedule retain that old behavior until restarted or manually checked once. This new polling and notification behavior takes effect after installing 2.4.0.
