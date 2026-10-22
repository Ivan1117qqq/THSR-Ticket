"""Generate a separate-AppId installer from the real template for safe local tests."""
import argparse
import json
import re
from pathlib import Path

TEST_APP_ID = 'AC67957F-3FE3-43AC-A675-23228CC39418'


def generate(root, payload, version, output):
    root, payload, output = Path(root).resolve(), Path(payload).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / 'build') or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Test output must stay inside build; version must be major.minor.patch')
    import pefile
    with pefile.PE(str(payload / 'TravelDesk.exe'), fast_load=True) as executable:
        executable.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
        info = executable.VS_FIXEDFILEINFO[0]
        actual = f'{info.FileVersionMS >> 16}.{info.FileVersionMS & 65535}.{info.FileVersionLS >> 16}'
    if actual != version:
        raise ValueError('Payload EXE version differs from test installer version')
    output.mkdir(parents=True, exist_ok=True)
    text = (root / 'installer/TravelDesk.iss').read_text(encoding='utf-8-sig')
    text = f'#define AppVersion "{version}"\n' + text
    replacements = {
        'AppId={{757AC553-6205-4B6B-ACB3-C6F68972804B}': 'AppId={{' + TEST_APP_ID + '}',
        'AppName=Travel Desk': 'AppName=Travel Desk Isolated Test',
        'DefaultDirName={localappdata}\\Programs\\TravelDesk':
            'DefaultDirName={localappdata}\\Programs\\TravelDeskIsolatedTest',
        'DefaultGroupName=Travel Desk': 'DefaultGroupName=Travel Desk Isolated Test',
        'OutputDir=..\\dist\\installer': 'OutputDir=' + str(output),
        'SetupIconFile=..\\build\\icons\\app.ico': 'SetupIconFile=' + str(root / 'build/icons/app.ico'),
        'Default.isl,TraditionalChinese.isl': 'Default.isl,' + str(root / 'installer/TraditionalChinese.isl'),
        'Source: "..\\dist\\TravelDesk\\*"': 'Source: "' + str(payload / '*') + '"',
        'Compression=lzma2': 'Compression=none',
        'SolidCompression=yes': 'SolidCompression=no',
        '{group}\\Travel Desk"': '{group}\\Travel Desk Isolated Test"',
        '{autodesktop}\\Travel Desk"': '{autodesktop}\\Travel Desk Isolated Test"',
    }
    for before, after in replacements.items():
        if before not in text:
            raise ValueError('Installer template changed: ' + before)
        text = text.replace(before, after)
    path = output / 'isolated.iss'
    path.write_text(text, encoding='utf-8-sig')
    return {'script': str(path), 'app_id': TEST_APP_ID, 'version': version,
            'installer': str(output / f'TravelDesk-Setup-{version}.exe')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(generate(Path(__file__).resolve().parents[1], args.payload, args.version, args.output), indent=2))


if __name__ == '__main__':
    main()
