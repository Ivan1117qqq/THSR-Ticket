"""Dual operator UI lifetime, guard checks and manual reconciliation using synthetic jobs."""
import json
import threading
from pathlib import Path
from uuid import uuid4

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QObject, QMetaObject, Qt, QUrl  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from shiboken6 import delete  # noqa: E402
from thsr_ticket.tra_booking import TraOptions  # noqa: E402
from thsr_ticket.unittest.test_desktop import qt as qt_fixture, controller as base_controller  # noqa: E402
from thsr_ticket.unittest.test_desktop import finish_records  # noqa: E402
from thsr_ticket.unittest.test_dual_rail import config  # noqa: E402
from thsr_ticket.unittest.test_planner_desktop import visual_item  # noqa: E402

qt = qt_fixture
controller = base_controller


def finish(service):
    if service.session:
        service.stop()
        for thread in service.session.threads.values():
            thread.join(3)
            assert not thread.is_alive()
        service.poll()


def test_both_jobs_receive_same_frozen_schedule_and_parent_blocks_other_work(controller):
    service = controller.dualRail
    entered = threading.Barrier(3)
    seen = []

    def thsr(conf, path, query_only, stop, messages):
        seen.append(conf)
        entered.wait(3)
        stop.wait(3)
        messages.put(('completion', {'code': 'stopped', 'message': '已停止'}))

    def tra(conf, options, directory, stop, emit, **kwargs):
        seen.append(conf)
        entered.wait(3)
        stop.wait(3)
        emit('stopped', '已停止')

    service.worker, service.tra_worker = thsr, tra
    assert service.start()
    try:
        entered.wait(3)
        assert controller.running and not controller.task['can_book']
        assert seen[0] is seen[1]
        saved = controller.path.read_bytes()
        original = dict(controller.form)
        controller.setField('dest_station', '左營')
        controller.save()
        assert dict(controller.form) == original and controller.path.read_bytes() == saved
        assert not service.start()
        assert not service.archive(True)
        assert not service.confirmResult('12345678', True)
    finally:
        finish(service)
    assert not controller.running
    assert 'personal_id' not in service.preferences.read_text(encoding='utf-8')
    assert 'phone_num' not in service.preferences.read_text(encoding='utf-8')


@pytest.mark.parametrize('operator', ['thsr', 'tra'])
def test_either_existing_record_blocks_both_jobs_before_launch(controller, operator):
    service = controller.dualRail
    path = controller.path.with_suffix('.state.json') if operator == 'thsr' else service.records.path
    path.write_text('{"status":"pending"}', encoding='utf-8')
    assert not service.start() and service.session is None
    assert path.read_text(encoding='utf-8') == '{"status":"pending"}'


def test_manual_reconciliation_and_archive_require_confirmation(controller):
    service = controller.dualRail
    service.records.pending(uuid4().hex, config(), TraOptions('臺北', '臺中'))
    service.refresh_record()
    before = service.records.path.read_bytes()
    assert not service.confirmResult('12345678', False)
    assert not service.archive(False)
    assert service.records.path.read_bytes() == before
    assert service.confirmResult('12345678', True)
    assert service.record['status'] == 'booked' and service.record['booking_code'] == '12345678'
    assert service.records.read()['source'] == 'user_confirmed'
    assert service.archive(True)
    archived = list((controller.data_dir / 'tra-booking.history').glob('*.json'))
    assert len(archived) == 1 and json.loads(archived[0].read_text(encoding='utf-8'))['booking_code'] == '12345678'
    assert not service.record


def test_corrupt_preferences_and_unknown_records_are_never_overwritten(controller):
    service = controller.dualRail
    service.preferences.write_text('{"version":99}', encoding='utf-8')
    service.read_preferences()
    assert not service.save() and not service.start()
    assert service.preferences.read_text(encoding='utf-8') == '{"version":99}'
    service.records.path.write_text('{"version":99}', encoding='utf-8')
    service.refresh_record()
    assert service.record['status'] == 'unreadable'
    assert not service.archive(True)


def test_review_mode_blocks_new_browser_and_official_entrypoints(qt, tmp_path, monkeypatch):
    from scripts.review_desktop import create_review_data, review_controller
    root = create_review_data(tmp_path / 'review-data')
    controller = review_controller(root)
    try:
        assert not controller.dualRail.network_enabled
        assert not controller.dualRail.start()
        assert not controller.dualRail.startTra()
        assert not controller.dualRail.previewTra()
        assert controller.dualRail.session is None
        calls = []
        monkeypatch.setattr('thsr_ticket.desktop.dual_rail.QDesktopServices.openUrl', lambda url: calls.append(url))
        controller.dualRail.official()
        assert not calls
    finally:
        controller.timer.stop()
        controller.storage._timer.stop()
        finish_records(controller)


