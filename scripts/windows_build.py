"""Preflight and isolate the pinned Qt 6.11 Windows deployment tool."""
from __future__ import annotations

import argparse
import configparser
import hashlib
import shlex
import zipfile
from importlib import metadata
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


def installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def check_prerequisites(venv: Path, platform_name=sys.platform, which=shutil.which,
                        version=installed_version, python_version=sys.version_info[:2]) -> list[str]:
    problems = []
    if platform_name != 'win32':
        problems.append('Windows is required for this build.')
    if not (venv / 'pyvenv.cfg').is_file():
        problems.append('Missing virtual environment pyvenv.cfg.')
    for filename in ['python.exe', 'pyside6-deploy.exe']:
        if not (venv / 'Scripts' / filename).is_file():
            problems.append(f'Missing virtual environment tool: {filename}')
    for tool in ['dumpbin', 'cl']:
        if not which(tool):
            problems.append(f'Missing MSVC {tool}; use an x64 Native Tools command prompt.')
    for package, required in [('PySide6-Essentials', '6.11.2'), ('Nuitka', '4.1.1'), ('ordered-set', None), ('zstandard', None)]:
        found = version(package)
        if not found or (required and found != required):
            problems.append(f'Missing/incompatible {package}{"==" + required if required else ""}; install .[dev,deploy] explicitly.')
    if python_version < (3, 11) and not version('tomli'):
        problems.append('Missing tomli for Qt deployment on Python < 3.11; install .[deploy] explicitly.')
    return problems


