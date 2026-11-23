"""DPI snapshot/restore and delayed preparation cancellation; no real DPI/app changes."""
import asyncio
import ctypes
from pathlib import Path
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from host.desktop_actions import DesktopActions,ScaleSnapshot
from host.server import State

class Api:
    relative=-1
    fail_restore=False
    def rc_save_scale(self,p):ctypes.cast(p,ctypes.POINTER(ScaleSnapshot)).contents.relative=self.relative;return 0
    def rc_set_scale125(self):self.relative=0;return 0
    def rc_restore_scale(self,p):
        if self.fail_restore:return 5
        self.relative=ctypes.cast(p,ctypes.POINTER(ScaleSnapshot)).contents.relative;return 0

async def main():
    api=Api();actions=DesktopActions('unused');actions.scale_api=lambda:api
    launches=[];actions.launch=launches.append
    assert actions.restore()==[] and api.relative==-1
    assert actions.prepare()==[] and api.relative==0
    api.fail_restore=True;assert actions.restore() and actions.original_scale is not None
    api.fail_restore=False;assert actions.restore()==[] and api.relative==-1
    assert actions.restore()==[] and launches==['chrome']
    # Disconnect waits for an already-running preparation before restoring its snapshot.
    entered=threading.Event()
    original=actions.prepare
    def slow_prepare():entered.set();time.sleep(.12);return original()
    actions.prepare=slow_prepare
    state=State();state.desktop_actions=actions;state.setup_desktop=True;state.session_id='real-person-test'
    task=asyncio.create_task(state.session_connected())
    await asyncio.to_thread(entered.wait)
    task.cancel();await state.disconnect()
    await asyncio.gather(task,return_exceptions=True)
    assert api.relative==-1 and actions.original_scale is None
    print('PASS: original DPI restored, failed restore retry, canceled setup cannot apply after disconnect.')

if __name__=='__main__':asyncio.run(main())
