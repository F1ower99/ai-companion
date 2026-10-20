from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def run_shell_script(code):
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    source_root = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
    with TemporaryDirectory() as local_app_data:
        env["LOCALAPPDATA"] = local_app_data
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            check=False,
        )


def test_lifecycle_subprocess_imports_companion_from_this_checkout():
    result = run_shell_script(
        "from companion.desktop import app; print(app.__file__)"
    )

    expected_source_root = Path(__file__).resolve().parents[2] / "src"
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve().is_relative_to(expected_source_root.resolve())


def test_application_construction_does_not_query_or_modify_startup():
    result = run_shell_script('''
from PySide6.QtCore import QTimer
from companion.desktop import startup_configuration
class GuardStore:
    def read(self):
        raise AssertionError('Unexpected startup registry read')
    def write(self, command):
        raise AssertionError('Unexpected startup registry write')
startup_configuration.WindowsStartupStore = GuardStore
startup_configuration.build_launch_command = lambda *args: 'expected'
from companion.desktop.app import create_application
app = create_application(['startup-lazy-test'])
assert app.tray_controller.startup_service is not None
QTimer.singleShot(0, app.quit)
raise SystemExit(app.exec())
''')
    assert result.returncode == 0, result.stderr


def test_app_event_loop_exits_when_pet_closes_without_system_tray():
    code = """
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QSystemTrayIcon

QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
from companion.desktop.app import create_application

app = create_application(["companion-lifecycle-test"])
assert not app.quitOnLastWindowClosed()
QTimer.singleShot(20, app.pet_window.close)
raise SystemExit(app.exec())
"""
    result = run_shell_script(code)

    assert result.returncode == 0, result.stderr


def test_closing_chat_keeps_pet_running_without_system_tray():
    code = """
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QSystemTrayIcon

QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
from companion.desktop.app import create_application

app = create_application(["companion-chat-close-test"])
app.chat_window.show()
QTimer.singleShot(20, app.chat_window.close)
def verify_pet_then_exit():
    assert app.pet_window.isVisible()
    print("pet-alive-after-chat-close", flush=True)
    app.pet_window.close()
QTimer.singleShot(50, verify_pet_then_exit)
raise SystemExit(app.exec())
"""
    result = run_shell_script(code)

    assert result.returncode == 0, result.stderr
    assert "pet-alive-after-chat-close" in result.stdout


def run_application_script(code, database_path):
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["AI_COMPANION_TEST_DB"] = str(database_path)
    env["LOCALAPPDATA"] = str(database_path.parent / "local-app-data")
    source_root = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )


def test_application_subprocess_uses_test_local_app_data(tmp_path):
    result = run_application_script(
        "from companion.infrastructure.sqlite.database import default_database_path; "
        "print(default_database_path())",
        tmp_path / "companion.sqlite3",
    )

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).is_relative_to(tmp_path)


def test_app_injects_local_database_and_task_service(tmp_path):
    code = '''
import os
from pathlib import Path
from companion.desktop.app import create_application
from companion.infrastructure.sqlite.database import SQLiteDatabase, default_database_path

seen = []
def factory(default_path):
    seen.append(default_path)
    return SQLiteDatabase(Path(os.environ["AI_COMPANION_TEST_DB"]))

app = create_application(["companion"], database_factory=factory)
assert seen == [default_database_path()]
assert app.chat_window.task_service is not None
assert app.chat_window.tasks_button.isEnabled()
assert Path(os.environ["AI_COMPANION_TEST_DB"]).exists()
app.pet_window.close()
'''
    result = run_application_script(code, tmp_path / "companion.sqlite3")
    assert result.returncode == 0, result.stderr


def test_app_holds_exclusive_lock_before_startup_recovery(tmp_path):
    code = '''
from PySide6.QtCore import QLockFile
from companion.desktop.app import create_application
from companion.infrastructure.sqlite.database import default_database_path

app = create_application(["companion-lock-test"])
lock_path = default_database_path().with_name("companion.instance.lock")
contender = QLockFile(str(lock_path))
assert app.instance_lock.isLocked()
assert not contender.tryLock(0)
app.pet_window.close()
'''
    result = run_application_script(code, tmp_path / "companion.sqlite3")
    assert result.returncode == 0, result.stderr


def test_second_app_instance_stops_before_database_recovery(tmp_path):
    code = '''
from PySide6.QtCore import QLockFile
from companion.desktop.app import create_application
from companion.infrastructure.sqlite.database import default_database_path

lock_path = default_database_path().with_name("companion.instance.lock")
lock_path.parent.mkdir(parents=True, exist_ok=True)
owner = QLockFile(str(lock_path))
assert owner.tryLock(0)
app = create_application(["companion-second-instance-test"])
assert app.startup_error == "AI Companion 已在运行；为保护本地对话，请使用已有窗口。"
assert not hasattr(app, "pet_window")
owner.unlock()
'''
    result = run_application_script(code, tmp_path / "companion.sqlite3")
    assert result.returncode == 0, result.stderr


def test_storage_failure_keeps_shell_running_with_safe_status(tmp_path):
    code = '''
from PySide6.QtWidgets import QSystemTrayIcon
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
from companion.domain.errors import StorageError
from companion.desktop.app import create_application

def fail_database_factory(path):
    raise StorageError("private-path-and-record-content")

app = create_application(["companion"], database_factory=fail_database_factory)
assert app.pet_window is not None and app.pet_window.isVisible()
assert app.chat_window is not None and not app.chat_window.isVisible()
assert app.chat_window.task_service is None
assert app.chat_window.tasks_button.isEnabled() is False
assert "本地数据" in app.chat_window.storage_status.text()
assert "private-path-and-record-content" not in app.chat_window.storage_status.text()
app.pet_window.close()
'''
    result = run_application_script(code, tmp_path / "unused.sqlite3")
    assert result.returncode == 0, result.stderr


def test_app_composes_disabled_activity_awareness_without_os_polling(tmp_path):
    code = '''
import os
from pathlib import Path
from companion.domain.reminders import ActivitySnapshot, ActivityState
from companion.infrastructure.sqlite.database import SQLiteDatabase
from companion.desktop import app as app_module

class FakeWindowsActivitySource:
    available = True
    instances = []
    def __init__(self):
        self.calls = 0
        self.resets = 0
        self.__class__.instances.append(self)
    def snapshot(self, at):
        self.calls += 1
        return ActivitySnapshot(ActivityState.FOCUSED, at, at)
    def reset(self):
        self.resets += 1

app_module.WindowsIdleActivitySource = FakeWindowsActivitySource
def factory(_default_path):
    return SQLiteDatabase(Path(os.environ["AI_COMPANION_TEST_DB"]))

app = app_module.create_application(["companion-stage6-test"], database_factory=factory)
assert app.activity_awareness_service is app.reminder_service.activity
assert app.activity_awareness_service.get_preferences().enabled is False
assert FakeWindowsActivitySource.instances[0].calls == 0
app.reminder_scheduler.evaluate_now()
assert FakeWindowsActivitySource.instances[0].calls == 0
app.pet_window.close()
'''
    result = run_application_script(code, tmp_path / "stage6-app.sqlite3")
    assert result.returncode == 0, result.stderr
