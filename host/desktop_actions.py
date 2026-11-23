"""Fixed, session-scoped desktop actions; no shell commands supplied by the web."""
import ctypes
import os
from pathlib import Path
import subprocess
import winreg
import threading


class ScaleSnapshot(ctypes.Structure):
    _fields_=[('adapter_low',ctypes.c_uint32),('adapter_high',ctypes.c_int32),('source',ctypes.c_uint32),('relative',ctypes.c_int32)]


class DesktopActions:
    def __init__(self,native_path):
        self.native_path=native_path
        self.original_scale=None
        self.lock=threading.Lock()

    def scale_api(self):
        dll=ctypes.CDLL(str(self.native_path))
        dll.rc_set_scale125.restype=ctypes.c_uint
        for name in ('rc_save_scale','rc_restore_scale'):
            function=getattr(dll,name);function.argtypes=[ctypes.POINTER(ScaleSnapshot)];function.restype=ctypes.c_uint
        return dll

    @staticmethod
    def chrome_path():
        candidates=[]
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') as key:
                    candidates.append(Path(winreg.QueryValue(key,None).strip('"')))
            except OSError:pass
        for root in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
            if os.environ.get(root):candidates.append(Path(os.environ[root])/'Google/Chrome/Application/chrome.exe')
        for path in candidates:
            if path.is_file():return str(path)
        raise RuntimeError('Google Chrome est introuvable sur le PC hôte.')

    def launch(self,action):
        if action=='cmd':
            subprocess.Popen([str(Path(os.environ['SYSTEMROOT'])/'System32/cmd.exe')],creationflags=subprocess.CREATE_NEW_CONSOLE)
        elif action in ('chrome','classroom'):
            url='https://classroom.google.com/' if action=='classroom' else 'chrome://newtab/'
            subprocess.Popen([self.chrome_path(),'--new-window',url])
        else:raise ValueError('Action non autorisée')

    def prepare(self):
        with self.lock:return self._prepare()

    def _prepare(self):
        errors=[]
        try:
            dll=self.scale_api()
            if self.original_scale is None:
                saved=ScaleSnapshot();code=dll.rc_save_scale(ctypes.byref(saved))
                if code:raise RuntimeError(f'Impossible de mémoriser l’échelle Windows (erreur {code}).')
                self.original_scale=saved
            code=dll.rc_set_scale125()
            if code:raise RuntimeError(f'Windows a refusé le réglage 125 % (erreur {code}).')
        except Exception as exc:errors.append(str(exc))
        try:self.launch('chrome')
        except Exception as exc:errors.append(str(exc))
        return errors

    def restore(self):
        with self.lock:
            if self.original_scale is None:return []
            try:
                code=self.scale_api().rc_restore_scale(ctypes.byref(self.original_scale))
                if code:raise RuntimeError(f'Restauration de l’échelle Windows refusée (erreur {code}).')
                self.original_scale=None
                return []
            except Exception as exc:return [str(exc)]
