import ast
import hashlib
import json

import pytest

from scripts.release_metadata import prepare, finalize, read_version


def project(tmp_path, version):
    package = tmp_path / 'thsr_ticket'
    package.mkdir(exist_ok=True)
    (package / 'version.py').write_text(f'VERSION = {version!r}\n', encoding='utf-8')
    return tmp_path


def test_version_change_updates_installer_and_windows_resource(tmp_path):
    root = project(tmp_path, '1.2.3')
    prepare(root)
    project(tmp_path, '1.2.4')
    data = prepare(root)
    assert data['version'] == '1.2.4'
    assert data['installer_filename'] == 'TravelDesk-Setup-1.2.4.exe'
    assert '"1.2.4"' in (root / 'build/release/version.iss').read_text()
    tree = ast.parse((root / 'build/release/version_info.txt').read_text())
    versions = [ast.literal_eval(keyword.value) for node in ast.walk(tree) if isinstance(node, ast.Call)
                for keyword in node.keywords if keyword.arg in ('filevers', 'prodvers')]
    assert versions == [(1, 2, 4, 0), (1, 2, 4, 0)]


def test_finalize_records_exact_installer_hash(tmp_path):
    root = project(tmp_path, '1.2.3')
    installer = root / 'dist/installer/TravelDesk-Setup-1.2.3.exe'
    installer.parent.mkdir(parents=True)
    installer.write_bytes(b'synthetic-installer')
    data = finalize(root)
    assert data['sha256'] == hashlib.sha256(installer.read_bytes()).hexdigest().upper()
    assert data['bytes'] == installer.stat().st_size
    assert not data['signed']
    assert json.loads((root / 'dist/release.json').read_text()) == data
    assert installer.with_suffix('.sha256').read_text().split()[0] == data['sha256']


@pytest.mark.parametrize('version', ['1.2', 'v1.2.3', '1.2.3-beta', '70000.2.3'])
def test_unsupported_version_is_rejected_without_generated_files(tmp_path, version):
    root = project(tmp_path, version)
    with pytest.raises(ValueError):
        prepare(root)
    assert not (root / 'build').exists()


def test_version_reader_never_executes_source_code(tmp_path):
    root = project(tmp_path, '1.2.3')
    (root / 'thsr_ticket/version.py').write_text("raise RuntimeError('must not execute')\nVERSION = '1.2.3'\n")
    assert read_version(root) == '1.2.3'
