"""Verify SendInput only against a dedicated local test window."""
import ctypes
import json
from pathlib import Path
import sys
import time
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from host.remote_input import RemoteInput

class TestState:
    control_allowed=False
    gamepad_status='Non initialisé'
    errors=[]
    def error(self,message):self.errors.append(message)

def main():
    state=TestState();remote=RemoteInput(state)
    root=tk.Tk();root.title('RemoteCore — test isolé des commandes')
    root.geometry('450x180+200+200');root.attributes('-topmost',True)
    tk.Label(root,text='Vérification locale du clavier / souris…').pack(pady=15)
    entry=tk.Entry(root);entry.pack();entry.focus_force()
    clicks=[];wheel=[]
    entry.bind('<Button-1>',lambda e:clicks.append(1))
    entry.bind('<MouseWheel>',lambda e:wheel.append(e.delta))
    result={}
    def attempt():
        entry.focus_force()
        remote.event({'type':'key','code':'Space','down':True})
        remote.event({'type':'key','code':'Space','down':False})
        root.after(150,authorized)
    def authorized():
        result['unauthorized_input_blocked']=entry.get()==''
        state.control_allowed=True
        remote.event({'type':'key','code':'Space','down':True})
        remote.event({'type':'key','code':'Space','down':False})
        # Preserve and restore the physical cursor around the isolated click test.
        point=ctypes.wintypes.POINT();ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        result['_cursor']=(point.x,point.y)
        ctypes.windll.user32.SetCursorPos(entry.winfo_rootx()+20,entry.winfo_rooty()+10)
        remote.event({'type':'button','button':0,'down':True})
        remote.event({'type':'button','button':0,'down':False})
        remote.event({'type':'wheel','delta':120})
        root.after(250,unicode_input)
    def unicode_input():
        entry.delete(0,'end')
        remote.event({'type':'text','text':'Nexus été'})
        root.after(150,repeat_input)
    def repeat_input():
        result['unicode_text_received']=entry.get()=='Nexus été'
        remote.event({'type':'key','code':'Space','down':True})
        root.after(60,repeat_down)
    def repeat_down():
        remote.event({'type':'key','code':'Space','down':True,'repeat':True})
        root.after(60,repeat_up)
    def repeat_up():
        remote.event({'type':'key','code':'Space','down':False})
        root.after(150,finish)
    def finish():
        result['keyboard_repeat_received']=entry.get().endswith('  ')
        result['mouse_click_received']=bool(clicks)
        result['mouse_wheel_received']=bool(wheel)
        remote.release();result['keys_and_buttons_released']=not remote.keys and not remote.buttons
        result['errors']=state.errors
        ctypes.windll.user32.SetCursorPos(*result.pop('_cursor'))
        root.destroy()
    root.after(500,attempt);root.mainloop()
    Path('test-results/input.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(result)
    assert all(result[k] for k in ('unauthorized_input_blocked','unicode_text_received','keyboard_repeat_received','mouse_click_received','mouse_wheel_received','keys_and_buttons_released'))
    assert not result['errors']

if __name__=='__main__':main()
