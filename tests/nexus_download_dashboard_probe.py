"""Exercise native dashboard state without touching the user's active download."""
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import ImageGrab
from nexus_repacks.cinematic import CinematicNexus


def main():
    app=CinematicNexus(smoke=True)
    for job in app.tk.call('after','info'):
        app.after_cancel(job)
    app.deiconify()
    app.attributes('-topmost',True)
    app.geometry('1440x900+40+30')
    app.reduced_motion=False
    errors,observed=[],{}
    app.report_callback_exception=lambda kind,error,tb:errors.append(str(error))
    app.download=Mock()
    app.transfer={'phase':'downloading','name':'Jeu de test','destination':str(app.root_path/'downloads'/'Fixture')}
    app.busy=True
    app.show_downloads()
    app.after(10,app.drain)
    def fixture():
        app.post('log','\x1b[32m[#46f934 36GiB/72GiB(50%) CN:6 SD:1 DL:2.4MiB ETA:4h12m]\x1b[0m')
        app.post('log','FILE: C:/Fixtures/Jeu de test.zip')
    def capture(name):
        app.update_idletasks()
        ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),
                            app.winfo_rooty()+app.winfo_height())).save('docs/'+name+'.png')
    def when(predicate, action, deadline=None):
        deadline=deadline or time.monotonic()+12
        if predicate():
            action()
        elif time.monotonic()>deadline:
            errors.append('Timed out waiting for UI state: '+action.__name__)
            finish()
        else:
            app.after(50,lambda:when(predicate,action,deadline))
    def check():
        view=app.download_view
        observed['progress_bar_shows_half']=abs(view.bar.get()-.5)<.001
        observed['visible_percent']=view.percent.cget('text')
        observed['visible_speed']=view.metrics['speed'].cget('text')
        observed['journal_hidden_by_default']=not app.download_log.winfo_ismapped()
        with patch('nexus_repacks.download_view.webbrowser.open') as browser:
            for button in view.source_buttons:
                button.invoke()
            observed['source_links']=[call.args[0] for call in browser.call_args_list]
        capture('nexus-downloads-2.1')
        app.download_source.insert(0,'https://example.org/page')
        app.show_library()
        app.show_downloads()
        observed['state_survives_tab_switch']=app.transfer['ratio']==.5 and app.download_source.get()=='https://example.org/page'
        active_transfer=app.transfer.copy()
        with patch('nexus_repacks.app.filedialog.askopenfilename',return_value='C:/Fixtures/Next Game.torrent') as select:
            app.download_view.torrent.invoke()
            observed['torrent_picker_works_while_downloading']=select.call_count==1 and app.download_source.get()=='C:/Fixtures/Next Game.torrent'
        observed['torrent_selection_preserves_active_transfer']=app.transfer==active_transfer and app.download_name.get()=='Next Game'
        for _ in range(20):
            app.download_view.cancel.invoke()
        observed['one_stop_for_20_cancel_clicks']=app.download.cancel.call_count==1
        app.finish_download_stop()
        app.post('call',lambda:setattr(app,'busy',False))
        when(lambda:app.transfer['phase']=='cancelled',compact)
    def interrupt_animation():
        old=app.download_view
        app.show_library()
        app.show_downloads()
        observed['leaving_during_bar_animation_cancels_callbacks']=not old.motion.jobs
        when(lambda:not app._navigation_active and 'progress' not in app.download_view.motion.jobs and app.download_view.bar.get()==.5,check)
    def compact():
        observed['cancelled_state']=app.transfer['phase']=='cancelled'
        app.geometry('1120x740+40+30')
        app.after(500,compact_capture)
    def compact_capture():
        capture('nexus-downloads-2.1-compact')
        app.transfer['phase']='paused'
        app._resume_download=('https://example.org/game.zip','Fixture','https://example.org/page','game.zip')
        app.begin_download=Mock()
        app.download_view.update_transfer()
        app.download_view.resume.invoke()
        observed['resume_retains_original_arguments']=app.begin_download.call_args.args==app._resume_download
        app.after(100,finish)
    def finish():
        observed.update(callback_errors=errors,user_downloads_touched=False,games_launched=0)
        Path('docs/nexus-download-dashboard-verification.json').write_text(json.dumps(observed,indent=2))
        app.motion.clear()
        app.destroy()
    app.after(100,fixture)
    app.after(240,interrupt_animation)
    app.mainloop()
    assert not errors,observed
    for key in ('progress_bar_shows_half','journal_hidden_by_default','state_survives_tab_switch',
                'one_stop_for_20_cancel_clicks','cancelled_state','resume_retains_original_arguments',
                'leaving_during_bar_animation_cancels_callbacks','torrent_picker_works_while_downloading',
                'torrent_selection_preserves_active_transfer'):
        assert observed[key],observed
    print(json.dumps(observed,indent=2))


if __name__=='__main__':
    main()