def test_close_waits_for_both_workers_before_emitting_close_ready(controller):
    service = controller.dualRail
    started = threading.Barrier(3)
    closed = []

    def thsr(conf, path, query_only, stop, messages):
        started.wait(3)
        assert stop.wait(3)
        messages.put(('completion', {'code': 'stopped', 'message': '已停止'}))

    def tra(conf, options, directory, stop, emit, **kwargs):
        started.wait(3)
        assert stop.wait(3)
        emit('stopped', '已停止')

    service.worker, service.tra_worker = thsr, tra
    controller.closeReady.connect(lambda: closed.append(True))
    assert service.start()
    try:
        started.wait(3)
        controller.requestClose()
        assert not closed and service.busy
    finally:
        finish(service)
    finish_records(controller)
    controller.poll()
    assert closed


def test_real_qml_dual_panel_persists_settings_and_displays_masked_code(controller, qt):
    service = controller.dualRail
    service.records.pending(uuid4().hex, config(), TraOptions('臺北', '臺中'))
    service.records.booked({'booking_code': '12345678'})
    service.refresh_record()
    engine, warnings = QQmlApplicationEngine(), []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.setInitialProperties({'backend': controller})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / 'desktop/qml/Main.qml')))
    try:
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        controller.navigate(1)
        QTest.qWait(100)
        opener = visual_item(window.contentItem(), 'dualRailButton')
        opener.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Space)
        QTest.qWait(100)
        dialog = window.findChild(QObject, 'dualRailDialog')
        assert dialog.property('visible')
        save = visual_item(dialog.property('contentItem'), 'saveDualButton')
        assert QMetaObject.invokeMethod(save, 'clicked')
        assert service.preferences.exists()
        start_tra = visual_item(dialog.property('contentItem'), 'startTraButton')
        assert start_tra is not None and start_tra.property('enabled')
        assert '09:30' in service.times and '09:31' not in service.times
        reveal = visual_item(dialog.property('contentItem'), 'revealTraCode')
        assert not reveal.property('checked')
        reveal.setProperty('checked', True)
        QMetaObject.invokeMethod(dialog, 'close')
        QTest.qWait(100)
        assert not reveal.property('checked')
        assert not warnings, warnings
    finally:
        delete(engine)
        finish_records(controller)


def test_only_tra_does_not_launch_thsr_or_change_its_existing_guard(controller):
    service = controller.dualRail
    state = controller.path.with_suffix('.state.json')
    state.write_text('{"status":"booked"}', encoding='utf-8')
    before = state.read_bytes()
    entered = threading.Event()

    def tra(conf, options, directory, stop, emit, **kwargs):
        entered.set()
        assert stop.wait(3)
        emit('stopped', '已停止')

    service.tra_worker = tra
    assert service.startTra()
    try:
        assert entered.wait(3)
        assert set(service.session.jobs) == {'tra'}
        assert service.jobs[0]['status'] == 'idle'
        controller.worker.assert_not_called()
        assert state.read_bytes() == before
        service.focusTra()
        assert service._focus.is_set()
    finally:
        finish(service)


def test_only_tra_also_respects_tra_guard(controller):
    service = controller.dualRail
    service.records.path.write_text('{"status":"pending"}', encoding='utf-8')
    assert not service.startTra() and service.session is None


def test_preferences_changed_to_unknown_version_are_preserved_on_save(controller):
    service = controller.dualRail
    assert service.save()
    service.preferences.write_text('{"version":99}', encoding='utf-8')
    assert not service.save()
    assert service.preferences.read_text(encoding='utf-8') == '{"version":99}'


def test_legacy_tra_preferences_gain_retry_defaults(controller):
    service = controller.dualRail
    assert service.save()
    data = json.loads(service.preferences.read_text(encoding='utf-8'))
    data['tra'].pop('network_failure_limit')
    data['tra'].pop('max_network_delay_seconds')
    service.preferences.write_text(json.dumps(data), encoding='utf-8')
    service.read_preferences()
    assert service.form['network_failure_limit'] == '3'
    assert service.save()


def test_known_but_unsaved_code_stays_visible_and_can_be_copied(controller, qt):
    service = controller.dualRail

    def tra(conf, options, directory, stop, emit, **kwargs):
        service.records.pending(uuid4().hex, conf, options)
        emit('pending', '代碼未存檔', 1, {'booking_code': '12345678'})

    service.tra_worker = tra
    assert service.startTra()
    for thread in service.session.threads.values():
        thread.join(3)
    service.poll()
    assert service.record['booking_code'] == '12345678' and service.record['save_failed']
    assert service.records.read()['status'] == 'pending'
    service.copyCode()
    assert qt.clipboard().text() == '12345678'
    assert '12345678' not in service.events
    assert service.confirmResult('12345678', True)
    assert not service.record.get('save_failed')


def test_preview_mode_launches_only_tra_with_explicit_no_booking_flag(controller):
    service, seen, entered = controller.dualRail, [], threading.Event()

    def tra(conf, options, directory, stop, emit, **kwargs):
        seen.append(kwargs['prefill_only'])
        entered.set()
        assert stop.wait(3)
        emit('stopped', '預填檢查已停止')

    service.tra_worker = tra
    assert service.previewTra()
    try:
        assert entered.wait(3) and seen == [True]
        assert set(service.session.jobs) == {'tra'}
        controller.worker.assert_not_called()
    finally:
        finish(service)
