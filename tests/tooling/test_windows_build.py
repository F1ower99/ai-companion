import subprocess
import shutil
from pathlib import Path

import pytest

from test_third_party_notices import load_script


def make_venv(tmp_path):
    venv = tmp_path / 'environment with spaces'
    (venv / 'Scripts').mkdir(parents=True)
    for name in ['python.exe', 'pyside6-deploy.exe']:
        (venv / 'Scripts' / name).touch()
    (venv / 'pyvenv.cfg').write_text('home = fixture', encoding='utf-8')
    return venv


def test_preflight_reports_missing_prerequisites_without_output(tmp_path):
    module = load_script('windows_build')
    problems = module.check_prerequisites(tmp_path / 'absent', 'win32', lambda name: None, lambda name: None)
    for word in ['python.exe', 'pyside6-deploy', 'dumpbin', 'cl', 'Nuitka']:
        assert any(word in problem for problem in problems)
    assert list(tmp_path.iterdir()) == []


def test_preflight_accepts_controlled_toolchain_with_spaces(tmp_path):
    module = load_script('windows_build')
    venv = make_venv(tmp_path)
    versions = {'PySide6-Essentials': '6.11.2', 'Nuitka': '4.1.1', 'ordered-set': '4.1.0', 'zstandard': '0.25.0'}
    assert module.check_prerequisites(venv, 'win32', lambda name: 'C:/tools with spaces/tool.exe', versions.get) == []
    assert module.check_prerequisites(venv, 'linux', lambda name: 'tool', versions.get)


def test_build_preserves_old_artifacts_and_passes_paths_as_arguments(tmp_path):
    module = load_script('windows_build')
    root = tmp_path / 'project with spaces'
    (root / 'src' / 'companion' / 'desktop').mkdir(parents=True)
    (root / 'src' / 'companion' / 'desktop' / 'app.py').write_text('raise RuntimeError("must not launch")')
    (root / 'pyproject.toml').write_text('[project]\nname="fixture"')
    (root / 'pysidedeploy.spec').write_text((Path(__file__).parents[2] / 'pysidedeploy.spec').read_text())
    old = root / 'dist' / 'old-build'
    old.mkdir(parents=True)
    (old / 'keep.txt').write_text('keep')
    calls = []
    def run(args, **kwargs):
        import configparser
        calls.append((args, kwargs))
        cfg = configparser.ConfigParser()
        cfg.read(args[args.index('-c') + 1])
        assert cfg['python']['packages'] == ''
        assert cfg['nuitka']['mode'] == 'standalone'
        return subprocess.CompletedProcess(args, 0)
    module.run_deployment(root, tmp_path / 'venv with spaces', dry_run=True, runner=run)
    args, kwargs = calls[0]
    assert len(calls) == 1
    assert args[0] == str(tmp_path / 'venv with spaces' / 'Scripts' / 'pyside6-deploy.exe')
    assert '--dry-run' in args and '--keep-deployment-files' in args
    assert kwargs['shell'] is False
    assert (old / 'keep.txt').read_text() == 'keep'
    assert len(list((root / 'build' / 'windows').iterdir())) == 1

    # Qt 6.11 can swallow a compiler error and return success: require a file.
    with pytest.raises(RuntimeError, match='No standalone executable'):
        module.run_deployment(root, tmp_path / 'venv with spaces', dry_run=False, runner=run)
    assert (old / 'keep.txt').read_text() == 'keep'


def test_powershell_entry_reports_missing_venv_with_spaces(tmp_path):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if shell is None:
        pytest.skip('PowerShell is not installed')
    script = Path(__file__).parents[2] / 'scripts' / 'build_windows.ps1'
    result = subprocess.run(
        [shell, '-NoProfile', '-File', str(script), '-VenvPath', str(tmp_path / 'missing environment'), '-PreflightOnly'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    assert result.returncode != 0
    assert 'Missing virtual environment Python' in result.stderr
    assert list(tmp_path.iterdir()) == []
