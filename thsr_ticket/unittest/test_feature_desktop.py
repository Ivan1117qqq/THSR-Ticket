import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QObject, QMetaObject, Qt, QUrl  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from shiboken6 import delete  # noqa: E402
from requests import Timeout  # noqa: E402
from thsr_ticket.unittest.test_desktop import qt as qt_fixture, controller as controller_fixture  # noqa: E402
from thsr_ticket.unittest.test_official_booking import CODE, TRIP, page  # noqa: E402
from thsr_ticket.unittest.test_retention import query_run  # noqa: E402
from thsr_ticket.official_booking import parse_official  # noqa: E402
from thsr_ticket.booking_records import record_paths, pending_fingerprint  # noqa: E402
from thsr_ticket.run_records import atomic_json  # noqa: E402
from thsr_ticket.captcha import CaptchaGuess  # noqa: E402

qt = qt_fixture
controller = controller_fixture


def wait_service(service, stage=None):
    deadline = time.monotonic() + 5
    while service.busy and (stage is None or service.stage != stage):
        service.poll()
        if time.monotonic() > deadline:
            raise AssertionError('Feature worker did not complete')
        time.sleep(0.002)
    service.poll()


class OfficialFake:
    def __init__(self, fail_cancel=False):
        self.fail_cancel = fail_cancel
        self.cancel_calls = 0
        self.closed = False

    def open(self, personal_id, code, expected):
        assert personal_id and code == CODE
        return 'data:image/png;base64,AA=='

    def query(self, captcha):
        assert captcha == 'ABCD'
        return parse_official(page(), CODE, TRIP)

    def prepare_cancel(self):
        return parse_official(page(), CODE, TRIP)

    def cancel(self):
        self.cancel_calls += 1
        if self.fail_cancel:
            raise Timeout('private response must not be shown')
        return parse_official(page('已取消'), CODE, TRIP)

    def close(self):
        self.closed = True


def management_ready(controller, fake, pending=False):
    controller.save()
    state, _ = record_paths(controller.path)
    atomic_json(state, {'_record_version': 1, 'status': 'submission_pending' if pending else 'booked',
                        'booking_codes': [CODE], 'outbound_date': '2099-01-15', 'train_id': 117,
                        'start_station': 2, 'dest_station': 7})
    manager = controller.management
    manager.factory = lambda: fake
    manager.start(CODE, pending_fingerprint(controller.path), TRIP)
    wait_service(manager, 'captcha')
    manager.query('ABCD')
    wait_service(manager, 'snapshot')
    assert manager.snapshot['trip_matches']
    return manager, state


@pytest.mark.parametrize('fails', [False, True])
def test_official_cancel_needs_consent_and_never_retries(controller, fails):
    fake = OfficialFake(fails)
    manager, state = management_ready(controller, fake)
    assert controller.running
    manager.confirmCancel(True)  # No reviewed cancellation yet.
    manager.reviewCancel()
    wait_service(manager, 'review')
    manager.confirmCancel(False)
    assert fake.cancel_calls == 0 and state.exists()
    manager.confirmCancel(True)
    wait_service(manager)
    assert fake.cancel_calls == 1 and fake.closed
    assert state.exists() == fails
    assert manager.stage == ('error' if fails else 'cancelled')
    assert 'private response' not in manager.message
    _, runs = record_paths(controller.path)
    evidence = json.loads(next((runs / 'official').glob('*.json')).read_text(encoding='utf-8'))
    assert evidence['status'] == ('cancellation_unconfirmed' if fails else 'cancelled')


def test_query_sync_pending_keeps_guard_and_close_waits_for_browser(controller):
    fake = OfficialFake()
    manager, state = management_ready(controller, fake, pending=True)
    manager.sync()
    wait_service(manager, 'snapshot')
    assert json.loads(state.read_text(encoding='utf-8'))['status'] == 'booked'
    closed = []
    controller.closeReady.connect(lambda: closed.append(True))
    controller.requestClose()
    wait_service(manager)
    controller.poll()
    assert fake.closed and state.exists() and closed


