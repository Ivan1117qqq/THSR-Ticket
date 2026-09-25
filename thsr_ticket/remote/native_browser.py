"""Start an isolated installed browser with a localhost-only debugging endpoint."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
from typing import Optional


def browser_executable(channel: str) -> str:
    names = {'chrome': ('google-chrome', 'google-chrome-stable', 'chrome'),
             'msedge': ('microsoft-edge', 'msedge')}[channel]
    for name in names:
        if found := shutil.which(name):
            return found
    relative = {'chrome': 'Google/Chrome/Application/chrome.exe',
                'msedge': 'Microsoft/Edge/Application/msedge.exe'}[channel]
    for root in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        if directory := os.environ.get(root):
            candidate = Path(directory) / relative
            if candidate.is_file():
                return str(candidate)
    mac = {'chrome': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
           'msedge': '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'}[channel]
    if Path(mac).is_file():
        return mac
    raise RuntimeError(f'找不到 {channel}，請先安裝瀏覽器。')


class NativeBrowser:
    def __init__(self, channel: str) -> None:
        self.executable = browser_executable(channel)
        self.temp_root = Path(tempfile.gettempdir()).resolve()
        self.profile: Optional[Path] = None
        self.process: Optional[subprocess.Popen] = None

    def start(self) -> str:
        self.profile = Path(tempfile.mkdtemp(prefix='thsr-browser-', dir=self.temp_root)).resolve()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        args = [self.executable, '--remote-debugging-address=127.0.0.1',
                f'--remote-debugging-port={port}', f'--user-data-dir={self.profile}',
                '--no-first-run', '--no-default-browser-check', 'about:blank']
        startup = None
        if os.name == 'nt':
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
        try:
            self.process = subprocess.Popen(args, startupinfo=startup,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.close()
            raise
        return f'http://127.0.0.1:{port}'

    def close(self) -> None:
        if self.process is not None:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
        if self.profile is not None:
            # Never recursively delete a caller-supplied path or a real browser profile.
            target = self.profile.resolve()
            if target.parent != self.temp_root or not target.name.startswith('thsr-browser-'):
                raise RuntimeError('拒絕清理非本程式建立的瀏覽器目錄。')
            try:
                shutil.rmtree(target)
            except FileNotFoundError:
                pass
            except OSError:
                # Browser child processes can briefly hold files on Windows.
                print(f'暫存瀏覽器目錄仍被占用，未刪除：{target}')
