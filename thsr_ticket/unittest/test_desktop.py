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
