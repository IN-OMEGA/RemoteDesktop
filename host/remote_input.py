import ctypes as c
from ctypes import wintypes as w
import time


class MOUSEINPUT(c.Structure):
    _fields_=[('dx',w.LONG),('dy',w.LONG),('mouseData',w.DWORD),('dwFlags',w.DWORD),('time',w.DWORD),('dwExtraInfo',c.c_size_t)]
class KEYBDINPUT(c.Structure):
    _fields_=[('wVk',w.WORD),('wScan',w.WORD),('dwFlags',w.DWORD),('time',w.DWORD),('dwExtraInfo',c.c_size_t)]
class HARDWAREINPUT(c.Structure):
    _fields_=[('uMsg',w.DWORD),('wParamL',w.WORD),('wParamH',w.WORD)]
class UNION(c.Union):
    _fields_=[('mi',MOUSEINPUT),('ki',KEYBDINPUT),('hi',HARDWAREINPUT)]
class INPUT(c.Structure):
    _anonymous_=('u',)
    _fields_=[('type',w.DWORD),('u',UNION)]
user=c.WinDLL('user32',use_last_error=True)
user.SendInput.argtypes=[w.UINT,c.POINTER(INPUT),c.c_int]
user.SendInput.restype=w.UINT
SCANS={'Escape':1,'Digit1':2,'Digit2':3,'Digit3':4,'Digit4':5,'Digit5':6,'Digit6':7,'Digit7':8,'Digit8':9,'Digit9':10,'Digit0':11,
 'Minus':12,'Equal':13,'Backspace':14,'Tab':15,'KeyQ':16,'KeyW':17,'KeyE':18,'KeyR':19,'KeyT':20,'KeyY':21,'KeyU':22,'KeyI':23,'KeyO':24,'KeyP':25,
 'BracketLeft':26,'BracketRight':27,'Enter':28,'ControlLeft':29,'KeyA':30,'KeyS':31,'KeyD':32,'KeyF':33,'KeyG':34,'KeyH':35,'KeyJ':36,'KeyK':37,'KeyL':38,
 'Semicolon':39,'Quote':40,'Backquote':41,'ShiftLeft':42,'Backslash':43,'KeyZ':44,'KeyX':45,'KeyC':46,'KeyV':47,'KeyB':48,'KeyN':49,'KeyM':50,
 'Comma':51,'Period':52,'Slash':53,'ShiftRight':54,'AltLeft':56,'Space':57,'CapsLock':58,
 'F1':59,'F2':60,'F3':61,'F4':62,'F5':63,'F6':64,'F7':65,'F8':66,'F9':67,'F10':68,'F11':87,'F12':88,
 'ArrowUp':0x148,'ArrowDown':0x150,'ArrowLeft':0x14b,'ArrowRight':0x14d,'Delete':0x153,'Insert':0x152,'Home':0x147,'End':0x14f,'PageUp':0x149,'PageDown':0x151,
 'ControlRight':0x11d,'AltRight':0x138,'MetaLeft':0x15b,'MetaRight':0x15c,
 'IntlBackslash':86,'IntlRo':0x73,'IntlYen':0x7d,'ContextMenu':0x15d,
 'NumLock':0x145,'ScrollLock':70,'PrintScreen':0x137,
 'Numpad0':82,'Numpad1':79,'Numpad2':80,'Numpad3':81,'Numpad4':75,'Numpad5':76,
 'Numpad6':77,'Numpad7':71,'Numpad8':72,'Numpad9':73,'NumpadDecimal':83,
 'NumpadAdd':78,'NumpadSubtract':74,'NumpadMultiply':55,'NumpadDivide':0x135,'NumpadEnter':0x11c}
VIRTUAL_KEYS={'Pause':0x13,'AudioVolumeMute':0xad,'AudioVolumeDown':0xae,'AudioVolumeUp':0xaf,
 'MediaTrackNext':0xb0,'MediaTrackPrevious':0xb1,'MediaStop':0xb2,'MediaPlayPause':0xb3,
 'BrowserBack':0xa6,'BrowserForward':0xa7,'BrowserRefresh':0xa8,'BrowserStop':0xa9,
 'BrowserSearch':0xaa,'BrowserFavorites':0xab,'BrowserHome':0xac,'LaunchMail':0xb4,
 'MediaSelect':0xb5,'LaunchApp1':0xb6,'LaunchApp2':0xb7,
 **{f'F{number}':0x70+number-1 for number in range(13,25)}}