def test_cancellation_review_expires_and_state_change_blocks(controller):
    fake = OfficialFake()
    manager, state = management_ready(controller, fake)
    manager.reviewCancel()
    wait_service(manager, 'review')
    manager._review_time -= 121
    manager.confirmCancel(True)
    assert fake.cancel_calls == 0 and manager.stage == 'snapshot'
    manager.reviewCancel()
    wait_service(manager, 'review')
    atomic_json(state, {'status': 'booked', 'booking_codes': ['87654321']})
    manager.confirmCancel(True)
    wait_service(manager)
    assert fake.cancel_calls == 0 and state.exists() and manager.stage == 'error'


def test_retention_preview_and_confirmation_only_delete_queries(controller):
    controller.save()
    directory = query_run(controller.path)
    protected = query_run(controller.path, 2, result=True)
    service = controller.retention
    service.preview(90)
    wait_service(service)
    assert service.result['count'] == 1 and service.result['protected'] >= 1
    service.apply(False)
    assert directory.exists()
    service.apply(True)
    wait_service(service)
    assert not directory.exists() and protected.exists()
    assert service.result['deleted'] == 1


def test_ocr_lab_labels_and_reports_without_changing_booking_model(controller, tmp_path, monkeypatch):
    folder = tmp_path / 'images'
    folder.mkdir()
    (folder / 'sample.png').write_bytes(b'fake image')
    monkeypatch.setattr('thsr_ticket.desktop.ocr_lab.QFileDialog.getExistingDirectory', lambda *a: str(folder))
    lab = controller.ocrLab
    lab.chooseFolder()
    wait_service(lab)
    assert lab.sample['count'] == 1 and lab.sample['labelled'] == 0
    lab.saveLabel('A7B3')
    wait_service(lab)
    manifest = folder / 'labels.json'
    assert json.loads(manifest.read_text())[0]['label'] == 'A7B3'
    reader = Mock(unavailable=False)
    reader.recognize.return_value = CaptchaGuess('A7B3', 0.9)
    monkeypatch.setattr('thsr_ticket.desktop.ocr_lab.CaptchaReader', Mock(return_value=reader))
    monkeypatch.setattr('thsr_ticket.desktop.ocr_lab.QFileDialog.getOpenFileName', lambda *a: (str(manifest), ''))
    old_model = controller.form['ocr_model']
    lab.evaluateFile(0.5)
    wait_service(lab)
    assert lab.result['models']['standard']['exact_match_rate'] == 1
    assert lab.result['models']['beta']['samples'] == 1
    assert controller.form['ocr_model'] == old_model
    assert 'sample.png' not in json.dumps(lab.result)


def test_retry_reason_and_countdown_follow_worker_events(controller):
    controller._running = True
    controller._messages.put(('event', {'event': 'retry_scheduled', 'phase': 'retry_wait',
                                        'outcome': 'network_retry', 'attempt': 2, 'delay_seconds': 4}))
    controller.poll()
    assert controller.retryReason == '連線暫時失敗'
    assert '秒後重查' in controller.countdown
    controller._running = False
    controller.poll()
    assert controller.retryReason == controller.countdown == ''


def test_actual_qml_cancellation_requires_checkbox(qt, controller, monkeypatch):
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.setInitialProperties({'backend': controller})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / 'desktop/qml/Main.qml')))
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    manager = controller.management
    manager._snapshot = parse_official(page(), CODE, TRIP)
    manager._stage, manager._review_time = 'review', time.monotonic()
    manager.changed.emit()
    sent = Mock()
    monkeypatch.setattr(manager, 'send', sent)
    QMetaObject.invokeMethod(window.findChild(QObject, 'managementDialog'), 'open')
    qt.processEvents()
    submit = window.findChild(QObject, 'submitCancellationButton')
    assert not submit.property('enabled')
    window.findChild(QObject, 'cancellationConsent').setProperty('checked', True)
    qt.processEvents()
    assert submit.property('enabled')
    QMetaObject.invokeMethod(submit, 'clicked', Qt.DirectConnection)
    sent.assert_called_once_with('cancel')
    assert not warnings
    window.setProperty('allowClose', True)
    window.close()
    delete(engine)


