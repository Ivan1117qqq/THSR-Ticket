from pathlib import Path

import pytest

from thsr_ticket.remote.native_browser import NativeBrowser


@pytest.mark.parametrize('location', ['wrong-name', 'outside/thsr-browser-test'])
def test_cleanup_refuses_unowned_profile(tmp_path, monkeypatch, location):
    monkeypatch.setattr('thsr_ticket.remote.native_browser.browser_executable', lambda channel: 'chrome')
    browser = NativeBrowser('chrome')
    browser.temp_root = tmp_path.resolve()
    target = tmp_path / location
    target.mkdir(parents=True)
    marker = target / 'keep.txt'
    marker.write_text('keep', encoding='utf-8')
    browser.profile = target
    with pytest.raises(RuntimeError):
        browser.close()
    assert marker.read_text(encoding='utf-8') == 'keep'


def test_failed_launch_removes_own_temp_profile(tmp_path, monkeypatch):
    monkeypatch.setattr('thsr_ticket.remote.native_browser.browser_executable', lambda channel: 'chrome')

    def fail_launch(*args, **kwargs):
        raise OSError('cannot start browser')

    monkeypatch.setattr('thsr_ticket.remote.native_browser.subprocess.Popen', fail_launch)
    browser = NativeBrowser('chrome')
    browser.temp_root = Path(tmp_path).resolve()
    with pytest.raises(OSError):
        browser.start()
    assert not browser.profile.exists()