class RemoteInput:
    def __init__(self,state):
        self.state=state
        self.keys=set()
        self.logical_keys=set()
        self.buttons=set()
        self.last=time.monotonic()
        self.window=time.monotonic()
        self.count=0
        self.pad=None

    def send(self,item):
        if user.SendInput(1,c.byref(item),c.sizeof(INPUT))!=1:
            self.state.error('SendInput refusé : fenêtre élevée ou bureau sécurisé.')

    def key(self,code,down,repeat=False,logical=False):
        scan=SCANS.get(code)
        virtual=VIRTUAL_KEYS.get(code)
        logical=logical or code in self.logical_keys
        if logical and code.startswith('Key') and len(code)==4 and 'A'<=code[-1]<='Z':virtual=ord(code[-1]);scan=None
        elif logical and code.startswith('Digit') and len(code)==6 and '0'<=code[-1]<='9':virtual=ord(code[-1]);scan=None
        if scan is None and virtual is None:return
        if down and code in self.keys and not repeat:return
        if not down and code not in self.keys:return
        if scan is None:self.send(INPUT(type=1,ki=KEYBDINPUT(virtual,0,0 if down else 2,0,0)))
        else:self.send(INPUT(type=1,ki=KEYBDINPUT(0,scan&255,8|(1 if scan>255 else 0)|(0 if down else 2),0,0)))
        if down:
            self.keys.add(code)
            if logical:self.logical_keys.add(code)
        else:self.keys.discard(code);self.logical_keys.discard(code)

    def text(self,value):
        if not isinstance(value,str) or len(value)>2048:return
        raw=value.encode('utf-16-le',errors='surrogatepass')
        for offset in range(0,len(raw),2):
            unit=int.from_bytes(raw[offset:offset+2],'little')
            self.send(INPUT(type=1,ki=KEYBDINPUT(0,unit,4,0,0)))
            self.send(INPUT(type=1,ki=KEYBDINPUT(0,unit,4|2,0,0)))

    def release(self):
        for key in list(self.keys):self.key(key,False)
        for button in list(self.buttons):self.button(button,False)
        if self.pad:
            self.pad.reset();self.pad.update()

    def button(self,button,down):
        if button not in (0,1,2):return
        if down and button in self.buttons:return
        if not down and button not in self.buttons:return
        flags={0:(2,4),1:(32,64),2:(8,16)}[button][0 if down else 1]
        self.send(INPUT(type=0,mi=MOUSEINPUT(0,0,0,flags,0,0)))
        if down:self.buttons.add(button)
        else:self.buttons.discard(button)

    def event(self,event):
        if not self.state.control_allowed:return
        now=time.monotonic()
        if now-self.window>1:self.window,self.count=now,0
        self.count+=1
        if self.count>600:return
        self.last=now
        kind=event.get('type')
        if kind=='release':self.release()
        elif kind=='key':self.key(str(event.get('code')),bool(event.get('down')),bool(event.get('repeat',False)),bool(event.get('logical',False)))
        elif kind=='text':self.text(event.get('text'))
        elif kind=='keepalive':pass  # Only sent while the browser still owns and focuses its input surface.
        elif kind=='button':self.button(int(event.get('button',0)),bool(event.get('down')))
        elif kind=='move':
            x=max(0,min(1,float(event['x'])));y=max(0,min(1,float(event['y'])))
            self.send(INPUT(type=0,mi=MOUSEINPUT(round(x*65535),round(y*65535),0,0x8001,0,0)))
        elif kind=='wheel':
            amount=max(-1200,min(1200,int(event.get('delta',0))))
            self.send(INPUT(type=0,mi=MOUSEINPUT(0,0,amount&0xffffffff,0x0800,0,0)))
            horizontal=max(-1200,min(1200,int(event.get('horizontal',0))))
            if horizontal:self.send(INPUT(type=0,mi=MOUSEINPUT(0,0,horizontal&0xffffffff,0x1000,0,0)))
        elif kind=='gamepad':self.gamepad(event)

    def gamepad(self,event):
        # Optional real XInput virtual controller: only when the ViGEm driver is already installed.
        if self.pad is None:
            if self.state.gamepad_status.startswith('Indisponible'):return
            try:
                import vgamepad as vg
                self.pad=vg.VX360Gamepad()
                self.state.gamepad_status='XInput / ViGEm actif'
            except Exception as exc:
                self.state.gamepad_status='Indisponible : pilote ViGEmBus requis ('+str(exc)+')'
                return
        import vgamepad as vg
        axes=[max(-1,min(1,float(x))) for x in event.get('axes',[])[:4]]
        if len(axes)<4:return
        self.pad.left_joystick_float(x_value_float=axes[0],y_value_float=-axes[1])
        self.pad.right_joystick_float(x_value_float=axes[2],y_value_float=-axes[3])
        buttons=event.get('buttons',[])[:17]
        mapping={0:vg.XUSB_BUTTON.XUSB_GAMEPAD_A,1:vg.XUSB_BUTTON.XUSB_GAMEPAD_B,2:vg.XUSB_BUTTON.XUSB_GAMEPAD_X,3:vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
                 4:vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,5:vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
                 8:vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,9:vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
                 10:vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,11:vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
                 12:vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,13:vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,14:vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,15:vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT}
        for index,button in mapping.items():
            if index<len(buttons):
                (self.pad.press_button if buttons[index]>.5 else self.pad.release_button)(button=button)
        if len(buttons)>7:
            self.pad.left_trigger_float(value_float=max(0,min(1,float(buttons[6]))))
            self.pad.right_trigger_float(value_float=max(0,min(1,float(buttons[7]))))
        self.pad.update()
