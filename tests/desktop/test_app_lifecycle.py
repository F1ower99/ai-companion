from __future__ import annotations

import os
import subprocess
import sys


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
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=4,
        check=False,
    )

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
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=4,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "pet-alive-after-chat-close" in result.stdout
