"""Muted native worker; stdout never becomes a log or an error message."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from threading import Event, Thread

from companion.infrastructure.tts_assets import MAX_PCM_BYTES

from companion.domain.voice import VoiceErrorCode, VoiceOperationError


def source_tts_supported():
    # Compiled desktop executables are not Python interpreters accepting -m.
    return not (getattr(sys, 'frozen', False) or '__compiled__' in globals())


def run_tts_worker(request, token, *, process_factory=subprocess.Popen, monotonic=time.monotonic):
    if token.is_cancelled():
        raise VoiceOperationError(VoiceErrorCode.CANCELLED)
    if not source_tts_supported():
        raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED)
    payload = json.dumps(request, ensure_ascii=True).encode('ascii')
    if len(payload) > 16384:
        raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)
    environment = os.environ.copy()
    source = str(Path(__file__).resolve().parents[2])
    environment['PYTHONPATH'] = source + os.pathsep + environment.get('PYTHONPATH', '')
    process = process_factory(
        [sys.executable, '-m', 'companion.infrastructure.tts_worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        shell=False, env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
    )
    received, failed, read_done, write_done = bytearray(), Event(), Event(), Event()
    limit = 12 + MAX_PCM_BYTES

    def receive():
        try:
            reader = getattr(process.stdout, 'read1', process.stdout.read)
            while True:
                # One sentinel byte detects overflow without accumulating it.
                chunk = reader(min(65536, limit - len(received) + 1))
                if not chunk:
                    break
                if len(received) + len(chunk) > limit:
                    failed.set()
                    break
                received.extend(chunk)
        except Exception:
            failed.set()
        finally:
            read_done.set()

    def send():
        try:
            process.stdin.write(payload)
            process.stdin.flush()
        except Exception:
            failed.set()
        finally:
            try:
                process.stdin.close()
            except Exception:
                failed.set()
            write_done.set()

    reader = Thread(target=receive, daemon=True)
    writer = Thread(target=send, daemon=True)
    deadline = monotonic() + 90
    try:
        reader.start()
        writer.start()
        while True:
            if token.is_cancelled():
                raise VoiceOperationError(VoiceErrorCode.CANCELLED)
            if failed.is_set() or monotonic() >= deadline:
                raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)
            code = process.poll()
            if code is not None and read_done.is_set() and write_done.is_set():
                if code != 0 or failed.is_set():
                    raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)
                return bytes(received)
            failed.wait(0.05)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for thread in (reader, writer):
            if thread.ident is not None:
                thread.join(timeout=5)
        process.stdout.close()
        received[:] = bytes(len(received))
        received.clear()
