"""Actual Qt preset, agenda and deduplicated reminder integration."""
import json
from datetime import datetime
from pathlib import Path

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QObject, QMetaObject, Qt, QUrl  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from shiboken6 import delete  # noqa: E402
from thsr_ticket.automation import TAIPEI  # noqa: E402
from thsr_ticket.desktop.planner import JourneyPlanner  # noqa: E402
from thsr_ticket.journey_planning import PlanningIndex  # noqa: E402
from thsr_ticket.unittest.test_desktop import qt as qt_fixture, controller as controller_fixture  # noqa: E402
from thsr_ticket.unittest.test_desktop import finish_records  # noqa: E402
from thsr_ticket.unittest.test_journey_planning import entry  # noqa: E402

qt = qt_fixture
controller = controller_fixture


def prepare(controller, records=None):
    service = controller.planner
    service.clock = lambda: datetime(2099, 1, 14, 10, tzinfo=TAIPEI)
    service.update_records(controller.path, PlanningIndex(records or [entry()]))
    return service


def visual_item(root, name):
    if root.objectName() == name:
        return root
    for child in root.childItems():
        result = visual_item(child, name)
        if result is not None:
            return result
    return None


def test_template_applies_atomically_without_relocating_config_or_touching_guard(controller):
    service = prepare(controller)
    original = dict(controller.form)
    assert service.saveTemplate('常用行程', original, '')
    identifier = service.templates[0]['id']
    controller.setField('dest_station', '台中')
    path = controller.path
    state = path.with_suffix('.state.json')
    state.write_text('{"status":"submission_pending"}', encoding='utf-8')
    before = state.read_bytes()
    assert service.applyTemplate(identifier)
    assert controller.form['dest_station'] == original['dest_station']
    for name in ('personal_id', 'phone_num', 'outbound_date', 'start_at'):
        assert controller.form[name] == original[name]
    assert controller.path == path and state.read_bytes() == before
    controller._running = True
    assert not service.saveTemplate('blocked', original, '')
    assert not service.applyTemplate(identifier)
    controller._running = False


def test_template_rename_duplicate_remove_do_not_mutate_form(controller):
    service = prepare(controller)
    original = dict(controller.form)
    assert service.saveTemplate('original', original, '')
    identifier = service.templates[0]['id']
    assert service.renameTemplate(identifier, 'renamed')
    assert service.duplicateTemplate(identifier)
    assert len(service.templates) == 2 and len({item['id'] for item in service.templates}) == 2
    assert service.deleteTemplate(identifier)
    assert len(service.templates) == 1 and dict(controller.form) == original


def test_reminder_requires_both_preferences_and_support_and_survives_restart(controller):
    service = prepare(controller)
    emitted = []
    service.desktopNotification.connect(lambda *args: emitted.append(args))
    service.setReminders(True, 180)
    assert not emitted
    controller.tools.set_notification_support(True)
    controller.tools.setNotifications(True)
    assert len(emitted) == 1 and emitted[0][2] == 'overview'
    assert 'TEST0001' not in str(emitted)
    service.tick(force=True)
    assert len(emitted) == 1
    restarted = JourneyPlanner(controller.data_dir, controller.preferences, controller.planning_context,
                               clock=service.clock)
    restarted.desktopNotification.connect(lambda *args: emitted.append(args))
    restarted.update_records(controller.path, service._index)
    assert len(emitted) == 1
    controller.openNotification('overview')
    assert controller.page == 0


def test_ambiguous_deadline_needs_manual_confirmation_and_stays_config_scoped(controller):
    service = prepare(controller, [entry(ticket={**entry()['ticket'], 'payment_deadline': '01/14'})])
    row = service.agenda['items'][0]
    assert not row['deadline']
    assert not service.setDeadline(row['id'], '01/14 12:00')
    assert not service.setDeadline(row['id'], '2099-01-15 09:32')
    assert service.setDeadline(row['id'], '2099-01-14 12:00')
    assert service.agenda['items'][0]['local_deadline']
    service.update_records(controller.path.parent / 'other.json', service._index)
    assert not service.agenda['items'][0]['deadline']
    service.update_records(controller.path, service._index)
    service.clearDeadline(row['id'])
    assert not service.agenda['items'][0]['deadline']


