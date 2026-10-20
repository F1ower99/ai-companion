"""Compose a launch command without registry access or inherited arguments."""
from pathlib import Path
import subprocess
import sys

from companion.application.startup import StartupError, StartupService, validate_command
from companion.infrastructure.windows_startup import WindowsStartupStore


def build_launch_command(executable: Path, source_root: Path | None = None) -> str:
    if not executable.is_absolute() or not executable.is_file():
        raise StartupError()
    arguments = [str(executable)]
    if source_root is not None:
        if not source_root.is_absolute() or not (source_root / 'companion/desktop/app.py').is_file():
            raise StartupError()
        bootstrap = (f'import sys;sys.path.insert(0,{str(source_root)!r});'
                     'from companion.desktop.app import main;raise SystemExit(main())')
        arguments += ['-c', bootstrap]
    return validate_command(subprocess.list2cmdline(arguments))


def build_startup_service() -> StartupService | None:
    if sys.platform != 'win32':
        return None
    try:
        compiled = '__compiled__' in globals() or getattr(sys, 'frozen', False)
        executable = Path(sys.executable)
        if compiled:
            command = build_launch_command(executable)
        else:
            command = build_launch_command(executable.with_name('pythonw.exe'), Path(__file__).resolve().parents[2])
        return StartupService(WindowsStartupStore(), command)
    except (OSError, ValueError, StartupError):
        return None
