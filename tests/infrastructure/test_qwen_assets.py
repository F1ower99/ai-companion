import hashlib
from pathlib import Path

import pytest

from companion.domain.voice import VoiceErrorCode, VoiceOperationError
from companion.infrastructure import qwen_assets as assets


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    root = tmp_path / 'model'; root.mkdir()
    entries = []
    for name, data in [('config.json', b'{}'), ('speech_tokenizer/model.safetensors', b'public')]:
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        entries.append((name, len(data), 'sha256', hashlib.sha256(data).hexdigest()))
    monkeypatch.setattr(assets, 'MODEL_ASSETS', tuple(entries))
    return root


def invalid(call):
    with pytest.raises(VoiceOperationError) as error:
        call()
    assert error.value.code is VoiceErrorCode.NOT_CONFIGURED
    assert str(error.value) == 'not_configured'


def test_shape_preflight_does_not_hash_but_worker_integrity_does(bundle, monkeypatch):
    original = Path.open
    def forbidden(*args, **kwargs): raise AssertionError('UI preflight read model data')
    monkeypatch.setattr(Path, 'open', forbidden)
    assert assets.qwen_model_directory(bundle) == bundle.resolve()
    monkeypatch.setattr(Path, 'open', original)
    assert assets.verify_qwen_model(bundle) == bundle.resolve()
    (bundle / 'config.json').write_bytes(b'[]')
    assert assets.qwen_model_directory(bundle) == bundle.resolve()
    invalid(lambda: assets.verify_qwen_model(bundle))


@pytest.mark.parametrize('mutation', ['missing', 'size', 'extra', 'extra_directory', 'linked'])
def test_model_shape_rejects_missing_changed_or_unexpected_entries(bundle, mutation):
    if mutation == 'missing': (bundle / 'config.json').unlink()
    elif mutation == 'size': (bundle / 'config.json').write_bytes(b'wrong')
    elif mutation == 'extra': (bundle / 'model.pkl').write_bytes(b'pickle')
    elif mutation == 'extra_directory': (bundle / 'cache').mkdir()
    else:
        try: (bundle / 'linked').symlink_to(bundle / 'config.json')
        except OSError: pytest.skip('Symlink privilege unavailable')
    invalid(lambda: assets.qwen_model_directory(bundle))


@pytest.mark.parametrize('path', ['relative', 'https://example/model', r'\\server\model'])
def test_remote_and_relative_paths_rejected(path):
    invalid(lambda: assets.qwen_model_directory(path))
    invalid(lambda: assets.runtime_python(path))
    invalid(lambda: assets.work_directory(path))


def test_runtime_and_work_are_existing_local_paths(tmp_path):
    runtime = tmp_path / 'runtime'; scripts = runtime / 'Scripts'; scripts.mkdir(parents=True)
    executable = scripts / 'python.exe'; executable.write_bytes(b'fixture')
    invalid(lambda: assets.runtime_python(executable))
    (runtime / 'pyvenv.cfg').write_text('fixture')
    assert assets.runtime_python(executable) == executable.resolve()
    assert assets.work_directory(tmp_path) == tmp_path.resolve()
    invalid(lambda: assets.work_directory(tmp_path / 'missing'))
    invalid(lambda: assets.work_directory(executable))


def test_pinned_public_manifest_is_complete():
    assert assets.MODEL_REVISION == '0c0e3051f131929182e2c023b9537f8b1c68adfe'
    assert len(assets.MODEL_ASSETS) == 13
    assert sum(entry[1] for entry in assets.MODEL_ASSETS) == 4520218951


def test_reparse_bundle_or_cache_entry_is_rejected_without_symlink_privilege(bundle, monkeypatch):
    original = assets._linked
    monkeypatch.setattr(assets, '_linked', lambda path: path == bundle / 'config.json' or original(path))
    invalid(lambda: assets.qwen_model_directory(bundle))
    monkeypatch.setattr(assets, '_linked', original)
    cache = bundle.parent / 'cache'; cache.mkdir()
    monkeypatch.setattr(assets, '_linked', lambda path: path == cache or original(path))
    invalid(lambda: assets.work_directory(bundle.parent))
