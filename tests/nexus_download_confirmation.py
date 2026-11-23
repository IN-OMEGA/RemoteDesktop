"""Exercise the actual confirmation buttons without downloading a game."""
import json
from pathlib import Path

import customtkinter as ctk
from PIL import ImageGrab

from nexus_repacks.cinematic import CinematicNexus
from nexus_repacks.link_resolver import Candidate, Resolution


def main():
    app = CinematicNexus(smoke=True)
    for job in app.tk.call('after', 'info'):
        app.after_cancel(job)
    app.deiconify()
    app.reduced_motion = False
    errors, transfers, inspections = [], [], []
    app.report_callback_exception = lambda kind, error, tb: errors.append(str(error))
    app.begin_download = lambda *args: transfers.append(args)
    candidate = Candidate('https://example.org/game.zip', 'Download game', 'file',
                          'game.zip', 2048, 'application/zip', 'https://example.org/games')
    observed = {}

    def button(dialog, text):
        return next(w for w in dialog.winfo_children() if isinstance(w, ctk.CTkButton) and w.cget('text') == text)

    def cancel():
        dialog = app.popup_active()
        observed['transfers_before_confirmation'] = len(transfers)
        ImageGrab.grab(bbox=(dialog.winfo_rootx(), dialog.winfo_rooty(),
                            dialog.winfo_rootx()+dialog.winfo_width(), dialog.winfo_rooty()+dialog.winfo_height())).save('docs/nexus-download-confirmation.png')
        button(dialog, 'Cancel').invoke()

    def reopen():
        observed['transfers_after_cancel'] = len(transfers)
        app.reduced_motion = True
        app.confirm_download(candidate, 'Fixture')

    def approve():
        dialog = app.popup_active()
        confirm = button(dialog, 'Confirm and download')
        for _ in range(20):
            confirm.invoke()
        observed['transfers_after_20_confirmation_clicks'] = len(transfers)

    def inspect_page():
        app.show_download_resolution(Resolution(candidate.source_page, candidate.source_page, 'Fixture page', [candidate]))

    def finish():
        observed.update(callback_errors=errors, games_launched=0,
                        reduced_motion_confirmation_tested=True)
        Path('docs/nexus-download-confirmation.json').write_text(json.dumps(observed, indent=2))
        app.motion.clear()
        app.destroy()

    app.after(40, lambda: app.confirm_download(candidate, 'Fixture'))
    app.after(900, cancel)
    app.after(1200, reopen)
    app.after(1700, approve)
    app.after(2000, inspect_page)
    app.after(2900, finish)
    app.mainloop()
    assert not errors, observed
    assert observed['transfers_before_confirmation'] == 0, observed
    assert observed['transfers_after_cancel'] == 0, observed
    assert observed['transfers_after_20_confirmation_clicks'] == 1, observed
    print(json.dumps(observed, indent=2))


if __name__ == '__main__':
    main()
