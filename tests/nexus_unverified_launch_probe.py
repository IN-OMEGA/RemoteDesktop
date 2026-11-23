"""Exercise the confirmation UI. All actual game launch calls are mocked."""
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import Mock, patch

import customtkinter as ctk
from PIL import ImageGrab
from nexus_repacks.cinematic import CinematicNexus
from nexus_repacks.library import Game
from nexus_repacks.security import Finding, ScanResult


def main():
    observed, errors = {}, []
    with tempfile.TemporaryDirectory(prefix='nexus-skip-scan-') as directory:
        root=Path(directory)
        target=root/'Harmless fixture.exe'
        target.write_text('Harmless fixture. Never executed.')
        game=Game.local(root,target,title='Large Game Fixture')
        app=CinematicNexus(smoke=True)
        for job in app.tk.call('after','info'):
            app.after_cancel(job)
        app.games=[game]
        app.selected=game
        report=ScanResult(str(root),findings=[Finding('incomplete','large-active',str(target),'Content too large to inspect.')])
        app.results={game.id:report}
        app.hide_to_tray=Mock()
        app.attributes('-topmost',True)
        app.geometry('1120x740+30+30')
        app.report_callback_exception=lambda kind,error,tb:errors.append(str(error))
        app.show_library()
        app.after(10,app.drain)

        def buttons(parent):
            result=[]
            for child in parent.winfo_children():
                if isinstance(child,ctk.CTkButton):
                    result.append(child)
                result.extend(buttons(child))
            return result

        def find(parent,text):
            return next(button for button in buttons(parent) if text in button.cget('text'))

        def when(predicate,action,deadline=None):
            deadline=deadline or time.monotonic()+12
            if predicate():
                action()
            elif time.monotonic()>deadline:
                errors.append('Timed out: '+action.__name__)
                finish()
            else:
                app.after(50,lambda:when(predicate,action,deadline))

        def capture(name):
            app.update_idletasks()
            ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),
                                app.winfo_rooty()+app.winfo_height())).save('docs/'+name+'.png')

        def cancel():
            observed['library_skip_button_present']=bool(app.scene.find_withtag('skip-scan'))
            capture('nexus-skip-scan-library-2.3.1')
            app.show_protection(game)
            observed['protection_skip_button_present']=bool(find(app.content,'Skip scan and play'))
            for _ in range(20):
                app.skip_scan_and_play(game)
            observed['one_dialog_for_repeated_requests']=len([w for w in app.winfo_children() if isinstance(w,ctk.CTkToplevel)])==1
            observed['no_launch_before_confirmation']=launch.call_count==0
            app.after(700,cancel_ready)

        def cancel_ready():
            observed['confirmation_buttons_visible']=all(button.winfo_ismapped() for button in buttons(app._skip_dialog))
            capture('nexus-skip-scan-confirmation-2.3.1')
            find(app._skip_dialog,'Cancel').invoke()
            app.after(250,close_window)

        def close_window():
            observed['cancel_never_launches']=launch.call_count==0
            app.skip_scan_and_play(game)
            app.tk.call(app._skip_dialog.protocol('WM_DELETE_WINDOW'))
            app.after(250,approve)

        def approve():
            observed['window_close_never_launches']=launch.call_count==0
            app.skip_scan_and_play(game)
            button=find(app._skip_dialog,'I understand')
            for _ in range(20):
                button.invoke()
            when(lambda:launch.call_count==1 and game.id in app._unscanned_launches,approved)

        def approved():
            observed['one_launch_after_repeated_confirmation']=launch.call_count==1
            observed['launch_uses_standard_user_helper']=launch.call_args.args==(target,)
            observed['scan_report_preserved']=app.results[game.id] is report and report.blocked
            observed['launch_marked_unverified']='NOT VERIFIED' in app.status_text.get()
            app.after(250,busy_download)

        def busy_download():
            app.busy=True
            app._active_scan_game_id=None
            app.cancel_scan.clear()
            app.skip_scan_and_play(game)
            observed['unrelated_download_not_interrupted']=launch.call_count==1 and not app.cancel_scan.is_set()
            app.busy=False
            cancel_current_scan()

        def cancel_current_scan():
            app.busy=True
            app._active_scan_game_id=game.id
            app.cancel_scan.clear()
            app.skip_scan_and_play(game)
            find(app._skip_dialog,'I understand').invoke()
            observed['current_scan_cancel_requested']=app.cancel_scan.is_set()
            observed['waits_for_scan_to_stop_before_launch']=launch.call_count==1
            app.after(180,scan_stopped)

        def scan_stopped():
            app._active_scan_game_id=None
            app.busy=False
            when(lambda:launch.call_count==2,finish)

        finished=False
        def finish():
            nonlocal finished
            if finished:
                return
            finished=True
            observed['no_scanner_or_hashing_on_override']=scanner.call_count==0 and hashing.call_count==0 and save.call_count==0
            observed.update(callback_errors=errors,real_games_launched=0)
            app.motion.clear()
            app.destroy()

        with patch('nexus_repacks.app.launch_executable') as launch, \
             patch('nexus_repacks.app.Scanner') as scanner, \
             patch('nexus_repacks.app.sha256') as hashing, \
             patch('nexus_repacks.app.save_verified') as save:
            app.after(650,cancel)
            app.mainloop()
        Path('docs/nexus-unverified-launch-verification.json').write_text(json.dumps(observed,indent=2),encoding='utf-8')
        assert not errors,observed
        for key,value in observed.items():
            if key not in ('callback_errors','real_games_launched'):
                assert value,observed
        print(json.dumps(observed,indent=2))


if __name__=='__main__':
    main()
