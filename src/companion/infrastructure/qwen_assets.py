"""Pinned public Qwen assets and local paths; no torch, Qt or model loading."""
import hashlib
from pathlib import Path
import stat

from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure.tts_assets import _local

MODEL_REVISION = '0c0e3051f131929182e2c023b9537f8b1c68adfe'
# (repository-relative path, byte size, digest kind, pinned Git/LFS digest)
MODEL_ASSETS = (
    ('.gitattributes', 1519, 'git', 'a6344aac8c09253b3b630fb776ae94478aa0275b'),
    ('README.md', 57846, 'git', '7fbce7d50243a423bf0af98fe5b1b11453dbf38e'),
    ('config.json', 4908, 'git', '95d74b20b7485f5dfa09d05988d6c606ec226811'),
    ('generation_config.json', 245, 'git', '1872b16d4535564abf2db5d6debe6cddd82b7f2e'),
    ('merges.txt', 1671839, 'git', '20024bfe7c83998e9aeaf98a0cd6a2ce6306c2f0'),
    ('model.safetensors', 3833402552, 'sha256', '38b1d5971bdbd982b561cccec982669a53b0537c3cf5e9bd4778ed07bb2f5137'),
    ('preprocessor_config.json', 127, 'git', '0525dd953bb9241912f7147666f0d535165d5d4f'),
    ('speech_tokenizer/config.json', 2336, 'git', '06cc8dc4c5ec8a1929086b71b98c313020d9268b'),
    ('speech_tokenizer/configuration.json', 76, 'git', 'ab58e2eaf53cd14a1a2a7527d9261ceea93a24cd'),
    ('speech_tokenizer/model.safetensors', 682293092, 'sha256', '836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258'),
    ('speech_tokenizer/preprocessor_config.json', 234, 'git', 'ba40914f4f49ab98a8ca545d4892ef7291a39592'),
    ('tokenizer_config.json', 7344, 'git', '6ff9fd60cc623bb54bbd603cbd418c97a11528d7'),
    ('vocab.json', 2776833, 'git', '4783fe10ac3adce15ac8f358ef5462739852c569'),
)


def _fail():
    raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED) from None


def _linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0)
                                     & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _path(value):
    raw = str(value)
    path = Path(raw)
    if '://' in raw or not path.is_absolute() or not _local(path) or _linked(path):
        raise ValueError('Existing local path required.')
    resolved = path.resolve(strict=True)
    if not _local(resolved):
        raise ValueError('Existing local path required.')
    return resolved


def qwen_model_directory(directory):
    try:
        root = _path(directory)
        if not root.is_dir():
            raise ValueError('Directory required.')
        expected = {name: size for name, size, _, _ in MODEL_ASSETS}
        expected_dirs = {str(Path(name).parent).replace('\\', '/') for name in expected} - {'.'}
        seen, stack = set(), [root]
        while stack:
            current = stack.pop()
            for path in current.iterdir():
                if _linked(path):
                    raise ValueError('Linked bundle entry.')
                path.resolve(strict=True).relative_to(root)
                name = path.relative_to(root).as_posix()
                if path.is_dir():
                    if name not in expected_dirs:
                        raise ValueError('Unexpected directory.')
                    stack.append(path)
                elif (not path.is_file() or name not in expected
                      or path.stat().st_size != expected[name]):
                    raise ValueError('Unexpected or incomplete asset.')
                else:
                    seen.add(name)
        if seen != set(expected):
            raise ValueError('Incomplete bundle.')
        return root
    except (OSError, ValueError, RuntimeError):
        _fail()


def verify_qwen_model(directory):
    try:
        root = qwen_model_directory(directory)
        for name, size, kind, expected in MODEL_ASSETS:
            digest = hashlib.sha256() if kind == 'sha256' else hashlib.sha1(
                b'blob ' + str(size).encode('ascii') + b'\0')
            with (root / name).open('rb') as stream:
                while chunk := stream.read(4 * 1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError('Asset integrity mismatch.')
        return root
    except (OSError, ValueError, RuntimeError):
        _fail()


def runtime_python(executable):
    try:
        path = _path(executable)
        if not path.is_file() or path.name.lower() != 'python.exe' or path.parent.name != 'Scripts':
            raise ValueError('Explicit virtual environment Python required.')
        configuration = path.parent.parent / 'pyvenv.cfg'
        if _linked(configuration) or not configuration.is_file():
            raise ValueError('Virtual environment required.')
        return path
    except (OSError, ValueError, RuntimeError):
        _fail()


def work_directory(directory):
    try:
        root = _path(directory)
        if not root.is_dir():
            raise ValueError('Directory required.')
        for name in ('cache', 'cache/pycache', 'cache/huggingface', 'cache/torch', 'cache/numba',
                     'cache/cuda', 'tmp'):
            path = root / name
            if path.exists() and (_linked(path) or not path.is_dir()):
                raise ValueError('Unsafe cache path.')
            if path.exists():
                path.resolve(strict=True).relative_to(root)
        return root
    except (OSError, ValueError, RuntimeError):
        _fail()
