"""Exercise real Tk event handlers during interrupted page/hover animations."""
import json
import traceback
from pathlib import Path

import customtkinter as ctk

from nexus_repacks.cinematic import AnimatedDialog, CinematicNexus


def main():
    app = CinematicNexus(smoke=True)
    for job in app.tk.call('after', 'info'):
        app.after_cancel(job)
    app.deiconify()
    app.state('normal')
    app.reduced_motion = False
    errors, cleared, clicks = [], [], []
    app.report_callback_exception = lambda kind, error, tb: errors.append(''.join(traceback.format_exception(kind, error, tb)))
    original_clear = app.clear
    def counted_clear():
        cleared.append(app.current_page)
        original_clear()
    app.clear = counted_clear
    app.after(10, app.drain)
    app.show_library()
    original_play = app.play
    app.play = lambda game: clicks.append(game.id)
    stages = 120
    states = ['downloads', 'protection', 'library']
    def hammer(i):
        if app.current_page == 'library' and app.scene:
            rects = app.scene.find_withtag('play')
            if rects:
                coords = app.scene.coords(rects[0])
                if len(coords) == 4:
                    app.scene.event_generate('<Motion>', x=round(coords[0]+10), y=round(coords[1]+10))
        app.request_page(states[i % 3])
    for i in range(stages):
        app.after(300+i*12, lambda n=i: hammer(n))
    app.after(1950, lambda: app.request_page('library'))
    observed = {}
    def click_burst():
        if app.current_page != 'library':
            app.request_page('library')
            app.after(450, click_burst)
            return
        invoked = []
        # Real CTkButton.invoke dispatches the same protected callback as a mouse click.
        button = app._button(app.content, 'fixture burst', lambda: invoked.append(1))
        for _ in range(50):
            button.invoke()
        observed['button_action_count_for_50_clicks'] = len(invoked)
        button.destroy()
        app.play = original_play
        for _ in range(20):
            app.play(app.games[0])
        dialogs = [w for w in app.winfo_children() if isinstance(w, AnimatedDialog) and not w._closing]
        observed['dialogs_for_20_play_clicks'] = len(dialogs)
        for dialog in dialogs:
            dialog.destroy()
    app.after(2600, click_burst)
    def finish():
        observed.update(navigation_requests=stages, actual_page_rebuilds=len(cleared), final_page=app.current_page,
                        callback_errors=errors, games_launched=0)
        Path('docs/nexus-repacks-navigation-stress.json').write_text(json.dumps(observed, indent=2))
        app.motion.clear()
        app.destroy()
    app.after(3700, finish)
    app.mainloop()
    assert not errors, observed
    assert observed['button_action_count_for_50_clicks'] == 1, observed
    assert observed['dialogs_for_20_play_clicks'] == 1, observed
    assert observed['actual_page_rebuilds'] < stages // 2, observed
    assert observed['final_page'] == 'library', observed
    print(json.dumps(observed, indent=2))


if __name__ == '__main__':
    main()
