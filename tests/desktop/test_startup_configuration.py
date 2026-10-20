import ast
from pathlib import Path
import subprocess

import pytest

from companion.application.startup import StartupError
from companion.desktop.startup_configuration import build_launch_command, build_startup_service


def test_source_command_preserves_quoted_path_without_inheriting_argv(monkeypatch):
    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    source = Path("C:/A B's & Companion/src")
    captured = []
    original = subprocess.list2cmdline
    def capture(args):
        captured.extend(args)
        return original(args)
    monkeypatch.setattr(subprocess, 'list2cmdline', capture)
    monkeypatch.setattr('sys.argv', ['app', 'private-secret'])
    command = build_launch_command(Path('C:/Python Space/pythonw.exe'), source)
    assert captured[0] == str(Path('C:/Python Space/pythonw.exe'))
    assert captured[1] == '-c' and len(captured) == 3
    tree = ast.parse(captured[2])
    insertion = tree.body[1].value
    assert ast.literal_eval(insertion.args[1]) == str(source)
    assert 'private-secret' not in command and len(command) <= 260


def test_compiled_command_has_only_executable(monkeypatch):
    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    assert build_launch_command(Path('C:/Program Files/Companion/app.exe')) == '"C:\\Program Files\\Companion\\app.exe"'


def test_missing_runtime_overlong_path_or_relative_path_is_unavailable(monkeypatch):
    with pytest.raises(StartupError):
        build_launch_command(Path('relative.exe'))
    monkeypatch.setattr(Path, 'is_file', lambda self: False)
    with pytest.raises(StartupError):
        build_launch_command(Path('C:/missing.exe'))
    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    with pytest.raises(StartupError):
        build_launch_command(Path('C:/' + 'a' * 255 + '.exe'))


def test_composition_is_lazy_and_unsupported_platform_is_safe(monkeypatch):
    import companion.desktop.startup_configuration as module
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    assert build_startup_service() is None
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    monkeypatch.setattr(module, 'build_launch_command', lambda *args: 'expected')
    class Store:
        def read(self):
            raise AssertionError('Registry must stay lazy')
    monkeypatch.setattr(module, 'WindowsStartupStore', Store)
    assert build_startup_service() is not None


@pytest.mark.parametrize('marker', ['nuitka', 'frozen'])
def test_compiled_composition_does_not_use_pythonw_or_source_bootstrap(monkeypatch, marker):
    import companion.desktop.startup_configuration as module
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    monkeypatch.setattr(module.sys, 'executable', 'C:/Companion/app.exe')
    if marker == 'nuitka':
        monkeypatch.setattr(module, '__compiled__', object(), raising=False)
    else:
        monkeypatch.setattr(module.sys, 'frozen', True, raising=False)
    seen = []
    monkeypatch.setattr(module, 'build_launch_command', lambda *args: (seen.append(args), 'expected')[1])
    assert build_startup_service() is not None
    assert seen == [(Path('C:/Companion/app.exe'),)]
