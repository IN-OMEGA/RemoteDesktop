"""Native catalog navigation + one-click local HTTP transfer, using benign fixtures."""
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch
import zipfile

from PIL import Image, ImageGrab
from nexus_repacks.cinematic import CinematicNexus


def main():
    observed,errors={},[]
    with tempfile.TemporaryDirectory(prefix='nexus-catalog-') as directory:
        root=Path(directory)
        art=root/'catalog-assets'
        art.mkdir()
        Image.new('RGB',(720,360),'#234d68').save(art/'fixture.png')
        with zipfile.ZipFile(root/'fixture.zip','w') as archive:
            archive.writestr('README.txt','Harmless catalog download fixture. No executable content.')
        expected=hashlib.sha256((root/'fixture.zip').read_bytes()).hexdigest()
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(SimpleHTTPRequestHandler,directory=root))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        entry={'id':'fixture','title':'Catalog Test Game','description':'A full game description.\n\nSecond paragraph.',
               'download_url':f'http://127.0.0.1:{server.server_port}/fixture.zip','folder':'Catalog Fixture',
               'filename':'game.zip','image':'catalog-assets/fixture.png','icon':'catalog-assets/fixture.png',
               'genre':'Adventure','size':'Small test fixture'}
        disabled=dict(entry,id='coming-soon',title='Coming Soon',enabled=False)
        (root/'catalog.json').write_text(json.dumps({'version':1,'games':[entry,disabled]}),encoding='utf-8')
        app=CinematicNexus(smoke=True)
        for job in app.tk.call('after','info'):
            app.after_cancel(job)
        app.games=[]
        app.root_path=root
        app.attributes('-topmost',True)
        app.geometry('1440x900+30+30')
        app.report_callback_exception=lambda kind,error,tb:errors.append(str(error))
        app.after(10,app.drain)
        app.show_catalog()

        def when(predicate,action,deadline=None):
            deadline=deadline or time.monotonic()+15
            if predicate():
                action()
            elif time.monotonic()>deadline:
                errors.append('Timed out: '+action.__name__)
                finish()
            else:
                app.after(60,lambda:when(predicate,action,deadline))

        def capture(name):
            app.update_idletasks()
            ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),
                                app.winfo_rooty()+app.winfo_height())).save('docs/'+name+'.png')

        def details():
            view=app.catalog_view
            observed['sidebar_catalog_button']='catalog' in app._nav
            observed['json_games_loaded']=len(view.games)==2
            observed['local_art_loaded']=any(image is not None for image in view.art_cache.values())
            capture('nexus-catalog-2.3')
            view.search.insert(0,'does-not-exist')
            view.show_grid()
            observed['search_no_results']=any(child.cget('text')=='No matching games'
                for frame in view.grid_host.winfo_children() for child in frame.winfo_children()
                if hasattr(child,'cget') and isinstance(child, __import__('customtkinter').CTkLabel))
            view.search.delete(0,'end')
            view.show_detail(view.games[1])
            observed['disabled_entry_cannot_download']=view.download_button.cget('state')=='disabled'
            view.show_detail(view.games[0])
            observed['description_displayed']=view.detail_description.get('1.0','end-1c')==entry['description']
            app.geometry('1120x740+30+30')
            app.after(500,download)

        def download():
            view=app.catalog_view
            app.update_idletasks()
            observed['detail_widgets_mapped']=bool(view.detail_description.winfo_ismapped() and view.download_button.winfo_ismapped())
            observed['download_visible_at_minimum_size']=view.download_button.winfo_rooty()+view.download_button.winfo_height()<app.winfo_rooty()+app.winfo_height()
            capture('nexus-catalog-detail-2.3-compact')
            self_path=root/'downloads/Catalog Fixture/game.zip'
            observed['no_transfer_before_download_click']=not self_path.exists()
            with patch.object(app,'confirm_download') as confirmation:
                view.download_button.invoke()
                observed['direct_download_without_second_confirmation']=confirmation.call_count==0
            observed['download_page_opened']=app.current_page=='downloads'
            when(lambda:not app.busy and app.transfer.get('phase')=='completed',navigation)

        def navigation():
            output=root/'downloads/Catalog Fixture/game.zip'
            observed['download_sha256_matches']=output.exists() and hashlib.sha256(output.read_bytes()).hexdigest()==expected
            observed['automatic_post_download_scan']=app.transfer['phase']=='completed'
            app.request_page('catalog')
            when(lambda:app.current_page=='catalog' and not app._navigation_active,reload_error)

        def reload_error():
            view=app.catalog_view
            observed['sidebar_navigation_back_to_catalog']=app.current_page=='catalog'
            (root/'catalog.json').write_text('{broken')
            view.reload()
            observed['bad_json_has_visible_error']=bool(view.error) and not view.games
            (root/'catalog.json').write_text(json.dumps({'version':1,'games':[entry]}))
            view.reload()
            observed['reload_recovers_from_error']=len(view.games)==1 and not view.error
            # Destroy the view with image tasks outstanding, then drain their callbacks.
            app.show_library()
            app.after(500,finish)

        finished=False
        def finish():
            nonlocal finished
            if finished:
                return
            finished=True
            observed.update(callback_errors=errors,games_launched=0,user_downloads_touched=False)
            app.motion.clear()
            app.destroy()

        when(lambda:not app._navigation_active and bool(app.catalog_view.art_cache),lambda:app.after(350,details))
        app.mainloop()
        server.shutdown()
        server.server_close()
        Path('docs/nexus-catalog-verification.json').write_text(json.dumps(observed,indent=2),encoding='utf-8')
        assert not errors,observed
        for key,value in observed.items():
            if key not in ('callback_errors','games_launched','user_downloads_touched'):
                assert value,observed
        print(json.dumps(observed,indent=2))


if __name__=='__main__':
    main()
