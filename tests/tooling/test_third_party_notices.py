import importlib.util
from email.message import Message
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_script(name):
    import sys
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[2] / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def dist(name, version='1.0', license=None, expression=None, requires=(), files=()):
    metadata = Message()
    metadata['Name'] = name
    if license:
        metadata['License'] = license
    if expression:
        metadata['License-Expression'] = expression
    return SimpleNamespace(metadata=metadata, version=version, requires=requires, files=files)


def test_inventory_filters_markers_handles_cycles_and_sorts():
    module = load_script('write_third_party_notices')
    packages = {
        'beta': dist('Beta', license='MIT', requires=['alpha', 'missing; python_version < "2"']),
        'alpha': dist('Alpha', expression='BSD-3-Clause', license='unstructured', requires=['beta']),
    }
    lookup = lambda name: packages[name.lower()]
    notices = module.collect_notices(['beta'], lookup)
    rendered = module.render_notices(notices)
    assert [notice.name for notice in notices] == ['Alpha', 'Beta']
    assert 'BSD-3-Clause' in rendered and 'unstructured' not in rendered
    assert rendered == module.render_notices(module.collect_notices(['alpha', 'beta'], lookup))


def test_absent_license_is_flagged_and_paths_are_relative():
    module = load_script('write_third_party_notices')
    value = dist('Unknown', files=['unknown.dist-info/licenses/LICENSE.txt', '/private/LICENSE', '../LICENSE'])
    rendered = module.render_notices(module.collect_notices(['unknown'], lambda name: value))
    assert 'REVIEW REQUIRED' in rendered
    assert 'unknown.dist-info/licenses/LICENSE.txt' in rendered
    assert '/private/LICENSE' not in rendered and '../LICENSE' not in rendered


def test_missing_distribution_and_invalid_requirement_fail_clearly():
    module = load_script('write_third_party_notices')
    def missing(name):
        raise PackageNotFoundError(name)
    with pytest.raises(ValueError, match='Missing installed distribution'):
        module.collect_notices(['missing'], missing)
    with pytest.raises(ValueError, match='Invalid dependency'):
        module.collect_notices(['not valid ???'], missing)


def test_version_mismatch_is_not_claimed_verified():
    module = load_script('write_third_party_notices')
    with pytest.raises(ValueError, match='does not satisfy'):
        module.collect_notices(['example==2'], lambda name: dist('example', '1.0'))


@pytest.mark.parametrize('expression,legacy', [
    ('MIT OR ???', None), (None, 'UNKNOWN'), (None, 'NOASSERTION'),
    (None, 'custom license text requiring review'),
])
def test_unparseable_license_is_preserved_and_flagged_even_with_license_file(expression, legacy):
    module = load_script('write_third_party_notices')
    value = dist('example', expression=expression, license=legacy, files=['example.dist-info/licenses/LICENSE'])
    rendered = module.render_notices(module.collect_notices(['example'], lambda name: value))
    assert 'REVIEW REQUIRED' in rendered
    assert (expression or legacy) in rendered


@pytest.mark.parametrize('name,version', [
    ('example', 'not a version'), ('not a valid name', '1.0'), ('another-package', '1.0'),
])
def test_invalid_or_mismatched_identity_metadata_is_rejected(name, version):
    module = load_script('write_third_party_notices')
    with pytest.raises(ValueError, match='Invalid distribution metadata'):
        module.collect_notices(['example'], lambda _: dist(name, version))


def project_metadata():
    value = dist('ai-companion', requires=[
        'base', 'speech[codec]; extra == "voice"',
        'recognizer; extra == "stt"', 'pytest; extra == "dev"',
        'legacy; python_version < "2"',
    ])
    for extra in ('voice', 'stt', 'dev'):
        value.metadata['Provides-Extra'] = extra
    return value


def test_runtime_selection_includes_base_and_selected_extras_only():
    module = load_script('write_third_party_notices')
    project = project_metadata()
    lookup = lambda name: project
    assert module.runtime_requirements([], lookup) == ['base']
    assert module.runtime_requirements(['VOICE', 'stt', 'voice'], lookup) == [
        'base', 'speech[codec]', 'recognizer',
    ]


def test_selected_optional_dependencies_keep_their_own_transitive_extras():
    module = load_script('write_third_party_notices')
    packages = {
        'ai-companion': project_metadata(), 'base': dist('base'),
        'speech': dist('speech', requires=['codec; extra == "codec"']),
        'codec': dist('codec'),
    }
    requirements = module.runtime_requirements(['voice'], packages.__getitem__)
    notices = module.collect_notices(requirements, packages.__getitem__)
    assert [notice.name for notice in notices] == ['base', 'codec', 'speech']


def test_unknown_extra_fails_instead_of_silently_omitting_dependencies():
    module = load_script('write_third_party_notices')
    with pytest.raises(ValueError, match='Unknown project extra: typo'):
        module.runtime_requirements(['typo'], lambda name: project_metadata())


def test_cli_extra_inventory_and_invalid_selection_preserve_existing_output(tmp_path, monkeypatch):
    module = load_script('write_third_party_notices')
    packages = {
        'ai-companion': project_metadata(), 'base': dist('base'),
        'speech': dist('speech', requires=['codec; extra == "codec"']), 'codec': dist('codec'),
    }
    monkeypatch.setattr(module.metadata, 'distribution', packages.__getitem__)
    # Supply lookup explicitly because collect_notices also supports injected fixture metadata.
    original = module.collect_notices
    monkeypatch.setattr(module, 'collect_notices', lambda roots: original(roots, packages.__getitem__))
    output = tmp_path / 'notices.md'
    monkeypatch.setattr('sys.argv', ['inventory', '--extra', 'voice', '--output', str(output)])
    assert module.main() == 0
    assert '| speech |' in output.read_text(encoding='utf-8')
    assert '| codec |' in output.read_text(encoding='utf-8')
    previous = output.read_bytes()
    monkeypatch.setattr('sys.argv', ['inventory', '--extra', 'typo', '--output', str(output)])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 1
    assert output.read_bytes() == previous


def test_cli_does_not_mix_project_extras_with_explicit_requirements(tmp_path, monkeypatch):
    module = load_script('write_third_party_notices')
    output = tmp_path / 'notices.md'
    monkeypatch.setattr('sys.argv', [
        'inventory', '--extra', 'voice', '--requirement', 'base', '--output', str(output),
    ])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert not output.exists()
