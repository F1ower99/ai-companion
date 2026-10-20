"""Bounded local Kokoro bundle policy; no native runtime or device imports."""
from pathlib import Path
import sys
import unicodedata

from companion.domain.voice import VoiceErrorCode, VoiceOperationError

MAX_PCM_BYTES = 24000 * 2 * 60
HEADER_MAGIC = b'ACV1'
REQUIRED_FILES = ('model.int8.onnx', 'voices.bin', 'tokens.txt', 'lexicon-us-en.txt', 'lexicon-zh.txt',
                  'date-zh.fst', 'number-zh.fst', 'phone-zh.fst', 'espeak-ng-data/phontab',
                  'espeak-ng-data/phonindex', 'espeak-ng-data/phondata', 'espeak-ng-data/intonations')


def speech_text(text):
    if not isinstance(text, str) or len(text) > 8000 or any(
        unicodedata.category(char) in ('Cc', 'Cs') and char not in '\r\n\t' for char in text
    ):
        raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)
    text = ' '.join(text.split())
    if not 1 <= len(text) <= 200 or not any(char.isalnum() for char in text):
        raise VoiceOperationError(VoiceErrorCode.SPEECH_FAILED)
    return text


def _local(path):
    if str(path).startswith(('\\\\', '//')):
        return False
    if sys.platform != 'win32':
        return True
    import ctypes
    reader = ctypes.WinDLL('kernel32', use_last_error=True).GetDriveTypeW
    reader.argtypes, reader.restype = [ctypes.c_wchar_p], ctypes.c_uint
    return reader(path.anchor) in (2, 3, 5, 6)


def model_directory(directory):
    try:
        raw = str(directory)
        root = Path(raw)
        if '://' in raw or ',' in raw or not root.is_absolute() or not _local(root):
            raise ValueError('Local bundle required.')
        root = root.resolve(strict=True)
        if not _local(root) or not root.is_dir():
            raise ValueError('Local bundle required.')
        for name in REQUIRED_FILES:
            file = root / name
            file.resolve(strict=True).relative_to(root)
            if not file.is_file() or file.stat().st_size <= 0:
                raise ValueError('Incomplete bundle.')
        stack, files, directories, total = [root], 0, 0, 0
        while stack:
            directory = stack.pop()
            directories += 1
            if directories > 1000:
                raise ValueError('Excessive bundle.')
            for file in directory.iterdir():
                if file.is_symlink():
                    raise ValueError('Linked bundle entry.')
                file.resolve(strict=True).relative_to(root)
                if file.is_dir():
                    stack.append(file)
                else:
                    files += 1
                    total += file.stat().st_size
                    if files > 1000 or total > 256 * 1024 * 1024:
                        raise ValueError('Excessive bundle.')
        return root
    except (OSError, ValueError, RuntimeError):
        raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED) from None
