"""Persistent connection code, encrypted for the current Windows account with DPAPI."""
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import re
import secrets
import tempfile


class Blob(c.Structure):
    _fields_=[('size',w.DWORD),('data',c.POINTER(c.c_ubyte))]


def crypt(data,unprotect=False):
    api=c.WinDLL('crypt32',use_last_error=True)
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[c.c_void_p];kernel.LocalFree.restype=c.c_void_p
    buffer=c.create_string_buffer(data)
    source=Blob(len(data),c.cast(buffer,c.POINTER(c.c_ubyte)));output=Blob()
    if unprotect:
        fn=api.CryptUnprotectData
        fn.argtypes=[c.POINTER(Blob),c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p,w.DWORD,c.POINTER(Blob)]
        args=(c.byref(source),None,None,None,None,1,c.byref(output))
    else:
        fn=api.CryptProtectData
        fn.argtypes=[c.POINTER(Blob),w.LPCWSTR,c.c_void_p,c.c_void_p,c.c_void_p,w.DWORD,c.POINTER(Blob)]
        args=(c.byref(source),'Nexus View connection code',None,None,None,1,c.byref(output))
    fn.restype=w.BOOL
    if not fn(*args):raise c.WinError(c.get_last_error())
    try:return c.string_at(output.data,output.size)
    finally:kernel.LocalFree(c.cast(output.data,c.c_void_p))


class CodeStore:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else Path(os.environ['LOCALAPPDATA'])/'NexusView'/'connection-code.bin'

    @staticmethod
    def validate(code):
        if not isinstance(code,str) or not re.fullmatch(r'[A-Za-z0-9_-]{24}',code):
            raise ValueError('Code de connexion enregistré invalide.')
        return code

    def load_or_create(self,initial_code=None):
        if self.path.exists():
            # Never silently replace an unreadable/corrupt code.
            return self.validate(crypt(self.path.read_bytes(),unprotect=True).decode('ascii'))
        code=self.validate(initial_code if initial_code is not None else secrets.token_urlsafe(18))
        data=crypt(code.encode('ascii'))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with self.path.open('xb') as file:
                file.write(data);file.flush();os.fsync(file.fileno())
        except FileExistsError:return self.load_or_create()
        return code

    def replace(self,code):
        data=crypt(self.validate(code).encode('ascii'))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent,delete=False) as file:
                temporary=Path(file.name)
                file.write(data);file.flush();os.fsync(file.fileno())
            os.replace(temporary,self.path)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