def _artifact_directory(root: Path, explicit: Path | None) -> Path:
    if explicit is None:
        return root
    path = Path(explicit)
    try:
        if not path.is_absolute() or not _local_artifact_drive(path):
            raise ValueError('Local absolute path required.')
        # Inspect top-down so a linked parent cannot redirect later probes.
        for ancestor in reversed((path, *path.parents)):
            if (ancestor.is_symlink()
                    or getattr(ancestor.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError('Linked ancestor.')
        if not path.is_dir():
            raise ValueError('Directory required.')
        path = path.resolve(strict=True)
        if not _local_artifact_drive(path):
            raise ValueError('Resolved network path.')
    except (OSError, ValueError):
        raise ValueError('Artifact root must be an existing absolute local directory without links.') from None
    if (path.is_relative_to(root / 'src')
            or any(part.casefold() == '.git' for part in path.parts)):
        raise ValueError('Artifact root must be outside source and Git metadata.')
    return path


def _local_artifact_drive(path: Path) -> bool:
    if str(path).startswith(('\\\\', '//')):
        return False
    if sys.platform != 'win32':
        return True
    import ctypes
    reader = ctypes.WinDLL('kernel32', use_last_error=True).GetDriveTypeW
    reader.argtypes, reader.restype = [ctypes.c_wchar_p], ctypes.c_uint
    return reader(path.anchor) in (2, 3, 6)


WORKER_FILES = (
    'companion/__init__.py', 'companion/domain/__init__.py',
    'companion/infrastructure/__init__.py', 'companion/domain/errors.py',
    'companion/domain/voice.py', 'companion/infrastructure/tts_assets.py',
    'companion/infrastructure/qwen_assets.py', 'companion/infrastructure/tts_worker.py',
    'companion/infrastructure/qwen_tts_worker.py',
)


def build_speech_worker_bundle(stage: Path) -> Path:
    source = stage / 'src'
    entries = []
    for name in WORKER_FILES:
        path = source / name
        for ancestor in (path, *path.parents):
            if ancestor == stage:
                break
            if (ancestor.is_symlink()
                    or getattr(ancestor.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError('Linked worker source.')
        data = path.read_bytes()
        if len(data) > 128 * 1024:
            raise ValueError('Unexpected worker source size.')
        entries.append((name, data))
    bundle = stage / 'companion-qwen-worker.zip'
    with zipfile.ZipFile(bundle, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    manifest = source / 'companion/infrastructure/_qwen_worker_manifest.py'
    manifest.write_text('WORKER_BUNDLE_SHA256 = ' + repr(digest) + '\n', encoding='utf-8')
    return bundle


def run_deployment(root: Path, venv: Path, *, dry_run: bool, runner=subprocess.run,
                   artifact_root: Path | None = None) -> Path:
    root, venv = root.resolve(), venv.resolve()
    source = root / 'src'
    if not source.is_dir() or any(path.is_symlink() for path in source.rglob('*')):
        raise ValueError('Build source must be an existing tree without symlinks.')
    artifacts = _artifact_directory(root, artifact_root)
    build_root = artifacts / 'build' / 'windows'
    build_root.resolve().relative_to(artifacts)
    build_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='build-', dir=build_root))
    stage.resolve().relative_to(artifacts)  # Validate before copying or invoking a tool.
    shutil.copytree(source, stage / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(root / 'pyproject.toml', stage / 'pyproject.toml')
    worker_bundle = build_speech_worker_bundle(stage)
    output_parent = artifacts / 'dist' / stage.name
    output_parent.resolve().relative_to(artifacts)
    output_parent.mkdir(parents=True, exist_ok=False)
    config = configparser.ConfigParser()
    config.read(root / 'pysidedeploy.spec', encoding='utf-8')
    config['app']['project_dir'] = str(stage)
    config['app']['input_file'] = str(stage / 'src' / 'companion' / 'desktop' / 'app.py')
    config['app']['exec_directory'] = str(output_parent)
    config['python']['python_path'] = str(venv / 'Scripts' / 'python.exe')
    # Qt 6.11 lacks --no-install. Its documented source skips installation
    # entirely for an empty packages field; preflight requires the tools.
    config['python']['packages'] = ''
    bundle_option = '--include-data-files=' + worker_bundle.as_posix() + '=companion-qwen-worker.zip'
    config['nuitka']['extra_args'] += ' ' + shlex.quote(bundle_option)
    if installed_version('faster-whisper'):
        # PyAV's Cython modules import siblings dynamically (e.g. av.utils).
        config['nuitka']['extra_args'] += ' --include-module=av.utils --include-package-data=faster_whisper'
    config_path = stage / 'pysidedeploy.spec'
    with config_path.open('w', encoding='utf-8') as handle:
        config.write(handle)
    args = [str(venv / 'Scripts' / 'pyside6-deploy.exe'), '-c', str(config_path), '--keep-deployment-files', '--mode', 'standalone']
    if dry_run:
        args.append('--dry-run')
    environment = os.environ.copy()
    temporary = stage / 'tmp'
    temporary.mkdir()
    environment.update(VIRTUAL_ENV=str(venv), PYTHONPATH=str(stage / 'src'), PIP_NO_INDEX='1',
                       PIP_DISABLE_PIP_VERSION_CHECK='1', NUITKA_CACHE_DIR=str(stage / 'nuitka-cache'),
                       TEMP=str(temporary), TMP=str(temporary),
                       PYTHONPYCACHEPREFIX=str(stage / 'python-cache'))
    result = runner(args, cwd=stage, env=environment, shell=False, stdin=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise RuntimeError(f'Deployment exited {result.returncode}; retained work: {stage}')
    output = output_parent / 'AICompanion.dist'
    # Qt's wrapper can return zero after a compiler failure. Verify the artifact.
    if not dry_run and not (output / 'app.exe').is_file():
        raise RuntimeError(f'No standalone executable produced; retained work: {stage}')
    print(f'{"Dry run only; expected output" if dry_run else "Standalone output"}: {output}')
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--venv-path', type=Path, required=True)
    parser.add_argument('--artifact-root', type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    problems = check_prerequisites(args.venv_path)
    if Path(sys.prefix).resolve() != args.venv_path.resolve():
        problems.append('Run this helper with the selected virtual environment Python.')
    if problems:
        for problem in problems:
            print(f'Build preflight: {problem}', file=sys.stderr)
        return 1
    if args.preflight_only:
        print('Build preflight passed; no build started.')
        return 0
    try:
        run_deployment(Path(__file__).parents[1], args.venv_path, dry_run=args.dry_run,
                       artifact_root=args.artifact_root)
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Build failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