@pytest.mark.parametrize('failure', ['broken', 'write'])
def test_failed_reminder_storage_does_not_emit_or_overwrite(controller, monkeypatch, failure):
    service = prepare(controller)
    if failure == 'broken':
        service.state_path.write_text('broken', encoding='utf-8')
        service._read_state()
    else:
        monkeypatch.setattr('thsr_ticket.desktop.planner.atomic_json', lambda *args: (_ for _ in ()).throw(OSError()))
    emitted = []
    service.desktopNotification.connect(lambda *args: emitted.append(args))
    controller.tools.set_notification_support(True)
    controller.tools.setNotifications(True)
    service.setReminders(True, 180)
    service.tick(force=True)
    assert not emitted
    if failure == 'broken':
        assert service.state_path.read_text(encoding='utf-8') == 'broken'


def test_paid_cancelled_expired_and_loading_do_not_generate_reminders(controller):
    service = prepare(controller, [entry(official_status='paid'), entry(code='C', resolution='cancelled'),
                                   entry(code='E', ticket={**entry()['ticket'],
                                                           'payment_deadline': '2099-01-14 09:00'})])
    emitted = []
    service.desktopNotification.connect(lambda *args: emitted.append(args))
    controller.tools.set_notification_support(True)
    controller.tools.setNotifications(True)
    service.setReminders(True, 180)
    assert not emitted
    controller._record_loader.busy = True
    prepare(controller)
    assert not emitted
    controller._record_loader.busy = False
    service.tick(force=True)
    assert len(emitted) == 1


def test_preferences_remember_and_task_notifications_keep_payment_options(controller):
    service = prepare(controller)
    service.setReminders(True, 1440)
    controller.preferences.remember(controller.path)
    controller.tools.setNotifications(False)
    data = controller.preferences.read()
    assert data['payment_reminders'] is True and data['payment_reminder_minutes'] == 1440
    assert not data['desktop_notifications']
    assert 'TEST0001' not in json.dumps(data)


def test_record_loader_prepares_planning_in_background(controller):
    controller.refresh()
    finish_records(controller)
    assert controller.planner._index is controller._record_loader.planning_index


def test_qml_templates_calendar_and_manual_deadline_controls(qt, controller):
    service = prepare(controller)
    service.selectDate('2099-01-15')
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(str(error) for error in errors))
    engine.setInitialProperties({'backend': controller})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / 'desktop/qml/Main.qml')))
    assert engine.rootObjects(), warnings
    try:
        window = engine.rootObjects()[0]
        window.resize(1080, 720)
        QMetaObject.invokeMethod(window.findChild(QObject, 'overviewTemplatesButton'), 'clicked')
        qt.processEvents()
        window.findChild(QObject, 'templateName').setProperty('text', '介面範本')
        QMetaObject.invokeMethod(window.findChild(QObject, 'saveTemplateButton'), 'clicked')
        qt.processEvents()
        assert len(service.templates) == 1
        controller.setField('dest_station', '台中')
        QMetaObject.invokeMethod(window.findChild(QObject, 'applyTemplateButton'), 'clicked')
        QTest.qWait(220)
        assert controller.form['dest_station'] != '台中'
        controller.navigate(0)
        QMetaObject.invokeMethod(window.findChild(QObject, 'nextJourneyMonth'), 'clicked')
        assert service.calendar['title'] == '2099 年 2 月'
        service.selectDate('2099-01-15')
        assert service.calendar['total'] == 1
        qt.processEvents()
        row = service.agenda['items'][0]
        route = []
        window.findChild(QObject, 'overviewPage').deadlineRequested.connect(lambda value: route.append(value))
        content = window.property('contentItem')
        assert isinstance(content, QQuickItem)
        edit = visual_item(content, 'editDeadline_' + row['id'])
        assert edit is not None, warnings
        assert edit.property('enabled')
        assert QMetaObject.invokeMethod(edit, 'clicked')
        qt.processEvents()
        dialog = window.findChild(QObject, 'deadlineDialog')
        assert dialog.property('visible'), (warnings, route, dialog.metaObject().className())
        assert route
        window.findChild(QObject, 'localDeadlineInput').setProperty('text', '2099-01-14 13:00')
        save = window.findChild(QObject, 'saveDeadlineButton')
        assert not save.property('enabled')
        window.findChild(QObject, 'deadlineConsent').setProperty('checked', True)
        qt.processEvents()
        assert save.property('enabled')
        QMetaObject.invokeMethod(save, 'clicked', Qt.DirectConnection)
        qt.processEvents()
        assert service.agenda['items'][0]['local_deadline']
        assert not warnings
    finally:
        delete(engine)
