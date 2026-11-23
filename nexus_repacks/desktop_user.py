"""Launch games with the interactive desktop user's non-elevated token.

An elevated Nexus must never silently elevate downloaded game code.
"""
import ctypes
import os
import subprocess
from ctypes import wintypes as w


class StartupInfo(ctypes.Structure):
    _fields_ = [('cb', w.DWORD), ('lpReserved', w.LPWSTR), ('lpDesktop', w.LPWSTR),
        ('lpTitle', w.LPWSTR), ('dwX', w.DWORD), ('dwY', w.DWORD), ('dwXSize', w.DWORD),
        ('dwYSize', w.DWORD), ('dwXCountChars', w.DWORD), ('dwYCountChars', w.DWORD),
        ('dwFillAttribute', w.DWORD), ('dwFlags', w.DWORD), ('wShowWindow', w.WORD),
        ('cbReserved2', w.WORD), ('lpReserved2', ctypes.POINTER(ctypes.c_ubyte)),
        ('hStdInput', w.HANDLE), ('hStdOutput', w.HANDLE), ('hStdError', w.HANDLE)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [('hProcess', w.HANDLE), ('hThread', w.HANDLE),
                ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD)]


def is_elevated():
    if os.name != 'nt':
        return False
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def build_batch_command(command_processor, target):
    target = str(target)
    if any(c in target for c in '%\r\n"'):
        raise ValueError('The batch path contains characters incompatible with a secure launch.')
    return f'"{command_processor}" /d /v:off /s /c ""{target}""'


def launch_as_desktop_user(application, command_line, cwd):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user = ctypes.WinDLL('user32', use_last_error=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    userenv = ctypes.WinDLL('userenv', use_last_error=True)
    user.GetShellWindow.argtypes = []
    user.GetShellWindow.restype = w.HWND
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetWindowThreadProcessId.restype = w.DWORD
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    advapi.OpenProcessToken.restype = w.BOOL
    advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    advapi.GetTokenInformation.restype = w.BOOL
    advapi.DuplicateTokenEx.argtypes = [w.HANDLE, w.DWORD, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(w.HANDLE)]
    advapi.DuplicateTokenEx.restype = w.BOOL
    userenv.CreateEnvironmentBlock.argtypes = [ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.BOOL]
    userenv.CreateEnvironmentBlock.restype = w.BOOL
    userenv.DestroyEnvironmentBlock.argtypes = [ctypes.c_void_p]
    userenv.DestroyEnvironmentBlock.restype = w.BOOL
    advapi.CreateProcessWithTokenW.argtypes = [w.HANDLE, w.DWORD, w.LPCWSTR, w.LPWSTR, w.DWORD,
        ctypes.c_void_p, w.LPCWSTR, ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)]
    advapi.CreateProcessWithTokenW.restype = w.BOOL
    shell = user.GetShellWindow()
    if not shell:
        raise RuntimeError('Standard Windows desktop not found: no game will be launched as administrator.')
    pid = w.DWORD()
    user.GetWindowThreadProcessId(shell, ctypes.byref(pid))
    process = kernel.OpenProcess(0x1000, False, pid.value)
    token, primary = w.HANDLE(), w.HANDLE()
    environment = ctypes.c_void_p()
    info = ProcessInfo()
    try:
        if not process or not advapi.OpenProcessToken(process, 0x0008 | 0x0002, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        elevation, length = w.DWORD(), w.DWORD()
        if not advapi.GetTokenInformation(token, 20, ctypes.byref(elevation), ctypes.sizeof(elevation), ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        if elevation.value:
            raise RuntimeError('The desktop is elevated: repack launch refused to avoid granting administrator rights.')
        if not advapi.DuplicateTokenEx(token, 0x02000000, None, 2, 1, ctypes.byref(primary)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not userenv.CreateEnvironmentBlock(ctypes.byref(environment), primary, False):
            raise ctypes.WinError(ctypes.get_last_error())
        startup = StartupInfo()
        startup.cb = ctypes.sizeof(startup)
        startup.lpDesktop = 'winsta0\\default'
        buffer = ctypes.create_unicode_buffer(command_line)
        if not advapi.CreateProcessWithTokenW(primary, 1, str(application), buffer, 0x00000400,
                environment, str(cwd), ctypes.byref(startup), ctypes.byref(info)):
            error = ctypes.get_last_error()
            raise OSError(error, 'Cannot launch the game without elevation: ' + str(ctypes.WinError(error)))
        return info.dwProcessId
    finally:
        if environment:
            userenv.DestroyEnvironmentBlock(environment)
        for handle in (info.hThread, info.hProcess, primary, token, process):
            if handle:
                kernel.CloseHandle(handle)
