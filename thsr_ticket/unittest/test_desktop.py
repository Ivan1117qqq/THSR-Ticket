import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtCore import QUrl, QObject, QMetaObject, Qt  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from thsr_ticket.desktop.controller import DesktopController, form_values  # noqa: E402
from thsr_ticket.unittest.test_gui import values  # noqa: E402
from thsr_ticket.application import form_config  # noqa: E402
from thsr_ticket.booking_records import pending_fingerprint  # noqa: E402
from thsr_ticket.task_status import save_task  # noqa: E402


@pytest.fixture(scope='module')
def qt():
    QQuickStyle.setStyle('Basic')
    app = QApplication.instance() or QApplication([])
    # Windows offscreen plugin has no system font fallback; load installed fonts for render tests.
    for name in ('msjh.ttc', 'msjhbd.ttc'):
        font = Path('C:/Windows/Fonts') / name
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    return app


@pytest.fixture
def controller(qt, tmp_path):
    controller = DesktopController(tmp_path, worker=Mock())
    controller._form = values()
    yield controller
    controller.timer.stop()


def test_diagnostic_preview_exports_exact_snapshot_without_overwrite(controller, tmp_path, monkeypatch):
    controller._messages.put(('event', {'event': 'run_stopped', 'reason': 'network_timeout',
                                        'code': 'SECRET-BOOKING'}))
    controller.poll()
    controller.prepareDiagnostics()
    preview = controller.diagnosticPreview
    assert 'SECRET-BOOKING' not in preview
    target = tmp_path / 'support.diagnostics.json'
    monkeypatch.setattr('thsr_ticket.desktop.controller.QFileDialog.getSaveFileName',
                        lambda *args: (str(target), ''))
    controller._diagnostic_events.append({'event': 'run_finished'})
    controller.exportDiagnostics()
    assert target.read_text(encoding='utf-8') == preview + '\n'
    target.write_text('existing')
    controller.exportDiagnostics()
    assert target.read_text() == 'existing'


def test_diagnostic_cancel_and_config_destination_are_safe(controller, tmp_path, monkeypatch):
    controller.prepareDiagnostics()
    target = tmp_path / 'booking.local.json'
    for destination in ('', str(target)):
        monkeypatch.setattr('thsr_ticket.desktop.controller.QFileDialog.getSaveFileName',
                            lambda *args: (destination, ''))
        controller.exportDiagnostics()
        assert not target.exists()


def test_startup_pending_is_visible_even_without_config(qt, tmp_path):
    state = tmp_path / 'booking.local.state.json'
    state.write_text('{"status":"submission_pending"}')
    instance = DesktopController(tmp_path, worker=Mock())
    try:
        assert instance.task['code'] == 'pending'
        assert not instance.task['can_book']
        instance.taskAction()
        assert instance.page == 3
        instance.start(False)
        instance.worker.assert_not_called()
        assert state.exists()
    finally:
        instance.timer.stop()


def test_reopen_failed_task_and_switch_config_resets_summary(controller, qt, tmp_path):
    controller.save_config()
    save_task(controller.path, 'network', True)
    reopened = DesktopController(tmp_path, worker=Mock())
    try:
        assert reopened.task['code'] == 'network'
        reopened.taskAction()
        assert reopened.page == 1
        reopened.worker.assert_not_called()
        other = tmp_path / 'other.json'
        other.write_text(form_config(values()).json(), encoding='utf-8')
        assert reopened.load_path(other)
        assert reopened.task['code'] == 'idle'
    finally:
        reopened.timer.stop()


def test_crashed_worker_persists_interruption_without_restart(controller):
    controller.worker = Mock()
    controller.start(True)
    controller._thread.join(3)
    controller.poll()
    assert controller.task['code'] == 'interrupted'
    controller.worker.assert_called_once()
    assert json.loads(controller.path.with_suffix('.task.json').read_text())['code'] == 'interrupted'


def test_resolve_pending_clears_recovery_without_erasing_history(controller):
    state = controller.path.with_suffix('.state.json')
    state.write_text('{"status":"submission_pending"}')
    save_task(controller.path, 'booking_unconfirmed', False)
    controller.refresh()
    controller.resolve(pending_fingerprint(controller.path), 'not_booked', '', True)
    assert controller.task['code'] == 'finished'
    assert controller.task['can_book']
    assert any(row.get('resolution') == 'not_booked' for row in controller.records)


