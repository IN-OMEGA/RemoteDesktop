"""Only succeeds when a virtual XInput controller is really visible to Windows."""
import ctypes as c
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

def main():
    result={}
    try:
        import vgamepad as vg
        class Gamepad(c.Structure):
            _fields_=[('buttons',c.c_ushort),('left_trigger',c.c_ubyte),('right_trigger',c.c_ubyte),
                      ('lx',c.c_short),('ly',c.c_short),('rx',c.c_short),('ry',c.c_short)]
        class State(c.Structure):_fields_=[('packet',c.c_uint),('gamepad',Gamepad)]
        pad=vg.VX360Gamepad()
        xinput=c.WinDLL('xinput1_4')
        state=State()
        pad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        pad.left_trigger_float(value_float=.5);pad.update()
        found=False
        for index in range(4):
            if xinput.XInputGetState(index,c.byref(state))==0:
                if state.gamepad.buttons&0x1000 and state.gamepad.left_trigger>100:found=True
        pad.reset();pad.update()
        result={'verified':found}
    except Exception as exc:result={'verified':False,'error':str(exc)}
    Path('test-results/gamepad.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(result)

if __name__=='__main__':main()
