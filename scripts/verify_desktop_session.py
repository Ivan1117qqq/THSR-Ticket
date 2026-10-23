"""Exercise our own QML window on Windows with isolated fake data, without booking.

This checks Qt focus/events and native APIs, not human visibility or a screen reader.
Use --send-notification to send one harmless local test message to this desktop.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scale', choices=('1', '1.25', '1.5'), default='1')
    parser.add_argument('--output', default='build/desktop-session.json')
    parser.add_argument('--send-notification', action='store_true')
    parser.add_argument('--review', action='store_true',
                        help='Exercise the isolated manual-review controller and records')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise SystemExit('This acceptance script requires Windows.')
    os.environ['QT_QPA_PLATFORM'] = 'windows'
    os.environ['QT_SCALE_FACTOR'] = args.scale
    from PySide6.QtCore import QObject, Qt, QUrl, QMetaObject, QPoint, QPointF
    from PySide6.QtGui import QAccessible, QIcon, QWheelEvent
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from shiboken6 import delete
    from thsr_ticket.desktop.controller import DesktopController
    from thsr_ticket.desktop.notifications import DesktopNotifications
    from thsr_ticket.desktop.single_instance import activate_window
    from thsr_ticket.version import VERSION

    QQuickStyle.setStyle('Basic')
    app = QApplication([])
    base = Path(__file__).resolve().parents[1] / 'thsr_ticket/desktop'
    app.setWindowIcon(QIcon(str(base / 'assets/app.svg')))
    warnings, checks = [], {}
    with tempfile.TemporaryDirectory(prefix='travel-native-acceptance-') as folder:
        if args.review:
            from scripts.review_desktop import create_review_data, review_controller
            review_data = create_review_data(Path(folder) / 'review-data')
            controller = review_controller(review_data)
            if not controller.load_path(review_data / 'booked/booking.local.json'):
                raise RuntimeError('Review records did not load')
        else:
            controller = DesktopController(folder)
        while controller._record_loader.busy:
            controller._record_loader._thread.join(timeout=5)
            if controller._record_loader._thread.is_alive():
                raise RuntimeError('Fake record loader did not stop')
            controller._record_loader.poll()
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
        engine.setInitialProperties({'backend': controller})
        engine.load(QUrl.fromLocalFile(str(base / 'qml/Main.qml')))
        if not engine.rootObjects():
            raise RuntimeError('QML did not load')
        window = engine.rootObjects()[0]
        if args.review:
            checks['review_records'] = controller.recordCount
            if controller.recordCount != 31:
                raise RuntimeError('Review record snapshot incomplete')

        def control(name):
            found = window.findChild(QObject, name)
            if found is not None:
                return found
            items = [window.contentItem()]
            while items:
                item = items.pop()
                if item.objectName() == name:
                    return item
                if isinstance(item, QQuickItem):
                    items.extend(item.childItems())
            raise RuntimeError('Acceptance control missing: ' + name)

        notifications = DesktopNotifications(app.windowIcon(), app)
        try:
            window.setTitle('Travel Desk · isolated acceptance / fake data')
            window.resize(1080, 720)
            QTest.qWait(300)
            window.showMaximized()
            QTest.qWait(150)
            activate_window(window)
            QTest.qWait(150)
            checks['maximized_preserved'] = window.windowState() == Qt.WindowMaximized
            window.showNormal()
            QTest.qWait(150)
            window.showMinimized()
            QTest.qWait(200)
            checks['minimized'] = window.windowState() == Qt.WindowMinimized
            activate_window(window)
            QTest.qWait(300)
            checks['restored'] = window.windowState() != Qt.WindowMinimized and window.isVisible()
            checks['active_window'] = window.isActive()
            # Exercise only this app's controls, never the user's other windows.
            navigation = control('navigation_3')
            navigation.forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Space)
            app.processEvents()
            checks['keyboard_navigation'] = controller.page == 3
            search = control('bookingSearch')
            search.forceActiveFocus()
            for letter in 'DEMO':
                QTest.keyClick(window, getattr(Qt, 'Key_' + letter))
            QTest.keyClick(window, Qt.Key_Return)
            app.processEvents()
            checks['keyboard_search'] = control('bookingsPage').property('appliedSearch') == 'demo'
            QTest.keyClick(window, Qt.Key_Tab)
            checks['tab_to_date'] = control('bookingDateFilter').property('activeFocus')
            accessible = {}
            for name in ('navigation_3', 'bookingSearch', 'bookingDateFilter', 'bookingStatusFilter'):
                interface = QAccessible.queryAccessibleInterface(control(name))
                accessible[name] = bool(interface and interface.text(QAccessible.Name))
            checks['accessible_names'] = all(accessible.values())
            checks['accessible_controls'] = accessible
            controller.navigate(4)
            app.processEvents()
            control('generalSettingsTab').forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Right)
            app.processEvents()
            checks['keyboard_settings_tab'] = control('settingsPage').property('section') == 1
            controller.setField('personal_id', 'A123456789')
            controller.setField('max_attempts', '0')
            controller.save()
            QTest.qWait(150)
            invalid = control('max_attempts')
            checks['invalid_field_focus'] = controller.page == 1 and invalid.property('activeFocus')
            controller.setField('outbound_date', '2024-01-31')
            QMetaObject.invokeMethod(control('calendar_outbound_date'), 'clicked')
            QTest.qWait(180)
            date_picker = control('datePicker_outbound_date')
            control('datePicker_outbound_date_month').forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Down)
            checks['date_month_length'] = date_picker.property('selectedDate') == '2024-02-29'
            QMetaObject.invokeMethod(control('datePicker_outbound_date_cancel'), 'clicked')
            QTest.qWait(180)
            checks['date_cancel_preserves_value'] = controller.form['outbound_date'] == '2024-01-31'
            controller.setField('outbound_date', '2099-01-15')
            QMetaObject.invokeMethod(control('calendar_outbound_date'), 'clicked')
            QTest.qWait(180)
            checks['date_reopened_value'] = date_picker.property('selectedDate') == '2099-01-15'
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            window.grabWindow().save(str(target.with_name(target.stem + '-date-initial.png')))
            scrolled = []
            scroll_values = []
            for axis in ('year', 'month', 'day'):
                wheel = control('datePicker_outbound_date_' + axis)
                position = wheel.mapToScene(QPointF(wheel.width() / 2, wheel.height() / 2))
                before = wheel.property('value')
                global_position = QPointF(window.mapToGlobal(position.toPoint()))
                event = QWheelEvent(position, global_position, QPoint(), QPoint(0, -120),
                                    Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
                app.sendEvent(window, event)
                QTest.qWait(200)
                scrolled.append(wheel.property('value') > before)
                scroll_values.append({'axis': axis, 'before': before, 'after': wheel.property('value')})
            checks['date_wheels_scroll'] = all(scrolled)
            checks['date_wheel_values'] = scroll_values
            wheel = control('datePicker_outbound_date_day')
            position = wheel.mapToScene(QPointF(wheel.width() / 2, wheel.height() / 2)).toPoint()
            before = wheel.property('value')
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, position)
            for distance in (16, 32, 48, 64, 80):
                QTest.mouseMove(window, position - QPoint(0, distance), 25)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, position - QPoint(0, 80))
            QTest.qWait(250)
            checks['date_wheel_drag'] = wheel.property('value') != before
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            date_frame = target.with_name(target.stem + '-date.png')
            checks['date_frame_saved'] = window.grabWindow().save(str(date_frame))
            QMetaObject.invokeMethod(control('datePicker_outbound_date_apply'), 'clicked')
            QTest.qWait(180)
            checks['date_applied'] = controller.form['outbound_date'] == date_picker.property('selectedDate')
            for name in ('calendar_outbound_date', 'time_start_at', 'increase_adult_tickets', 'decrease_adult_tickets'):
                interface = QAccessible.queryAccessibleInterface(control(name))
                accessible[name] = bool(interface and interface.text(QAccessible.Name))
            checks['accessible_names'] = all(accessible.values())
            control('increase_adult_tickets').forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Space)
            checks['keyboard_increase_ticket'] = controller.form['adult_tickets'] == '2'
            control('decrease_adult_tickets').forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Space)
            checks['keyboard_decrease_ticket'] = controller.form['adult_tickets'] == '1'
            controller.setField('max_attempts', '60')
            controller.planner.saveTemplate('native preset', controller.form, '')
            control('journeyTemplatesButton').forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Space)
            QTest.qWait(200)
            checks['preset_dialog_keyboard'] = control('templateDialog').property('visible')
            control('templateList').setProperty('currentIndex', 0)
            original = dict(controller.form)
            controller.setField('dest_station', '台中' if original['dest_station'] != '台中' else '左營')
            control('applyTemplateButton').forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Space)
            QTest.qWait(200)
            checks['preset_applied'] = all(controller.form[key] == original[key] for key in (
                'dest_station', 'personal_id', 'phone_num', 'outbound_date', 'start_at'))
            controller.navigate(0)
            viewport = control('overviewPage').property('contentItem')
            offset = max(0, viewport.property('contentHeight') - viewport.property('height'))
            viewport.setProperty('contentY', offset)
            before = controller.planner.calendar['title']
            control('nextJourneyMonth').forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Space)
            checks['calendar_keyboard'] = controller.planner.calendar['title'] != before
            QTest.qWait(150)
            checks['planner_frame_saved'] = window.grabWindow().save(
                str(target.with_name(target.stem + '-planner.png')))
            # The forwarding path is simulated; this is not a real toast click.
            notifications.opened.connect(lambda target: (controller.openNotification(target), activate_window(window)))
            notifications.opened.emit('settings')
            app.processEvents()
            checks['notification_forwarding_simulated'] = controller.page == 4
            controller.tools.set_notification_support(notifications.available)
            controller.tools.notificationsChanged.connect(notifications.set_enabled)
            controller.tools.desktopNotification.connect(notifications.publish)
            sent = []
            controller.tools.desktopNotification.connect(lambda *item: sent.append(item))
            if args.send_notification and notifications.available:
                controller.tools.setNotifications(True)
                controller.tools.testNotification()
                QTest.qWait(300)
            checks['notification_supported'] = notifications.available
            checks['notification_requested'] = bool(sent)
            frame = window.grabWindow()
            checks['frame_saved'] = not frame.isNull() and frame.save(str(target.with_suffix('.png')))
            report = {'app_version': VERSION, 'platform': app.platformName(), 'scale_factor': args.scale,
                      'review_mode': args.review,
                      'device_pixel_ratio': window.devicePixelRatio(), 'checks': checks, 'qml_warnings': warnings,
                      'scope': 'native Windows Qt events on isolated fake data; no website or real booking',
                      'manual_pending': ['visually confirm and click native notification',
                                         'screen reader reading order and speech',
                                         'human layout review at configured scaling']}
            target.write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report, indent=2))
        finally:
            notifications.set_enabled(False)
            controller._record_loader.cancel()
            if controller._record_loader._thread is not None:
                controller._record_loader._thread.join(timeout=5)
                controller._record_loader.poll()
            controller.timer.stop()
            controller.storage._timer.stop()
            window.setProperty('allowClose', True)
            window.close()
            delete(engine)
    required = ('maximized_preserved', 'minimized', 'restored', 'active_window', 'keyboard_navigation',
                'keyboard_search', 'tab_to_date', 'keyboard_increase_ticket', 'keyboard_decrease_ticket',
                'date_month_length', 'date_cancel_preserves_value', 'date_wheels_scroll', 'date_wheel_drag',
                'date_frame_saved', 'date_applied', 'date_reopened_value',
                'preset_dialog_keyboard', 'preset_applied', 'calendar_keyboard', 'planner_frame_saved',
                'accessible_names', 'keyboard_settings_tab', 'invalid_field_focus', 'frame_saved',
                'notification_forwarding_simulated')
    if warnings or not all(checks[name] for name in required):
        raise SystemExit('Native acceptance checks failed; inspect the JSON report.')


if __name__ == '__main__':
    main()
