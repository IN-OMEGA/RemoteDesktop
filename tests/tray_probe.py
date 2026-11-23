"""Check real close/minimize-to-tray lifecycle while the local server remains live."""
import asyncio
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from host.server import State,serve
from host.host_ui import HostUI

class Probe(HostUI):
    def poll(self):
        super().poll()
        if not hasattr(self,'testing') and self.tray_ready.is_set() and self.state.server_ready:
            self.testing=True
            self.root.tk.call(self.root.protocol('WM_DELETE_WINDOW'))
            self.root.after(250,self.check_closed)

    def check_closed(self):
        assert self.root.state()=='withdrawn' and self.state.server_ready and self.tray.visible
        self.show_window();self.root.after(250,self.minimize)

    def minimize(self):
        assert self.root.state()=='normal'
        self.root.iconify();self.root.after(350,self.check_minimized)

    def check_minimized(self):
        assert self.root.state()=='withdrawn' and self.state.server_ready and self.tray.visible
        print('PASS: close and minimize hide to tray; reopening works; server stays active.',flush=True)
        self.quit()

def main():
    state=State();ui=Probe(state,8082);stop=threading.Event();ui.stop_callback=stop.set
    thread=threading.Thread(target=lambda:asyncio.run(serve(state,ui,'127.0.0.1',8082,stop)),daemon=True)
    thread.start();ui.run();stop.set();thread.join(10)
    assert not state.server_ready

if __name__=='__main__':main()
