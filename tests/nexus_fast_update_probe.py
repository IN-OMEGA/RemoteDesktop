"""Urgent update UI while a transfer runs. No EXE is installed or executed."""
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from PIL import ImageGrab
from nexus_repacks.cinematic import CinematicNexus


def main():
    observed,errors={},[]
    with tempfile.TemporaryDirectory(prefix='nexus-fast-update-') as directory:
        root=Path(directory)
        app=CinematicNexus(smoke=True)
        for job in app.tk.call('after','info'):
            app.after_cancel(job)
        app.root_path=root
        app.geometry('1120x740+30+30')
        app.attributes('-topmost',True)
        app.report_callback_exception=lambda kind,error,tb:errors.append(str(error))
        app.busy=True
        app.download=Mock()
        app.transfer={'phase':'downloading','name':'Fixture'}
        app._resume_download=('https://example.org/game.zip','Fixture','','game.zip')
        app.updater.on_close=Mock()
        app.updater.check=Mock()
        real_destroy=app.destroy
        app.destroy=Mock()
        data={'version':'9.0.0','url':'https://example.org/new.exe','sha256':'a'*64,'size':2048}
        app.after(10,app.drain)

        def available():
            app.on_update_event('available',data)
            notice=app._update_notice
            observed['visible_notice_does_not_wait_for_busy_transfer']=bool(notice) and app.busy
            app.on_update_event('downloading',data,.5)
            observed['download_progress_displayed']=notice.progress.get()==.5
            observed['install_disabled_until_verified']=notice.install.cget('state')=='disabled'
            blocked=Mock()
            app.guarded_action('test-action',blocked)
            observed['normal_actions_blocked_by_update_notice']=blocked.call_count==0
            app.tk.call(notice.window.protocol('WM_DELETE_WINDOW'))
            observed['closing_prompt_keeps_update_visible']=notice.window.winfo_exists()
            app.after(300,error)

        def error():
            notice=app._update_notice
            app.on_update_event('error',data,error='Fixture failure')
            notice.install.invoke()
            observed['error_provides_retry']=app.updater.check.call_count==1
            app.on_update_event('available',dict(data,version='9.0.1'))
            observed['new_release_reuses_same_prompt']=app._update_notice is notice
            app.updater.pending=(root/'staged.exe',dict(data,version='9.0.1'))
            app.on_update_event('ready',app.updater.pending[1],1.)
            observed['ready_has_update_and_restart']=notice.install.cget('text')=='Update & restart' and notice.install.cget('state')=='normal'
            app.after(300,restart)

        def restart():
            app.update_idletasks()
            ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),
                                app.winfo_rooty()+app.winfo_height())).save('docs/nexus-fast-update-2.4.png')
            notice=app._update_notice
            for _ in range(20):
                notice.install.invoke()
            observed['running_download_is_paused_once']=app.download.cancel.call_count==1
            observed['does_not_close_before_worker_stops']=app.destroy.call_count==0
            app.finish_download_stop()
            app.post('call',lambda:setattr(app,'busy',False))
            app.after(400,finish)

        def finish():
            observed['one_install_and_restart']=app.updater.on_close.call_count==1 and app.updater.on_close.call_args.kwargs=={'restart':True}
            observed['old_window_closed_once']=app.destroy.call_count==1
            session=json.loads((root/'updates/resume.json').read_text())
            observed['paused_transfer_saved_for_new_version']=tuple(session['download'])==app._resume_download
            app._update_notice.destroy()
            app._update_notice=None
            app.motion.clear()
            real_destroy()

        with patch('nexus_repacks.app.STATE',root),patch('nexus_repacks.app.library.save_library'):
            app.after(400,available)
            app.mainloop()
        observed.update(callback_errors=errors,real_games_launched=0,real_updates_installed=0)
        Path('docs/nexus-fast-update-verification.json').write_text(json.dumps(observed,indent=2),encoding='utf-8')
        assert not errors,observed
        for key,value in observed.items():
            if key not in ('callback_errors','real_games_launched','real_updates_installed'):
                assert value,observed
        print(json.dumps(observed,indent=2))


if __name__=='__main__':
    main()
