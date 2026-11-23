"""Native intro, responsive layout and motion preference checks. No games launched."""
import json
from pathlib import Path
from PIL import ImageGrab
from nexus_repacks.cinematic import CinematicNexus
from nexus_repacks.motion import FrameClock
from statistics import median


def main():
    app = CinematicNexus(smoke=True)
    for job in app.tk.call('after', 'info'):
        app.after_cancel(job)
    app.deiconify()
    app.geometry('1440x900+60+40')
    app.reduced_motion = False
    errors, observed, samples = [], {}, []
    app.report_callback_exception = lambda kind, error, tb: errors.append(str(error))
    app.after(10, app.drain)

    def capture(name):
        app.update_idletasks()
        ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),
                            app.winfo_rooty()+app.winfo_height())).save('docs/'+name+'.png')

    def sample():
        if getattr(app, '_intro', None) and app._intro.winfo_exists():
            samples.append(app._intro.progress)
        app.after(80, sample)

    def entered():
        observed['intro_removed'] = not app._intro.winfo_exists()
        observed['window_visible_after_intro'] = float(app.attributes('-alpha')) == 1
        intervals=app._intro.motion.intervals
        observed['intro_frame_interval_median_ms'] = round(median(intervals),2) if intervals else None
        capture('nexus-aurora-library-1440')
        app.geometry('1120x740+60+40')

    def compact():
        capture('nexus-aurora-library-1120')
        canvas=app.scene
        play=canvas.bbox('play')
        options=canvas.bbox('options')
        observed['launch_controls_fit_compact_window'] = bool(play and options and play[0]>=0 and options[2]<canvas.winfo_width())
        app.reduced_motion=True
        app.show_intro()

    def reduced():
        observed['reduced_intro_removed'] = not app._intro.winfo_exists()
        app.reduced_motion=False
        app.show_intro()
        app._intro.finish()
        app._intro.finish()
        app.request_page('downloads')

    def finish():
        observed.update(callback_errors=errors, intro_samples=len(samples),
                        intro_intermediate_samples=sum(0<v<1 for v in samples),
                        click_to_skip_leaves_no_overlay=not app._intro.winfo_exists(), games_launched=0)
        observed['tab_change_during_intro_exit_preserves_opacity'] = float(app.attributes('-alpha')) == 1
        observed['high_resolution_timer_released_at_rest'] = not FrameClock.active and not FrameClock.requested
        Path('docs/nexus-aurora-verification.json').write_text(json.dumps(observed,indent=2))
        app.motion.clear()
        app.destroy()

    app.after(100,app.show_intro)
    app.after(130,sample)
    app.after(350,lambda:capture('nexus-aurora-intro-start'))
    app.after(900,lambda:capture('nexus-aurora-intro-middle'))
    app.after(1500,lambda:capture('nexus-aurora-intro-end'))
    app.after(2350,entered)
    app.after(2850,compact)
    app.after(3300,reduced)
    app.after(4200,finish)
    app.mainloop()
    assert not errors, observed
    for key in ('intro_removed','window_visible_after_intro','launch_controls_fit_compact_window',
                'reduced_intro_removed','click_to_skip_leaves_no_overlay','tab_change_during_intro_exit_preserves_opacity',
                'high_resolution_timer_released_at_rest'):
        assert observed[key], observed
    assert observed['intro_intermediate_samples'] >= 3, observed
    print(json.dumps(observed,indent=2))


if __name__ == '__main__':
    main()
