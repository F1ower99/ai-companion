"""Owned isolated Qwen child; no shell, inherited secrets or model imports."""
import os
from pathlib import Path
import subprocess
import time

from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure.qwen_assets import runtime_python, work_directory as local_work_directory
from companion.infrastructure.qwen_worker_bundle import worker_import_path
from companion.infrastructure.tts_process import _run_bounded_worker, source_tts_supported


# -I removes inherited CWD/user-site/PYTHONPATH before any worker import, even
# on Python3.10 where -P does not exist. Only our validated root/ZIP is added.
WORKER_BOOTSTRAP = (
    "import sys, runpy; sys.path.insert(0, sys.argv[1]); "
    "runpy.run_module('companion.infrastructure.qwen_tts_worker', run_name='__main__')"
)


def offline_environment(work, import_path=None):
    environment = {name: value for name, value in os.environ.items()
                   if name.upper() in {'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'COMSPEC', 'PATH', 'PATHEXT'}}
    environment.update({
        'PYTHONPATH': str(import_path if import_path is not None else worker_import_path()),
        'PYTHONNOUSERSITE': '1', 'PYTHONPYCACHEPREFIX': str(work / 'cache' / 'pycache'),
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
        'DO_NOT_TRACK': '1', 'TOKENIZERS_PARALLELISM': 'false',
        'HF_HOME': str(work / 'cache' / 'huggingface'), 'TORCH_HOME': str(work / 'cache' / 'torch'),
        'NUMBA_CACHE_DIR': str(work / 'cache' / 'numba'),
        'CUDA_CACHE_PATH': str(work / 'cache' / 'cuda'),
        'TEMP': str(work / 'tmp'), 'TMP': str(work / 'tmp'),
        'AI_COMPANION_QWEN_WORK_DIR': str(work),
    })
    return environment


def run_qwen_worker(request, token, *, runtime, work_directory,
                    process_factory=subprocess.Popen, monotonic=time.monotonic):
    if token.is_cancelled():
        raise VoiceOperationError(VoiceErrorCode.CANCELLED)
    import_path = worker_import_path(compiled=not source_tts_supported())
    python = runtime_python(runtime)
    work = local_work_directory(work_directory)
    return _run_bounded_worker(
        request, token,
        command=[str(python), '-I', '-X', 'pycache_prefix=' + str(work / 'cache' / 'pycache'),
                 '-c', WORKER_BOOTSTRAP, str(import_path)],
        environment=offline_environment(work, import_path), timeout_seconds=120,
        process_factory=process_factory, monotonic=monotonic,
    )
