"""Session-scoped Unicode clipboard access. Clipboard contents are never logged."""
import ctypes as c
from ctypes import wintypes as w

MAX_BYTES=32768


def validate_text(value):
    if not isinstance(value,str) or '\0' in value or len(value.encode('utf-8'))>MAX_BYTES:
        raise ValueError('Texte du presse-papiers invalide ou supérieur à 32 Ko.')
    return value


class WindowsClipboard:
    def __init__(self):
        self.owner=None
        self.user=c.WinDLL('user32',use_last_error=True)
        self.kernel=c.WinDLL('kernel32',use_last_error=True)
        self.user.GetClipboardSequenceNumber.restype=w.DWORD
        self.user.OpenClipboard.argtypes=[w.HWND];self.user.OpenClipboard.restype=w.BOOL
        self.user.GetClipboardData.argtypes=[w.UINT];self.user.GetClipboardData.restype=w.HANDLE
        self.user.SetClipboardData.argtypes=[w.UINT,w.HANDLE];self.user.SetClipboardData.restype=w.HANDLE
        self.user.CreateWindowExW.argtypes=[w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,w.HWND,w.HMENU,w.HINSTANCE,c.c_void_p]
        self.user.CreateWindowExW.restype=w.HWND
        self.user.DestroyWindow.argtypes=[w.HWND]
        self.kernel.GlobalAlloc.argtypes=[w.UINT,c.c_size_t];self.kernel.GlobalAlloc.restype=w.HGLOBAL
        self.kernel.GlobalLock.argtypes=[w.HGLOBAL];self.kernel.GlobalLock.restype=c.c_void_p
        self.kernel.GlobalUnlock.argtypes=[w.HGLOBAL]
        self.kernel.GlobalSize.argtypes=[w.HGLOBAL];self.kernel.GlobalSize.restype=c.c_size_t
        self.kernel.GlobalFree.argtypes=[w.HGLOBAL];self.kernel.GlobalFree.restype=w.HGLOBAL

    def snapshot(self,since=None):
        sequence=str(self.user.GetClipboardSequenceNumber())
        result={'sequence':sequence,'text':None}
        if sequence==since or not self.user.IsClipboardFormatAvailable(13):return result
        if not self.user.OpenClipboard(None):raise OSError('Presse-papiers occupé. Réessayez.')
        try:
            handle=self.user.GetClipboardData(13)
            if not handle:return result
            size=self.kernel.GlobalSize(handle)
            if not size or size>2*(MAX_BYTES+1):return result
            pointer=self.kernel.GlobalLock(handle)
            if not pointer:raise OSError('Lecture du presse-papiers impossible.')
            try:text=c.string_at(pointer,size).decode('utf-16-le').split('\0',1)[0]
            finally:self.kernel.GlobalUnlock(handle)
            result['sequence']=str(self.user.GetClipboardSequenceNumber())
            try:result['text']=validate_text(text)
            except (ValueError,UnicodeError):pass
            return result
        finally:self.user.CloseClipboard()

    def set_text(self,text):
        validate_text(text)
        payload=(text+'\0').encode('utf-16-le')
        if not self.owner:
            self.owner=self.user.CreateWindowExW(0,'STATIC','Nexus Clipboard',0,0,0,0,0,w.HWND(-3),None,None,None)
            if not self.owner:raise OSError('Initialisation du presse-papiers impossible.')
        handle=self.kernel.GlobalAlloc(2,len(payload))
        if not handle:raise OSError('Allocation du presse-papiers impossible.')
        try:
            pointer=self.kernel.GlobalLock(handle)
            if not pointer:raise OSError('Allocation du presse-papiers impossible.')
            try:c.memmove(pointer,payload,len(payload))
            finally:self.kernel.GlobalUnlock(handle)
            if not self.user.OpenClipboard(self.owner):raise OSError('Presse-papiers occupé. Réessayez.')
            try:
                if not self.user.EmptyClipboard() or not self.user.SetClipboardData(13,handle):
                    raise OSError('Écriture du presse-papiers impossible.')
                handle=None  # Windows owns the allocation after successful transfer.
                return str(self.user.GetClipboardSequenceNumber())
            finally:self.user.CloseClipboard()
        finally:
            if handle:self.kernel.GlobalFree(handle)

    def close(self):
        if self.owner:self.user.DestroyWindow(self.owner);self.owner=None