def test_python_pagination_filters_and_bounds_records(controller):
    controller._records = [{'code': f'{number:08d}', 'status': 'history', 'current': False,
                            'ticket': {'date': '2099-01-15', 'train_id': str(number)}} for number in range(10000)]
    data = controller.recordPageData(True, '', '', 0, 399)
    assert data['pages'] == 400 and data['total'] == 10000 and len(data['items']) == 25
    assert data['items'][-1]['code'] == '00009999'
    assert controller.recordPageData(False, '', '', 0, 0)['total'] == 0
    assert controller.recordPageData(True, '00009999', '2099', 4, 500)['total'] == 1
    assert controller.recordPageData(True, '', '', 1, 0)['total'] == 0


def test_background_index_is_adopted_and_replacement_invalidates_cache(controller, monkeypatch):
    import threading
    from thsr_ticket.desktop.record_loader import RecordSearchIndex
    from thsr_ticket.unittest.test_desktop import finish_records
    workers = []

    def prepare(entries, cancel=None):
        workers.append(threading.get_ident())
        return RecordSearchIndex(entries, cancel)

    monkeypatch.setattr('thsr_ticket.desktop.record_loader.RecordSearchIndex', prepare)
    monkeypatch.setattr('thsr_ticket.desktop.record_loader.record_entries',
                        lambda *a, **k: [{'code': 'OLD', 'current': True}])
    controller.refresh()
    finish_records(controller)
    prepared = controller._record_loader.search_index
    assert controller._record_search is prepared and prepared.source is controller._records
    assert workers and all(identifier != threading.get_ident() for identifier in workers)
    assert controller.recordPageData(False, 'old', '', 0, 0)['total'] == 1
    controller._records = [{'code': 'NEW', 'current': True}]
    assert controller.recordPageData(False, 'old', '', 0, 0)['total'] == 0
    assert controller.recordPageData(False, 'new', '', 0, 0)['total'] == 1


def test_actual_qml_search_coalesces_typing_enter_and_clear_are_immediate(qt, controller):
    from PySide6.QtTest import QTest
    controller.navigate(3)
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.setInitialProperties({'backend': controller})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / 'desktop/qml/Main.qml')))
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    search = window.findChild(QObject, 'bookingSearch')
    page = window.findChild(QObject, 'bookingsPage')
    for text in ('0', '00', '000', '0001'):
        search.setProperty('text', text)
        qt.processEvents()
    assert page.property('appliedSearch') == ''
    QTest.qWait(350)
    assert page.property('appliedSearch') == '0001'
    search.setProperty('text', '0002')
    QMetaObject.invokeMethod(search, 'accepted', Qt.DirectConnection)
    qt.processEvents()
    assert page.property('appliedSearch') == '0002'
    search.setProperty('text', '')
    qt.processEvents()
    assert page.property('appliedSearch') == ''
    assert not warnings
    window.setProperty('allowClose', True)
    window.close()
    delete(engine)


def test_local_worker_start_failure_is_not_left_busy(controller, monkeypatch):
    monkeypatch.setattr('thsr_ticket.desktop.jobs.threading.Thread.start', Mock(side_effect=RuntimeError()))
    assert not controller.ocrLab.launch('evaluate', lambda: {})
    assert not controller.ocrLab.busy
    assert '無法啟動' in controller.ocrLab.message


