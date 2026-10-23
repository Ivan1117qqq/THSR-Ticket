"""Journey presets and a local agenda; never submits or changes a booking."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from thsr_ticket.automation import TAIPEI
from thsr_ticket.journey_planning import PlanningIndex, deadline_time, full_date
from thsr_ticket.journey_templates import TemplateStore
from thsr_ticket.run_records import atomic_json


class JourneyPlanner(QObject):
    changed = Signal()
    applyRequested = Signal(object)
    desktopNotification = Signal(str, str, str)

    def __init__(self, directory, preferences, context, parent=None, clock=None):
        super().__init__(parent)
        self.store = TemplateStore(directory)
        self.state_path = Path(directory) / 'journey-reminders.json'
        self.preferences, self.context = preferences, context
        self.clock = clock or (lambda: datetime.now(TAIPEI))
        self._templates, self._message = [], ''
        self._template_message, self._reminder_message = '', ''
        self._overrides, self._sent, self._state_error = {}, {}, False
        self._scope, self._index, self._minute = '', PlanningIndex([]), ''
        today = self.clock().date()
        self._year, self._month, self._selected = today.year, today.month, today.isoformat()
        options = preferences.read()
        self._enabled = options.get('payment_reminders') is True
        self._lead = options.get('payment_reminder_minutes', 180)
        if type(self._lead) is not int or self._lead not in (60, 180, 1440):
            self._lead = 180
        self._agenda = self._index.agenda(self.clock(), {})
        self._read_state()
        self.reloadTemplates()

    def _read_state(self):
        try:
            if not self.state_path.exists():
                return
            if self.state_path.is_symlink() or self.state_path.stat().st_size > 512 * 1024:
                raise ValueError()
            data = json.loads(self.state_path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or set(data) != {'version', 'overrides', 'sent'}
                    or type(data['version']) is not int or data['version'] != 1):
                raise ValueError()
            for name in ('overrides', 'sent'):
                values = data[name]
                if not isinstance(values, dict) or len(values) > 1000 or any(
                        not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key)
                        or not deadline_time(value) for key, value in values.items()):
                    raise ValueError()
            self._overrides, self._sent = data['overrides'], data['sent']
        except (ValueError, TypeError, OSError):
            self._state_error = True
            self._message = '本機提醒紀錄無法讀取；原檔保留，暫停通知以免重複。'
            self._reminder_message = self._message

    def _write_state(self, overrides, sent):
        if self._state_error or self.state_path.is_symlink():
            raise ValueError('提醒紀錄需要處理。')
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.state_path, {'version': 1, 'overrides': overrides, 'sent': sent})
        self._overrides, self._sent = overrides, sent

    def _notice(self, text, scope='template'):
        self._message = text
        if scope == 'template':
            self._template_message = text
        else:
            self._reminder_message = text
        self.changed.emit()

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(str, notify=changed)
    def templateMessage(self):
        return self._template_message

    @Property(str, notify=changed)
    def reminderMessage(self):
        return self._reminder_message

    @Slot()
    def clearReminderMessage(self):
        if not self._state_error:
            self._reminder_message = ''
            self.changed.emit()

    @Property('QVariantList', notify=changed)
    def templates(self):
        return self._templates

    @Slot()
    def reloadTemplates(self):
        try:
            self._templates = self.store.read()
        except (ValueError, TypeError, KeyError, OSError):
            self._templates = []
            self._notice('範本無法讀取；原檔保留，請檢查資料夾或還原備份。')
        self.changed.emit()

    @Slot(str, 'QVariantMap', str, result=bool)
    def saveTemplate(self, name, form, identifier):
        if self.context()['running']:
            return False
        try:
            self.store.save(name, dict(form), identifier)
            self.reloadTemplates()
            self._notice('範本已儲存；不包含日期、證號或手機。')
            return True
        except (ValueError, TypeError, KeyError, OSError) as error:
            self._notice(str(error) if isinstance(error, ValueError) else '無法儲存範本，原檔保留。')
            return False

    @Slot(str, str, result=bool)
    def renameTemplate(self, identifier, name):
        item = next((item for item in self._templates if item['id'] == identifier), None)
        return self.saveTemplate(name, item['values'], identifier) if item else False

    @Slot(str, result=bool)
    def duplicateTemplate(self, identifier):
        item = next((item for item in self._templates if item['id'] == identifier), None)
        if item is None:
            return False
        names = {value['name'].casefold() for value in self._templates}
        for number in range(1, 52):
            name = item['name'][:30] + f' 副本 {number}'
            if name.casefold() not in names:
                return self.saveTemplate(name, item['values'], '')
        return False

    @Slot(str, result=bool)
    def deleteTemplate(self, identifier):
        if self.context()['running']:
            return False
        try:
            self.store.delete(identifier)
            self.reloadTemplates()
            self._notice('範本已移除，目前行程及訂位不受影響。')
            return True
        except (ValueError, TypeError, KeyError, OSError):
            self._notice('無法移除範本，請重新開啟確認。')
            return False

    @Slot(str, result=bool)
    def applyTemplate(self, identifier):
        if self.context()['running']:
            return False
        try:
            item = next(item for item in self.store.read() if item['id'] == identifier)
        except (ValueError, TypeError, KeyError, OSError, StopIteration):
            self._notice('範本已變更或無法讀取，請重新開啟。')
            return False
        self.applyRequested.emit(dict(item['values']))
        self._notice('已套用範本，請確認搭車日期與啟動時間。')
        return True

    def update_records(self, config, index):
        self._scope = hashlib.sha256(str(Path(config).resolve()).encode()).hexdigest()
        self._index = index
        self.tick(force=True)

    def _key(self, identifier):
        return hashlib.sha256((self._scope + identifier).encode()).hexdigest()

    def tick(self, force=False):
        now = self.clock()
        minute = now.strftime('%Y-%m-%d %H:%M')
        if not force and minute == self._minute:
            return
        self._minute = minute
        overrides = {row['id']: self._overrides[self._key(row['id'])] for row in self._index.rows
                     if self._key(row['id']) in self._overrides}
        self._agenda = self._index.agenda(now, overrides)
        self.changed.emit()
        context = self.context()
        if (not self._enabled or self._state_error or not context.get('notifications')
                or not context.get('notification_available') or context.get('loading')):
            return
        due = [row for row in self._agenda['reminders']
               if (deadline_time(row['deadline']) - now).total_seconds() <= self._lead * 60]
        tokens = {hashlib.sha256((self._key(row['id']) + row['deadline'] + str(self._lead)).encode()).hexdigest()
                  for row in due}
        fresh = tokens - self._sent.keys()
        if not fresh:
            return
        sent = dict(self._sent)
        sent.update({token: now.isoformat() for token in fresh})
        sent = dict(sorted(sent.items(), key=lambda item: item[1])[-1000:])
        try:
            self._write_state(dict(self._overrides), sent)
        except (ValueError, OSError):
            self._state_error = True
            self._notice('無法保存提醒紀錄，通知已暫停；請在首頁查看繳費待辦。', 'reminder')
            return
        self.desktopNotification.emit('訂位繳費期限提醒', '有本機紀錄即將到達繳費期限，請回到旅程總覽核對。', 'overview')

    @Property('QVariantMap', notify=changed)
    def agenda(self):
        return {key: value for key, value in self._agenda.items() if key != 'reminders'}

    @Property('QVariantMap', notify=changed)
    def calendar(self):
        return self._index.calendar(self._year, self._month, self._selected)

    @Property(str, notify=changed)
    def selectedDate(self):
        return self._selected

    @Slot(int)
    def moveMonth(self, delta):
        number = (self._year - 1) * 12 + self._month - 1 + delta
        if delta not in (-1, 1) or not 0 <= number < 9999 * 12:
            return
        self._year, self._month = number // 12 + 1, number % 12 + 1
        self._selected = f'{self._year:04d}-{self._month:02d}-01'
        self.changed.emit()

    @Slot(str)
    def selectDate(self, value):
        day = full_date(value)
        if day:
            self._year, self._month, self._selected = day.year, day.month, day.isoformat()
            self.changed.emit()

    @Slot()
    def today(self):
        self.selectDate(self.clock().date().isoformat())

    @Property(bool, notify=changed)
    def remindersEnabled(self):
        return self._enabled

    @Property(int, notify=changed)
    def leadMinutes(self):
        return self._lead

    @Slot(bool, int)
    def setReminders(self, enabled, minutes):
        if minutes not in (60, 180, 1440):
            return
        try:
            self.preferences.payment_reminders(enabled, minutes)
        except OSError:
            self._notice('無法保存繳費提醒偏好。', 'reminder')
            return
        self._enabled, self._lead = bool(enabled), minutes
        self.tick(force=True)

    @Slot(str, str, result=bool)
    def setDeadline(self, identifier, value):
        if self.context()['running']:
            return False
        row = next((row for row in self._index.rows if row['id'] == identifier and row['payable']), None)
        deadline = deadline_time(value)
        if row is None or not deadline or deadline <= self.clock():
            self._notice('請選擇繳費待辦，並輸入未來的完整日期及時間。', 'reminder')
            return False
        day = full_date(row['date'])
        if day and deadline.date() > day:
            self._notice('提醒期限不可晚於搭車日期。', 'reminder')
            return False
        trial = self._index.agenda(self.clock(), {identifier: deadline.isoformat()})
        if not any(item['id'] == identifier for item in trial['reminders']):
            self._notice('提醒期限不可晚於出發時間。', 'reminder')
            return False
        overrides = dict(self._overrides)
        if len(overrides) >= 1000 and self._key(identifier) not in overrides:
            self._notice('本機提醒設定已達上限。', 'reminder')
            return False
        overrides[self._key(identifier)] = deadline.isoformat()
        try:
            self._write_state(overrides, dict(self._sent))
        except (ValueError, OSError):
            self._notice('無法保存本機提醒期限，原訂位不受影響。', 'reminder')
            return False
        self._notice('已保存本機提醒期限；官網繳費期限未變更。', 'reminder')
        self.tick(force=True)
        return True

    @Slot(str)
    def clearDeadline(self, identifier):
        if self.context()['running'] or not any(row['id'] == identifier for row in self._index.rows):
            return
        values = dict(self._overrides)
        values.pop(self._key(identifier), None)
        try:
            self._write_state(values, dict(self._sent))
            self._notice('已移除本機手動期限。', 'reminder')
            self.tick(force=True)
        except (ValueError, OSError):
            self._notice('無法移除本機期限，原檔保留。', 'reminder')
