"""Resolve only a hash-bound adjacent first-party worker ZIP in compiled apps."""
import hashlib
from pathlib import Path
import stat
import sys

from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure._qwen_worker_manifest import WORKER_BUNDLE_SHA256
from companion.infrastructure.tts_assets import _local

MAX_BUNDLE_BYTES = 1024 * 1024
BUNDLE_NAME = 'companion-qwen-worker.zip'


def worker_import_path(*, compiled=None, executable=None, expected_digest=None):
    if compiled is None:
        compiled = getattr(sys, 'frozen', False) or '__compiled__' in globals()
    if not compiled:
        return Path(__file__).resolve().parents[2]
    try:
        digest = WORKER_BUNDLE_SHA256 if expected_digest is None else expected_digest
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('Unprepared build.')
        path = Path(sys.executable if executable is None else executable).parent / BUNDLE_NAME
        if not path.is_absolute() or not _local(path):
            raise ValueError('Local fixed bundle required.')
        for ancestor in reversed((path, *path.parents)):
            if (ancestor.is_symlink()
                    or getattr(ancestor.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError('Linked path.')
        path = path.resolve(strict=True)
        if not _local(path) or not path.is_file() or not 0 < path.stat().st_size <= MAX_BUNDLE_BYTES:
            raise ValueError('Invalid bundle.')
        with path.open('rb') as stream:
            data = stream.read(MAX_BUNDLE_BYTES + 1)
        if len(data) > MAX_BUNDLE_BYTES or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Bundle integrity mismatch.')
        return path
    except (OSError, ValueError, RuntimeError):
        raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED) from None
