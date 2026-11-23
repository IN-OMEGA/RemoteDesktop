"""Keep PyInstaller's private DLL directory out of external game processes."""
import ctypes
import os
import subprocess
import sys
from pathlib import Path

from nexus_repacks.desktop_user import is_elevated, launch_as_desktop_user, build_batch_command


def prepare_external_environment():
    if sys.platform == 'win32' and getattr(sys, 'frozen', False):
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    env = os.environ.copy()
    bundle = getattr(sys, '_MEIPASS', '')
    if bundle:
        env['PATH'] = os.pathsep.join(p for p in env.get('PATH', '').split(os.pathsep)
                                     if not os.path.normcase(p).startswith(os.path.normcase(bundle)))
    return env


def launch_executable(target):
    if is_elevated():
        prepare_external_environment()
        return launch_as_desktop_user(target, subprocess.list2cmdline([str(target)]), target.parent)
    return subprocess.Popen([str(target)], cwd=str(target.parent), shell=False,
                            env=prepare_external_environment())


def launch_batch(target):
    prepare_external_environment()
    if is_elevated():
        system_path = ctypes.create_unicode_buffer(32768)
        if not ctypes.windll.kernel32.GetSystemDirectoryW(system_path, len(system_path)):
            raise ctypes.WinError()
        command_processor = Path(system_path.value) / 'cmd.exe'
        return launch_as_desktop_user(command_processor, build_batch_command(command_processor, target), target.parent)
    os.startfile(str(target), cwd=str(target.parent))
