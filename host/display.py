import ctypes as c
from ctypes import wintypes as w
import socket

class DEVMODE(c.Structure):
    _fields_=[('name',w.WCHAR*32),('spec',w.WORD),('driver',w.WORD),('size',w.WORD),('extra',w.WORD),
              ('fields',w.DWORD),('display_union',w.BYTE*16),('color',w.SHORT),('duplex',w.SHORT),
              ('yres',w.SHORT),('tt',w.SHORT),('collate',w.SHORT),('form',w.WCHAR*32),('logpixels',w.WORD),
              ('bits',w.DWORD),('width',w.DWORD),('height',w.DWORD),('flags',w.DWORD),('frequency',w.DWORD),
              ('icm',w.DWORD),('intent',w.DWORD),('media',w.DWORD),('dither',w.DWORD),('res1',w.DWORD),('res2',w.DWORD),
              ('panw',w.DWORD),('panh',w.DWORD)]

def display_info():
    mode=DEVMODE();mode.size=c.sizeof(mode)
    if not c.windll.user32.EnumDisplaySettingsW(None,0xffffffff,c.byref(mode)):
        return dict(width=0,height=0,refresh_hz=0)
    return dict(width=mode.width,height=mode.height,refresh_hz=mode.frequency)

def lan_addresses():
    addresses=set()
    try:
        for result in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            ip=result[4][0]
            if not ip.startswith(('127.','169.254.')):addresses.add(ip)
    except OSError:pass
    return sorted(addresses)
