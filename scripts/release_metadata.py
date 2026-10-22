"""Generate every Windows version field from thsr_ticket/version.py."""
import argparse
import ast
import hashlib
import json
import re
from pathlib import Path


def read_version(root):
    tree = ast.parse((Path(root) / 'thsr_ticket/version.py').read_text(encoding='utf-8'))
    values = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets)]
    if len(values) != 1 or not isinstance(values[0], str) or not re.fullmatch(r'\d+\.\d+\.\d+', values[0]):
        raise ValueError('VERSION must be a single literal major.minor.patch string')
    if any(int(part) > 65535 for part in values[0].split('.')):
        raise ValueError('Windows version fields must fit unsigned 16-bit values')
    return values[0]


def prepare(root):
    root = Path(root)
    version = read_version(root)
    directory = root / 'build/release'
    directory.mkdir(parents=True, exist_ok=True)
    numeric = ','.join(version.split('.') + ['0'])
    resource = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numeric}), prodvers=({numeric}), mask=0x3f,
                    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Travel Desk Project'),
    StringStruct('FileDescription', 'Travel Desk - THSR journey manager'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'TravelDesk'),
    StringStruct('OriginalFilename', 'TravelDesk.exe'),
    StringStruct('ProductName', 'Travel Desk'),
    StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"""
    (directory / 'version_info.txt').write_text(resource, encoding='utf-8')
    (directory / 'version.iss').write_text(f'#define AppVersion "{version}"\n', encoding='utf-8')
    metadata = {'version': version, 'installer_filename': f'TravelDesk-Setup-{version}.exe', 'signed': False}
    (directory / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return metadata


def finalize(root):
    root = Path(root)
    metadata = prepare(root)
    installer = root / 'dist/installer' / metadata['installer_filename']
    digest = hashlib.sha256()
    with installer.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    metadata.update(sha256=digest.hexdigest().upper(), bytes=installer.stat().st_size)
    installer.with_suffix('.sha256').write_text(f'{metadata["sha256"]}  {installer.name}\n', encoding='utf-8')
    (root / 'dist/release.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(finalize(root) if args.finalize else prepare(root), indent=2))


if __name__ == '__main__':
    main()
