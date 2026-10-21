"""Owned source-runtime Qwen child; no shell, inherited secrets or model imports."""
import os
from pathlib import Path
import subprocess
import time

from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure.qwen_assets import runtime_python, work_directory as local_work_directory
from companion.infrastructure.tts_process import _run_bounded_worker, source_tts_supported


def offline_environment(work):
    environment = {name: value for name, value in os.environ.items()
                   if name.upper() in {'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'COMSPEC', 'PATH', 'PATHEXT'}}
    environment.update({
        'PYTHONPATH': str(Path(__file__).resolve().parents[2]),
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
    if not source_tts_supported():
        raise VoiceOperationError(VoiceErrorCode.NOT_CONFIGURED)
    python = runtime_python(runtime)
    work = local_work_directory(work_directory)
    return _run_bounded_worker(
        request, token,
        command=[str(python), '-s', '-m', 'companion.infrastructure.qwen_tts_worker'],
        environment=offline_environment(work), timeout_seconds=120,
        process_factory=process_factory, monotonic=monotonic,
    )
