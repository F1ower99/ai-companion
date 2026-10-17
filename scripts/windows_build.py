"""Preflight and isolate the pinned Qt 6.11 Windows deployment tool."""
from __future__ import annotations

import argparse
import configparser
from importlib import metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def check_prerequisites(venv: Path, platform_name=sys.platform, which=shutil.which, version=installed_version) -> list[str]:
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
    return problems


def run_deployment(root: Path, venv: Path, *, dry_run: bool, runner=subprocess.run) -> Path:
    root, venv = root.resolve(), venv.resolve()
    source = root / 'src'
    if not source.is_dir() or any(path.is_symlink() for path in source.rglob('*')):
        raise ValueError('Build source must be an existing tree without symlinks.')
    build_root = root / 'build' / 'windows'
    build_root.resolve().relative_to(root)
    build_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='build-', dir=build_root))
    stage.resolve().relative_to(root)  # Validate before copying or invoking a tool.
    shutil.copytree(source, stage / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(root / 'pyproject.toml', stage / 'pyproject.toml')
    output_parent = root / 'dist' / stage.name
    output_parent.resolve().relative_to(root)
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
    config_path = stage / 'pysidedeploy.spec'
    with config_path.open('w', encoding='utf-8') as handle:
        config.write(handle)
    args = [str(venv / 'Scripts' / 'pyside6-deploy.exe'), '-c', str(config_path), '--keep-deployment-files', '--mode', 'standalone']
    if dry_run:
        args.append('--dry-run')
    environment = os.environ.copy()
    environment.update(VIRTUAL_ENV=str(venv), PYTHONPATH=str(stage / 'src'), PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1', NUITKA_CACHE_DIR=str(stage / 'nuitka-cache'))
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
        run_deployment(Path(__file__).parents[1], args.venv_path, dry_run=args.dry_run)
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Build failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
