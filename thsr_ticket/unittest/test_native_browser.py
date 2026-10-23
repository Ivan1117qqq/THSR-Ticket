from pathlib import Path
import shutil
from unittest.mock import Mock

import pytest

from thsr_ticket.remote.native_browser import NativeBrowser
from thsr_ticket.remote.browser_request import BrowserRequest


@pytest.mark.parametrize('location', ['wrong-name', 'outside/thsr-browser-test', 'thsr-browser-not-owned'])
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


def owned_browser(tmp_path, monkeypatch):
    monkeypatch.setattr('thsr_ticket.remote.native_browser.browser_executable', lambda channel: 'chrome')
    monkeypatch.setattr('thsr_ticket.remote.native_browser.subprocess.Popen', Mock(return_value=Mock()))
    monkeypatch.setattr('thsr_ticket.remote.native_browser.time.sleep', Mock())
    browser = NativeBrowser('chrome')
    browser.temp_root = tmp_path.resolve()
    browser.start()
    return browser


def test_profile_cleanup_waits_for_temporary_file_locks(tmp_path, monkeypatch):
    browser = owned_browser(tmp_path, monkeypatch)
    remove = shutil.rmtree
    failures = [PermissionError(), PermissionError()]

    def delayed_remove(path):
        if failures:
            raise failures.pop()
        remove(path)

    monkeypatch.setattr('thsr_ticket.remote.native_browser.shutil.rmtree', delayed_remove)
    browser.close()
    assert not browser.profile.exists()
    browser.close()  # Already-cleaned owned profiles remain safe to close again.


def test_permanent_file_lock_has_a_finite_cleanup_limit(tmp_path, monkeypatch):
    browser = owned_browser(tmp_path, monkeypatch)
    marker = browser.profile / 'locked'
    marker.write_text('keep')
    remove = Mock(side_effect=PermissionError())
    monkeypatch.setattr('thsr_ticket.remote.native_browser.shutil.rmtree', remove)
    browser.close()
    assert remove.call_count == 5 and marker.read_text() == 'keep'


def test_cleanup_revalidates_owned_path_after_each_lock_retry(tmp_path, monkeypatch):
    browser = owned_browser(tmp_path, monkeypatch)
    foreign = tmp_path / 'thsr-browser-foreign'
    foreign.mkdir()
    marker = foreign / 'keep'
    marker.write_text('keep')

    def changed_path(path):
        browser.profile = foreign
        raise PermissionError()

    remove = Mock(side_effect=changed_path)
    monkeypatch.setattr('thsr_ticket.remote.native_browser.shutil.rmtree', remove)
    with pytest.raises(RuntimeError):
        browser.close()
    assert remove.call_count == 1 and marker.read_text() == 'keep'


@pytest.mark.parametrize('native', [False, True])
def test_browser_shutdown_sends_cdp_exit_only_to_its_own_native_instance(native):
    client = BrowserRequest.__new__(BrowserRequest)
    client.browser, client.driver, client.sess = Mock(), Mock(), Mock()
    client.native = Mock() if native else None
    client.browser_error = RuntimeError
    client.close()
    if native:
        client.browser.new_browser_cdp_session.return_value.send.assert_called_once_with('Browser.close')
        client.native.close.assert_called_once()
    else:
        client.browser.new_browser_cdp_session.assert_not_called()
    client.driver.stop.assert_called_once()
    client.sess.close.assert_called_once()


def test_native_shutdown_still_releases_resources_if_chrome_closes_the_channel():
    client = BrowserRequest.__new__(BrowserRequest)
    client.browser, client.driver, client.sess, client.native = Mock(), Mock(), Mock(), Mock()
    client.browser_error = RuntimeError
    client.browser.new_browser_cdp_session.return_value.send.side_effect = RuntimeError()
    client.browser.close.side_effect = RuntimeError()
    client.close()
    client.driver.stop.assert_called_once()
    client.native.close.assert_called_once()
    client.sess.close.assert_called_once()
