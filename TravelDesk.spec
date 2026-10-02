# Build with: python -m PyInstaller TravelDesk.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH)
datas = [(str(root / 'thsr_ticket/desktop/qml'), 'thsr_ticket/desktop/qml')]
datas += collect_data_files('ddddocr')
binaries = collect_dynamic_libs('onnxruntime')
a = Analysis(
    [str(root / 'desktop_launcher.py')], pathex=[str(root)], datas=datas, binaries=binaries,
    hiddenimports=['PySide6.QtQuick', 'PySide6.QtQuickControls2', 'playwright.sync_api', 'ddddocr'],
    excludes=['tkinter', 'pytest', 'mypy', 'pylint', 'flake8', 'thsr_ticket.unittest', 'tensorflow', 'torch'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TravelDesk', console=False)
coll = COLLECT(exe, a.binaries, a.datas, name='TravelDesk')
