"""Render real host dashboard pages against a live local server, then close cleanly."""
import asyncio
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import ImageGrab
from host.server import State,serve
from host.host_ui import HostUI

class Preview(HostUI):
    shots=0
    def poll(self):
        super().poll()
        self.shots+=1
        if self.shots==8:
            self.root.after(200,lambda:self.capture('overview'))
        if self.shots==12:
            self.select('connection');self.root.after(200,lambda:self.capture('connection'))
        if self.shots==16:
            self.select('display');self.root.after(200,lambda:self.capture('display'))
        if self.shots==20:self.quit()

    def capture(self,name):
        root=self.root
        ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save('test-results/nexus-host-'+name+'.png')

def main():
    state=State();ui=Preview(state,8082);stop=threading.Event();ui.stop_callback=stop.set
    thread=threading.Thread(target=lambda:asyncio.run(serve(state,ui,'127.0.0.1',8082,stop)),daemon=True)
    thread.start();ui.run();stop.set();thread.join(10)

if __name__=='__main__':main()
