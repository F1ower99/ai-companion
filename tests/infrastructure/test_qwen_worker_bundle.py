import hashlib
from pathlib import Path
import pytest
from companion.domain.voice import VoiceErrorCode, VoiceOperationError


def resolver():
    from companion.infrastructure import qwen_worker_bundle
    return qwen_worker_bundle


def test_source_uses_fixed_project_root_without_bundle():
    module = resolver()
    root = module.worker_import_path(compiled=False)
    assert (root / 'companion/infrastructure/qwen_tts_worker.py').is_file()


def test_compiled_bundle_digest_checked_without_importing_its_code(tmp_path):
    module = resolver()
    exe = tmp_path / 'app.exe'; exe.touch()
    archive = tmp_path / 'companion-qwen-worker.zip'
    data = b'not executed by parent'; archive.write_bytes(data)
    assert module.worker_import_path(compiled=True, executable=exe,
        expected_digest=hashlib.sha256(data).hexdigest()) == archive.resolve()
    archive.write_bytes(b'modified')
    with pytest.raises(VoiceOperationError) as failure:
        module.worker_import_path(compiled=True, executable=exe,
            expected_digest=hashlib.sha256(data).hexdigest())
    assert failure.value.code is VoiceErrorCode.NOT_CONFIGURED


@pytest.mark.parametrize('kind', ['missing', 'no_digest', 'oversized', 'linked', 'ancestor', 'network'])
def test_untrusted_bundle_never_resolves(tmp_path, monkeypatch, kind):
    module = resolver()
    exe = tmp_path / 'app.exe'; exe.touch()
    archive = tmp_path / 'companion-qwen-worker.zip'
    data = b'fixture'; digest = hashlib.sha256(data).hexdigest()
    if kind != 'missing': archive.write_bytes(data)
    if kind == 'no_digest': digest = None
    if kind == 'oversized': archive.write_bytes(b'x' * (module.MAX_BUNDLE_BYTES + 1))
    if kind in ('linked', 'ancestor'):
        original = Path.is_symlink
        target = archive if kind == 'linked' else tmp_path
        monkeypatch.setattr(Path, 'is_symlink', lambda p: p == target or original(p))
    if kind == 'network': monkeypatch.setattr(module, '_local', lambda _: False)
    with pytest.raises(VoiceOperationError):
        module.worker_import_path(compiled=True, executable=exe, expected_digest=digest)