def test_summary_save_failure_is_visible_but_never_overrides_booking(controller, monkeypatch):
    monkeypatch.setattr('thsr_ticket.desktop.controller.save_task', Mock(side_effect=OSError()))
    controller.persist_task('network')
    controller.refresh()
    assert controller.task['code'] == 'network'
    assert '摘要無法保存' in controller.task['detail']
    controller.path.with_suffix('.state.json').write_text('{"status":"submission_pending"}')
    controller.refresh()
    assert controller.task['code'] == 'pending'
    assert not controller.task['can_book']


def test_thread_start_failure_does_not_leave_ui_running(controller, monkeypatch):
    thread = Mock()
    thread.start.side_effect = RuntimeError()
    monkeypatch.setattr('thsr_ticket.desktop.controller.threading.Thread', Mock(return_value=thread))
    controller.start(True)
    assert not controller.running
    assert controller.task['code'] == 'operation_failed'
    controller.worker.assert_not_called()


def test_cancellation_link_does_not_change_state(controller, monkeypatch):
    state = controller.path.with_suffix('.state.json')
    state.write_text('{"status":"booked","booking_codes":["TEST1234"]}')
    original = state.read_bytes()
    controller.refresh()
    opened = Mock(return_value=True)
    monkeypatch.setattr('thsr_ticket.desktop.controller.QDesktopServices.openUrl', opened)
    assert not controller.openCancellation('OTHER')
    opened.assert_not_called()
    assert controller.openCancellation('TEST1234')
    assert 'History' in opened.call_args.args[0].toString()
    assert state.read_bytes() == original
    controller.confirmCancellation('TEST1234', pending_fingerprint(controller.path), False)
    assert state.read_bytes() == original
    controller._running = True
    assert not controller.openCancellation('TEST1234')
    controller.confirmCancellation('TEST1234', pending_fingerprint(controller.path), True)
    assert state.read_bytes() == original
    controller._running = False
    controller.confirmCancellation('TEST1234', pending_fingerprint(controller.path), True)
    assert not state.exists()


def test_load_preserves_existing_state_location(controller, tmp_path):
    directory = tmp_path / 'legacy'
    directory.mkdir()
    config = directory / 'booking.local.json'
    config.write_text(form_config(values()).json(), encoding='utf-8')
    state = config.with_suffix('.state.json')
    state.write_text('{"status":"booked","booking_codes":["TEST1234"]}')
    assert controller.load_path(config)
    assert controller.path == config
    controller.start(False)
    controller.worker.assert_not_called()
    assert controller.page == 3 and state.exists()


def test_controller_saves_and_worker_gets_mode(controller, qt):
    def worker(config, path, query_only, stop, messages):
        assert query_only
        messages.put(('done', 'test complete'))
    controller.worker = worker
    controller.start(True)
    controller._thread.join(timeout=3)
    controller.poll()
    assert not controller.running and controller._thread is None
    assert controller.path.exists()
    assert controller.phase == 'test complete'


def test_controller_stops_cooperatively_and_prevents_second_start(controller):
    def worker(config, path, query_only, stop, messages):
        stop.wait(3)
        messages.put(('done', 'stopped'))
    controller.worker = Mock(side_effect=worker)
    controller.start(True)
    controller.start(False)
    original = controller.form['personal_id']
    controller.setField('personal_id', 'CHANGED')
    assert controller.form['personal_id'] == original
    controller.requestClose()
    controller._thread.join(timeout=4)
    ready = Mock()
    controller.closeReady.connect(ready)
    controller.poll()
    ready.assert_called_once()
    controller.worker.assert_called_once()


def test_controller_pending_requires_verified_resolution(controller):
    state = controller.path.with_suffix('.state.json')
    state.write_text('{"status":"submission_pending"}')
    fingerprint = pending_fingerprint(controller.path)
    controller.resolve(fingerprint, 'not_booked', '', False)
    assert state.exists() and controller.error
    controller.resolve(fingerprint, 'not_booked', '', True)
    assert not state.exists()
    assert controller.records[0]['status'] == 'resolved'


def test_invalid_input_does_not_launch_worker(controller):
    controller.setField('interval_seconds', '0')
    controller.start(False)
    controller.worker.assert_not_called()
    assert controller.error and 'interval_seconds' in controller.issues
    assert not controller.path.exists()