def test_ocr_report_export_never_overwrites_booking_or_existing_report(controller, tmp_path, monkeypatch):
    controller.save()
    lab = controller.ocrLab
    lab._report = {'models': {'standard': {'samples': 1}}}
    original = controller.path.read_bytes()
    target = controller.path
    monkeypatch.setattr('thsr_ticket.desktop.ocr_lab.QFileDialog.getSaveFileName', lambda *a: (str(target), ''))
    lab.exportReport()
    wait_service(lab)
    assert controller.path.read_bytes() == original
    target = tmp_path / 'existing.ocr-report.json'
    target.write_text('keep')
    lab.exportReport()
    wait_service(lab)
    assert target.read_text() == 'keep'
    target = tmp_path / 'new.ocr-report.json'
    lab.exportReport()
    wait_service(lab)
    assert json.loads(target.read_text())['models']['standard']['samples'] == 1
    assert lab.result['models']['standard']['samples'] == 1


def test_isolated_review_blocks_real_actions_and_settings_outside_fixture(qt, tmp_path, monkeypatch):
    from PySide6.QtCore import Q_ARG
    from scripts.review_desktop import create_review_data, review_controller
    from thsr_ticket.storage_errors import StorageError
    from thsr_ticket.unittest.test_desktop import finish_records
    root = create_review_data(tmp_path / 'review')
    review = review_controller(root)
    original = root / 'booked/booking.local.json'
    try:
        assert review.load_path(original)
        finish_records(review)
        worker = Mock()
        review.worker = worker
        external = Mock()
        monkeypatch.setattr('thsr_ticket.desktop.controller.QDesktopServices.openUrl', external)
        for query_only in (True, False):
            QMetaObject.invokeMethod(review, 'start', Qt.DirectConnection, Q_ARG(bool, query_only))
        QMetaObject.invokeMethod(review, 'official', Qt.DirectConnection)
        worker.assert_not_called()
        external.assert_not_called()
        with pytest.raises(StorageError):
            review.management.factory()
        outside = tmp_path / 'outside.json'
        outside.write_text('{}')
        assert not review.load_path(outside) and review.path == original
        review.path = outside
        with pytest.raises(ValueError):
            review.save_config()
        assert outside.read_text() == '{}'
    finally:
        review._record_loader.cancel()
        finish_records(review)
        review.timer.stop()
        review.storage._timer.stop()


@pytest.fixture
def date_scene(qt, controller):
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    controller.navigate(1)
    engine.setInitialProperties({'backend': controller})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / 'desktop/qml/Main.qml')))
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    qt.processEvents()
    yield window
    window.setProperty('allowClose', True)
    window.close()
    delete(engine)
    assert not warnings


def open_date(window, key):
    from PySide6.QtTest import QTest
    QMetaObject.invokeMethod(window.findChild(QObject, 'calendar_' + key), 'clicked', Qt.DirectConnection)
    QTest.qWait(180)
    popup = window.findChild(QObject, 'datePicker_' + key)
    assert popup is not None and popup.property('opened')
    return popup


@pytest.mark.parametrize('initial,axis,expected', [
    ('2024-01-31', 'month', '2024-02-29'), ('2023-01-31', 'month', '2023-02-28'),
    ('2100-01-31', 'month', '2100-02-28'), ('2000-01-31', 'month', '2000-02-29'),
    ('2024-03-31', 'month', '2024-04-30'), ('2024-02-29', 'year', '2025-02-28')])
def test_date_wheels_adjust_month_length_and_leap_years(date_scene, controller, initial, axis, expected):
    from PySide6.QtTest import QTest
    controller.setField('outbound_date', initial)
    popup = open_date(date_scene, 'outbound_date')
    wheel = date_scene.findChild(QObject, popup.objectName() + '_' + axis)
    wheel.forceActiveFocus()
    QTest.keyClick(date_scene, Qt.Key_Down)
    QTest.qWait(100)
    assert popup.property('selectedDate') == expected
    assert controller.form['outbound_date'] == initial
    button = date_scene.findChild(QObject, popup.objectName() + '_apply')
    QMetaObject.invokeMethod(button, 'clicked', Qt.DirectConnection)
    assert controller.form['outbound_date'] == expected


