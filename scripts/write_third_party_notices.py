"""Inventory installed runtime metadata, not a redistribution certification."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path, PurePosixPath, PureWindowsPath

from packaging.requirements import InvalidRequirement, Requirement
from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression
from packaging.utils import canonicalize_name
from packaging.version import Version


@dataclass(frozen=True)
class PackageNotice:
    name: str
    version: str
    license: str | None
    license_files: tuple[str, ...]
    review_reasons: tuple[str, ...] = ()


def collect_notices(requirements: list[str], distribution_lookup=metadata.distribution) -> list[PackageNotice]:
    pending = [(raw, frozenset()) for raw in requirements]
    visited = set()
    notices = {}
    while pending:
        raw, active_extras = pending.pop()
        try:
            requirement = Requirement(raw)
        except InvalidRequirement as error:
            raise ValueError(f'Invalid dependency: {raw}') from error
        if requirement.marker and not any(
            requirement.marker.evaluate({'extra': extra}) for extra in active_extras or {''}
        ):
            continue
        name = canonicalize_name(requirement.name)
        try:
            distribution = distribution_lookup(name)
        except metadata.PackageNotFoundError as error:
            raise ValueError(f'Missing installed distribution: {name}') from error
        if not distribution.version or not distribution.metadata.get('Name'):
            raise ValueError(f'Missing name/version metadata: {name}')
        try:
            actual_name = canonicalize_name(distribution.metadata['Name'], validate=True)
            Version(distribution.version)
            if actual_name != name:
                raise ValueError('Distribution identity differs from dependency.')
        except (ValueError, TypeError) as error:
            raise ValueError(f'Invalid distribution metadata: {name}') from error
        if requirement.specifier and distribution.version not in requirement.specifier:
            raise ValueError(f'{name} {distribution.version} does not satisfy {requirement.specifier}')
        key = (name, frozenset(requirement.extras))
        if key in visited:
            continue
        visited.add(key)
        license_value = distribution.metadata.get('License-Expression') or distribution.metadata.get('License')
        review_reasons = []
        if license_value:
            try:
                canonicalize_license_expression(license_value)
            except InvalidLicenseExpression:
                review_reasons.append('Unparseable or unknown declared license; review original metadata.')
        license_files = []
        for file in distribution.files or ():
            path = str(file).replace('\\', '/')
            parsed = PurePosixPath(path)
            if parsed.is_absolute() or PureWindowsPath(path).drive or '..' in parsed.parts:
                continue
            if parsed.name.lower().startswith(('license', 'copying', 'notice')) or 'licenses' in parsed.parts:
                license_files.append(path)
        notices[name] = PackageNotice(
            distribution.metadata['Name'], distribution.version,
            ' '.join(license_value.split()) if license_value else None,
            tuple(sorted(set(license_files))),
            tuple(review_reasons),
        )
        pending.extend((child, frozenset(requirement.extras)) for child in distribution.requires or ())
    return [notices[name] for name in sorted(notices)]


def _cell(value: str) -> str:
    return ' '.join(value.split()).replace('|', '\\|').replace('`', "'")


def runtime_requirements(extras: list[str], distribution_lookup=None) -> list[str]:
    """Select installed project roots; project extras do not leak to child packages."""
    lookup = distribution_lookup or metadata.distribution
    project = lookup('ai-companion')
    available = {canonicalize_name(extra) for extra in project.metadata.get_all('Provides-Extra', [])}
    selected = {canonicalize_name(extra) for extra in extras}
    unknown = selected - available
    if unknown:
        raise ValueError(f'Unknown project extra: {sorted(unknown)[0]}')
    roots = []
    for raw in project.requires or ():
        try:
            requirement = Requirement(raw)
        except InvalidRequirement as error:
            raise ValueError(f'Invalid dependency: {raw}') from error
        if requirement.marker and not any(
            requirement.marker.evaluate({'extra': extra}) for extra in selected | {''}
        ):
            continue
        # Already evaluated in the project's context. Child extras remain intact.
        requirement.marker = None
        roots.append(str(requirement))
    return roots


def render_notices(notices: list[PackageNotice]) -> str:
    lines = [
        '# Third-party runtime dependency inventory', '',
        'Generated from installed distribution metadata for the declared runtime dependency closure.',
        'Build tools, the Python interpreter, Qt plugins/native libraries, and model assets require separate release review.',
        'License metadata is recorded as declared, not inferred. Include the applicable license texts and review redistribution obligations before shipping.', '',
        '| Distribution | Version | Declared license |', '| --- | --- | --- |',
    ]
    for notice in notices:
        lines.append(f'| {_cell(notice.name)} | {_cell(notice.version)} | {_cell(notice.license or "REVIEW REQUIRED: missing license metadata")} |')
    for notice in notices:
        lines.extend(['', f'## {_cell(notice.name)}', '', 'License file paths in the installed distribution:'])
        lines.extend(f'- REVIEW REQUIRED: {_cell(reason)}' for reason in notice.review_reasons)
        lines.extend(f'- `{_cell(path)}`' for path in notice.license_files)
        if not notice.license_files:
            lines.append('- REVIEW REQUIRED: no license files recorded in distribution metadata.')
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--requirement', action='append')
    selection.add_argument('--extra', action='append', help='Include a declared project extra; repeat to combine.')
    parser.add_argument('--output', type=Path, default=Path(__file__).parents[1] / 'THIRD_PARTY_NOTICES.md')
    args = parser.parse_args()
    try:
        requirements = args.requirement if args.requirement is not None else runtime_requirements(args.extra or [])
        notices = collect_notices(requirements or [])
        if not notices:
            raise ValueError('No runtime dependency metadata found.')
        args.output.write_text(render_notices(notices), encoding='utf-8')
    except (ValueError, OSError, metadata.PackageNotFoundError) as error:
        parser.exit(1, f'Inventory failed: {error}\n')
    print(f'Wrote {len(notices)} distributions to {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