def test_remembers_external_path_and_guard(controller, tmp_path):
    path = tmp_path / 'external.json'
    path.write_text(form_config(values()).json(), encoding='utf-8')
    path.with_suffix('.state.json').write_text('{"status":"submission_pending"}')
    assert controller.load_path(path)
    restored = DesktopController(controller.data_dir, worker=Mock())
    try:
        assert restored.path == path
        restored.start(False)
        restored.worker.assert_not_called()
        assert restored.page == 3
    finally:
        restored.timer.stop()


def test_unsaved_close_requires_explicit_choice(controller):
    ready, question = Mock(), Mock()
    controller.closeReady.connect(ready)
    controller.confirmRequested.connect(question)
    controller.setField('phone_num', '0912345678')
    controller.requestClose()
    question.assert_called_once_with('close')
    ready.assert_not_called()
    controller.confirmAction('close', 'cancel')
    ready.assert_not_called()
    controller.confirmAction('close', 'save')
    assert not controller.dirty
    ready.assert_called_once()


def test_corrupt_preferences_do_not_break_startup(qt, tmp_path):
    (tmp_path / 'preferences.json').write_text('broken')
    desktop = DesktopController(tmp_path)
    assert desktop.path == tmp_path / 'booking.local.json'
    desktop.timer.stop()


def test_completion_error_preserves_recovery(controller):
    controller._messages.put(('completion', {'code': 'booking_unconfirmed', 'action': 'records'}))
    controller._messages.put(('done', 'needs verification'))
    controller.poll()
    assert controller.error and controller.recovery == 'records'
    controller.recover()
    assert controller.page == 3


def test_integer_errors_are_attached_to_field(controller):
    controller.setField('adult_tickets', '1.5')
    controller.save()
    assert controller.error and 'adult_tickets' in controller.issues


def test_template_requires_save_as(controller, tmp_path):
    path = tmp_path / 'booking.example.json'
    path.write_text(form_config(values()).json(), encoding='utf-8')
    original = path.read_bytes()
    assert controller.load_path(path)
    controller.save()
    assert controller.error and path.read_bytes() == original


def test_progress_train_and_unexpected_worker_exit(controller):
    controller._messages.put(('event', {
        'event': 'train_selected', 'train_id': '0117', 'depart': '09:31', 'arrive': '10:18'}))
    controller.poll()
    assert controller.match['train_id'] == '0117'
    controller.worker = lambda *args: None
    controller.start(True)
    controller._thread.join(timeout=3)
    controller.poll()
    assert controller.error and not controller.running


def test_form_round_trip_and_rejects_state():
    config = form_config(values())
    config.start_at = config.start_at.replace(microsecond=0)
    assert form_config(form_values(json.loads(config.json()))) == config
    with pytest.raises(ValueError):
        form_values({'status': 'booked'})


def test_qml_pages_render_without_errors(qt, controller, tmp_path):
    warnings = []
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.setInitialProperties({'backend': controller})
    qml = Path(__file__).parents[1] / 'desktop' / 'qml' / 'Main.qml'
    engine.load(QUrl.fromLocalFile(str(qml)))
    assert engine.rootObjects(), warnings
    root = engine.rootObjects()[0]
    controller.navigate(1)
    qt.processEvents()
    entry = root.findChild(QObject, 'personal_id')
    eye = root.findChild(QObject, 'reveal_personal_id')
    assert entry.property('displayText') != controller.form['personal_id']
    assert QMetaObject.invokeMethod(eye, 'clicked', Qt.DirectConnection)
    assert entry.property('displayText') == controller.form['personal_id']
    controller.resetSecrets.emit()
    assert entry.property('displayText') != controller.form['personal_id']
    controller._records = [{'current': True, 'status': 'booked', 'code': 'TEST1234',
                            'ticket': {'start_station': '台北', 'dest_station': '台中'}}]
    controller.changed.emit()
    for page in range(5):
        controller.navigate(page)
        for _ in range(5):
            qt.processEvents()
        frame = root.grabWindow()
        assert not frame.isNull()
    root.resize(1080, 720)
    controller.navigate(1)
    qt.processEvents()
    assert not root.grabWindow().isNull()
    assert not warnings
    root.setProperty('allowClose', True)
    root.close()
    engine.deleteLater()
    qt.processEvents()