@pytest.mark.parametrize('axis', ['year', 'month', 'day'])
def test_each_date_wheel_responds_to_mouse_scrolling(date_scene, controller, qt, axis):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    controller.setField('outbound_date', '2099-01-15')
    popup = open_date(date_scene, 'outbound_date')
    if axis == 'day':
        date_scene.findChild(QObject, popup.objectName() + '_month').forceActiveFocus()
        QTest.keyClick(date_scene, Qt.Key_Down)
        QTest.qWait(100)
        assert popup.property('selectedDate') == '2099-02-15'
    wheel = date_scene.findChild(QObject, popup.objectName() + '_' + axis)
    position = wheel.mapToScene(QPointF(wheel.width() / 2, wheel.height() / 2))
    before = wheel.property('value')
    event = QWheelEvent(position, QPointF(date_scene.mapToGlobal(position.toPoint())), QPoint(), QPoint(0, -120),
                        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    qt.sendEvent(date_scene, event)
    QTest.qWait(300)
    assert wheel.property('value') > before
    assert controller.form['outbound_date'] == '2099-01-15'


def test_date_wheel_can_be_dragged_vertically(date_scene, controller):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtTest import QTest
    controller.setField('outbound_date', '2099-01-15')
    popup = open_date(date_scene, 'outbound_date')
    wheel = date_scene.findChild(QObject, popup.objectName() + '_day')
    position = wheel.mapToScene(QPointF(wheel.width() / 2, wheel.height() / 2)).toPoint()
    QTest.mousePress(date_scene, Qt.LeftButton, Qt.NoModifier, position)
    for distance in (16, 32, 48, 64, 80):
        QTest.mouseMove(date_scene, position - QPoint(0, distance), 25)
    QTest.mouseRelease(date_scene, Qt.LeftButton, Qt.NoModifier, position - QPoint(0, 80))
    QTest.qWait(300)
    assert wheel.property('value') != 15
    assert 1 <= popup.property('day') <= 31


def test_cancelled_date_is_not_saved_and_reopening_uses_current_value(date_scene, controller):
    from PySide6.QtTest import QTest
    controller.setField('outbound_date', '2099-01-15')
    popup = open_date(date_scene, 'outbound_date')
    date_scene.findChild(QObject, popup.objectName() + '_day').setProperty('currentIndex', 19)
    assert popup.property('selectedDate') == '2099-01-20'
    button = date_scene.findChild(QObject, popup.objectName() + '_cancel')
    QMetaObject.invokeMethod(button, 'clicked', Qt.DirectConnection)
    QTest.qWait(180)
    assert controller.form['outbound_date'] == '2099-01-15'
    assert date_scene.findChild(QObject, 'calendar_outbound_date').property('activeFocus')
    assert open_date(date_scene, 'outbound_date').property('selectedDate') == '2099-01-15'


def test_start_date_picker_preserves_existing_time(date_scene, controller):
    controller.setField('start_at', '2099-01-15 17:25:30')
    popup = open_date(date_scene, 'start_at')
    date_scene.findChild(QObject, popup.objectName() + '_day').setProperty('currentIndex', 15)
    button = date_scene.findChild(QObject, popup.objectName() + '_apply')
    QMetaObject.invokeMethod(button, 'clicked', Qt.DirectConnection)
    assert controller.form['start_at'] == '2099-01-16 17:25:30'


def test_reopened_date_picker_reads_replaced_year_month_and_day(date_scene, controller):
    from PySide6.QtTest import QTest
    controller.setField('outbound_date', '2024-02-29')
    popup = open_date(date_scene, 'outbound_date')
    assert popup.property('selectedDate') == '2024-02-29'
    QMetaObject.invokeMethod(popup, 'close')
    QTest.qWait(180)
    controller.setField('outbound_date', '2099-07-21')
    popup = open_date(date_scene, 'outbound_date')
    assert popup.property('selectedDate') == '2099-07-21'
    assert [date_scene.findChild(QObject, popup.objectName() + '_' + axis).property('value')
            for axis in ('year', 'month', 'day')] == [2099, 7, 21]
