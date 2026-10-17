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
