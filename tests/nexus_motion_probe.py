"""UI-only probe: actual motion, repeated navigation and tray restoration. No games run."""
import json
import time
from pathlib import Path

from nexus_repacks import library
from nexus_repacks.cinematic import CinematicNexus, AnimatedDialog
from nexus_repacks.motion import Motion


def main():
    app = CinematicNexus(smoke=True)
    for callback in app.tk.call('after', 'info'):
        app.after_cancel(callback)
    # Cancelling startup jobs also cancels CustomTkinter's title-bar remap.
    app.deiconify()
    app.state('normal')
    app.reduced_motion = False
    errors = []
    app.report_callback_exception = lambda *args: errors.append(str(args[1]))
    app.games = library.discover(app.root_path / 'games')
    app.show_library()
    samples = []
    timeline = Motion(app)
    timeline.animate('proof', 320, lambda value: samples.append(value))
    def popup():
        app.game_menu()
    observed = {}
    def early():
        dialogs = [w for w in app.winfo_children() if isinstance(w, AnimatedDialog)]
        if dialogs:
            dialog = dialogs[0]
            observed['early_alpha'] = float(dialog.attributes('-alpha'))
            observed['early_rows'] = sum(c.winfo_ismapped() for c in dialog.winfo_children())
    def late():
        dialogs = [w for w in app.winfo_children() if isinstance(w, AnimatedDialog)]
        if dialogs:
            dialog = dialogs[0]
            observed['late_alpha'] = float(dialog.attributes('-alpha'))
            observed['late_rows'] = sum(c.winfo_ismapped() for c in dialog.winfo_children())
            observed['dialog_state'] = dialog.state()
            observed['dialog_children'] = [(type(c).__name__, c.winfo_manager(), c.winfo_width(), c.winfo_height()) for c in dialog.winfo_children()]
            dialog.destroy()
    def navigation():
        app.show_downloads()
        app.show_protection()
        app.show_library()
        if len(app.games) > 1:
            app.select(app.games[1])
            app.select(app.games[0])
        selected = app.selected.id
        app.scene.event_generate('<MouseWheel>', delta=-120)
        app.scene.event_generate('<MouseWheel>', delta=120)
        observed['mousewheel_keeps_game'] = app.selected.id == selected
    def save_warning():
        app.play(app.games[0])
    def close_warning():
        dialogs = [w for w in app.winfo_children() if isinstance(w, AnimatedDialog) and w.title() == 'Remember to save']
        observed['save_warning_shown'] = bool(dialogs)
        for dialog in dialogs:
            dialog.destroy()
    def tray():
        app.hide_to_tray()
        observed['tray_hidden'] = app.state() == 'withdrawn'
        observed['tray_icon_created'] = app._tray is not None
    def restore():
        app.restore_from_tray()
        observed['tray_restored'] = app.state() != 'withdrawn'
    def finish():
        timeline.clear()
        if app._tray:
            app._tray.stop()
        observed['animation_samples'] = len(samples)
        observed['animation_intermediate_values'] = sum(0 < v < 1 for v in samples)
        observed['callbacks_errors'] = errors
        observed['sources'] = sorted({g.source for g in app.games})
        Path('docs/nexus-repacks-motion-verification.json').write_text(json.dumps(observed, indent=2))
        app.destroy()
    app.after(650, popup)
    app.after(780, early)
    app.after(1600, late)
    app.after(1850, navigation)
    app.after(2100, save_warning)
    app.after(2500, close_warning)
    app.after(2800, tray)
    app.after(3250, restore)
    app.after(3900, finish)
    app.mainloop()
    assert not errors, errors
    assert observed['animation_intermediate_values'] >= 3, observed
    assert observed.get('early_rows', 99) < observed.get('late_rows', 0), observed
    assert observed.get('tray_hidden') and observed.get('tray_restored'), observed
    assert observed['sources'] == ['REPACKS'], observed
    assert observed['mousewheel_keeps_game'], observed
    assert observed['save_warning_shown'], observed
    print(json.dumps(observed, indent=2))


if __name__ == '__main__':
    main()
