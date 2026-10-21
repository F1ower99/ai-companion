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
    versions = {'PySide6-Essentials': '6.11.2', 'Nuitka': '4.1.1', 'ordered-set': '4.1.0',
                'zstandard': '0.25.0', 'tomli': '2.3.0'}
    assert module.check_prerequisites(venv, 'win32', lambda name: 'C:/tools with spaces/tool.exe', versions.get) == []
    assert module.check_prerequisites(venv, 'linux', lambda name: 'tool', versions.get)


def test_python310_deploy_requires_tomli_but_python311_has_tomllib(tmp_path):
    module = load_script('windows_build')
    venv = make_venv(tmp_path)
    versions = {'PySide6-Essentials': '6.11.2', 'Nuitka': '4.1.1',
                'ordered-set': '4.1.0', 'zstandard': '0.25.0'}
    old = module.check_prerequisites(venv, 'win32', lambda _: 'tool', versions.get, python_version=(3, 10))
    assert any('tomli' in problem for problem in old)
    assert module.check_prerequisites(venv, 'win32', lambda _: 'tool', versions.get,
                                       python_version=(3, 11)) == []


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


def make_project(root):
    (root / 'src' / 'companion' / 'desktop').mkdir(parents=True)
    (root / 'src' / 'companion' / 'desktop' / 'app.py').write_text('raise RuntimeError("must not launch")')
    (root / 'pyproject.toml').write_text('[project]\nname="fixture"')
    (root / 'pysidedeploy.spec').write_text((Path(__file__).parents[2] / 'pysidedeploy.spec').read_text())


def test_explicit_artifact_root_contains_staging_cache_temp_and_output(tmp_path):
    module = load_script('windows_build')
    root, artifacts = tmp_path / 'source project', tmp_path / 'external artifacts'
    make_project(root); artifacts.mkdir()
    old = artifacts / 'dist' / 'old'; old.mkdir(parents=True)
    (old / 'keep.txt').write_text('keep')
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)
    output = module.run_deployment(root, tmp_path / 'venv', artifact_root=artifacts,
                                    dry_run=True, runner=run)
    assert output.is_relative_to(artifacts) and not (root / 'build').exists()
    assert not (root / 'dist').exists() and (old / 'keep.txt').read_text() == 'keep'
    args, options = calls[0]
    assert options['cwd'].is_relative_to(artifacts)
    for key in ('NUITKA_CACHE_DIR', 'TEMP', 'TMP', 'PYTHONPYCACHEPREFIX'):
        assert Path(options['env'][key]).is_relative_to(artifacts)
    assert Path(options['env']['TEMP']).is_dir()


@pytest.mark.parametrize('location', ['relative', 'missing', 'source', 'git'])
def test_invalid_artifact_roots_fail_before_output_or_process(tmp_path, location):
    module = load_script('windows_build')
    root = tmp_path / 'source project'; make_project(root)
    (root / '.git').mkdir()
    artifact = {'relative': Path('relative'), 'missing': tmp_path / 'missing',
                'source': root / 'src', 'git': root / '.git'}[location]
    def forbidden(*args, **kwargs): pytest.fail('Invalid artifact root launched build', pytrace=False)
    with pytest.raises(ValueError):
        module.run_deployment(root, tmp_path / 'venv', artifact_root=artifact,
                              dry_run=True, runner=forbidden)
    assert not (root / 'build').exists() and not (root / 'dist').exists()


def test_linked_artifact_root_fails_before_staging(tmp_path, monkeypatch):
    module = load_script('windows_build')
    root, artifacts = tmp_path / 'source', tmp_path / 'artifacts'
    make_project(root); artifacts.mkdir()
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == artifacts or original(path))
    with pytest.raises(ValueError, match='without links'):
        module.run_deployment(root, tmp_path / 'venv', artifact_root=artifacts,
                              dry_run=True, runner=lambda *a, **k: pytest.fail('Unexpected build'))
    assert list(artifacts.iterdir()) == []


def test_artifact_root_rejects_linked_ancestor_before_staging(tmp_path, monkeypatch):
    module = load_script('windows_build')
    root, parent = tmp_path / 'source', tmp_path / 'redirected parent'
    artifacts = parent / 'artifacts'
    make_project(root); artifacts.mkdir(parents=True)
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == parent or original(path))
    with pytest.raises(ValueError):
        module.run_deployment(root, tmp_path / 'venv', artifact_root=artifacts,
                              dry_run=True, runner=lambda *a, **k: pytest.fail('Linked ancestor launched build'))
    assert list(artifacts.iterdir()) == []


def test_artifact_root_rejects_resolved_network_destination(tmp_path, monkeypatch):
    module = load_script('windows_build')
    root, artifacts = tmp_path / 'source', tmp_path / 'artifacts'
    make_project(root); artifacts.mkdir()
    original = Path.resolve
    monkeypatch.setattr(Path, 'resolve', lambda path, *a, **k:
                        Path(r'\\server\share\artifacts') if path == artifacts else original(path, *a, **k))
    with pytest.raises(ValueError):
        module._artifact_directory(root.resolve(), artifacts)
