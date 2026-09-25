"""Local Tk configuration editor and cooperative background automation."""
import json
import io
import os
import queue
import threading
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

from thsr_ticket.automation import AutomationConfig, AutomationRunner, TAIPEI, wait_until
from thsr_ticket.run_records import atomic_json
from thsr_ticket.booking_records import record_paths, read_object, booking_codes, show_bookings, archive_booking


STATIONS = ['南港', '台北', '板橋', '桃園', '新竹', '苗栗', '台中', '彰化', '雲林', '嘉義', '台南', '左營']
FIELDS = [
    ('start_at', '開始查票時間（YYYY-MM-DD HH:MM:SS）'),
    ('outbound_date', '搭車日期（YYYY-MM-DD）'),
    ('start_station', '上車站'), ('dest_station', '下車站'),
    ('earliest_departure', '最早發車（HH:MM）'), ('latest_departure', '最晚發車（HH:MM）'),
    ('train_ids', '車次優先順序（逗號分隔，留空不限）'),
    ('adult_tickets', '成人票'), ('child_tickets', '孩童票'), ('disabled_tickets', '愛心票'),
    ('elder_tickets', '敬老票'), ('college_tickets', '大學生票'),
    ('class_type', '車廂'), ('personal_id', '身分證字號'), ('phone_num', '手機（可留空）'),
    ('interval_seconds', '每輪等待秒數'), ('max_attempts', '最多查詢輪數'), ('ocr_model', 'OCR 模型'),
]
INTEGER_FIELDS = ('adult_tickets', 'child_tickets', 'disabled_tickets', 'elder_tickets',
                  'college_tickets', 'max_attempts')


def protected_config_path(path):
    name = Path(path).name.casefold()
    return name.endswith(('.state.json', '.example.json')) or name in ('state.json', 'result.json')


def form_config(values):
    data = dict(values)
    for name in INTEGER_FIELDS:
        try:
            data[name] = int(data[name])
        except ValueError:
            raise ValueError(f'{dict(FIELDS)[name]}必須是整數。') from None
    data['start_station'] = STATIONS.index(data['start_station']) + 1
    data['dest_station'] = STATIONS.index(data['dest_station']) + 1
    data['class_type'] = ['標準', '商務'].index(data['class_type'])
    try:
        data['interval_seconds'] = float(data['interval_seconds'])
        data['train_ids'] = [int(item.strip()) for item in data['train_ids'].replace('，', ',').split(',')
                             if item.strip()]
    except ValueError:
        raise ValueError('間隔必須是數字，車次必須是以逗號分隔的整數。') from None
    return AutomationConfig(**data)


class QueueWriter:
    def __init__(self, messages):
        self.messages = messages

    def write(self, text):
        if text:
            self.messages.put(('text', text))
        return len(text)

    def flush(self):
        pass


class StoppableClient:
    def __init__(self, client, stop):
        self.client, self.stop = client, stop

    def __getattr__(self, name):
        method = getattr(self.client, name)
        if not callable(method):
            return method

        def call(*args, **kwargs):
            if self.stop.is_set():
                raise KeyboardInterrupt()
            return method(*args, **kwargs)
        return call


def run_background(config, path, query_only, stop, messages, client_factory=None, reader_factory=None):
    def sleep(seconds):
        if stop.wait(seconds):
            raise KeyboardInterrupt()

    client = None
    phase = 'preflight'
    outcome = '執行結束'
    with redirect_stdout(QueueWriter(messages)):
        try:
            if stop.is_set():
                raise KeyboardInterrupt()
            state = path.resolve().with_suffix('.state.json')
            if not query_only and state.exists():
                raise RuntimeError('已有訂位送出紀錄，請先查看並確認原訂位。')
            if client_factory is None:
                from thsr_ticket.remote.browser_request import BrowserRequest
                client_factory = BrowserRequest
            if reader_factory is None:
                from thsr_ticket.captcha import CaptchaReader
                reader_factory = CaptchaReader
            phase = 'browser_start'
            client = client_factory(channel='chrome', interactive=False)
            phase = 'ocr_load'
            reader = reader_factory(model=config.ocr_model)
            if not reader.prepare():
                raise RuntimeError('OCR 無法載入，請確認已安裝自動化套件。')
            print(f'等待台灣時間 {config.start_at.isoformat()}；可按停止取消。')
            phase = 'schedule'
            wait_until(config.start_at, sleep=sleep)
            if stop.is_set():
                raise KeyboardInterrupt()
            runner = AutomationRunner(config, StoppableClient(client, stop), reader, state, sleep=sleep)
            phase = 'query'
            success = runner.run(query_only)
            outcome = ('找到符合車次' if query_only else '訂位成功，尚未付款') if success else '已達查詢上限'
        except KeyboardInterrupt:
            outcome = '已停止；若已嘗試送出訂位，請確認官網狀態'
        except Exception as exc:
            # Do not echo arbitrary exceptions or website content into the UI log.
            outcome = '執行失敗，請查看執行紀錄；若已送出訂位，先確認官網狀態'
            print(f'錯誤類型：{type(exc).__name__}')
            hints = {'preflight': '請先確認是否已有訂位紀錄。',
                     'browser_start': 'Chrome 無法啟動，請確認已安裝 Chrome 及自動化套件。',
                     'ocr_load': 'OCR 無法載入，請依 README 安裝 requirements-automation-lock.txt。'}
            if phase in hints:
                outcome = hints[phase]
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    print('瀏覽器清理失敗，請檢查程式開啟的獨立視窗。')
            print(outcome)
            messages.put(('done', outcome))


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title('高鐵訂票小幫手')
    root.geometry('1100x850')
    root.minsize(920, 700)
    root.configure(background='#eef3f7')
    root.option_add('*Font', ('Microsoft JhengHei UI', 10))
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Microsoft JhengHei UI', 10))
    style.configure('TFrame', background='#eef3f7')
    style.configure('TLabel', background='#eef3f7', foreground='#24364b')
    style.configure('Title.TLabel', font=('Microsoft JhengHei UI', 22, 'bold'))
    style.configure('Hint.TLabel', foreground='#61738a')
    style.configure('TButton', padding=(14, 8))
    style.configure('Primary.TButton', background='#087f8c', foreground='white')
    style.map('Primary.TButton', background=[('active', '#096874'), ('disabled', '#ccd9dd')])
    style.configure('TLabelframe', background='white', bordercolor='#d8e2ec')
    style.configure('TLabelframe.Label', background='#eef3f7', foreground='#087f8c',
                    font=('Microsoft JhengHei UI', 11, 'bold'))
    style.configure('Field.TLabel', background='white')
    style.configure('TEntry', padding=6)
    style.configure('TCombobox', padding=6)
    style.configure('TNotebook', background='#eef3f7', borderwidth=0)
    style.configure('TNotebook.Tab', padding=(22, 10))
    style.map('TNotebook.Tab', background=[('selected', 'white')], foreground=[('selected', '#087f8c')])
    header = ttk.Frame(root, padding=(24, 16, 24, 8))
    header.pack(fill='x')
    ttk.Label(header, text='高鐵訂票小幫手', style='Title.TLabel').pack(anchor='w')
    ttk.Label(header, text='設定行程、追蹤查詢、管理訂位，一個視窗完成。', style='Hint.TLabel').pack(anchor='w', pady=(4, 0))
    path = tk.StringVar(value=str(Path('booking.local.json').resolve()))
    has_save_target = [False]
    status = tk.StringVar(value='先載入設定或填寫資料，再驗證／儲存。')
    values = {name: tk.StringVar() for name, _ in FIELDS}
    messages = queue.Queue()
    stop = threading.Event()
    active = [False]
    closing = [False]
    controls = []
    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=True, padx=12, pady=8)
    settings = ttk.Frame(notebook)
    canvas = tk.Canvas(settings, highlightthickness=0, background='#eef3f7')
    scrollbar = ttk.Scrollbar(settings, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    form = ttk.Frame(canvas, padding=12)
    form_window = canvas.create_window((0, 0), window=form, anchor='nw')
    form.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda event: canvas.itemconfigure(form_window, width=event.width))
    output = ttk.Frame(notebook, padding=8)
    notebook.add(settings, text='訂票設定')
    notebook.add(output, text='執行進度')
    records_page = ttk.Frame(notebook, padding=16)
    notebook.add(records_page, text='訂位紀錄')
    form.columnconfigure((0, 1), weight=1, uniform='cards')
    log = ScrolledText(output, wrap='word', state='disabled', background='#132238', foreground='#dce9f4',
                       font=('Microsoft JhengHei UI', 10), relief='flat', padx=16, pady=16)
    log.pack(fill='both', expand=True)
    groups = [
        ('01  行程與車次', [
            'outbound_date', 'start_station', 'dest_station', 'earliest_departure',
            'latest_departure', 'train_ids', 'class_type']),
        ('02  啟動與重試', ['start_at', 'interval_seconds', 'max_attempts', 'ocr_model']),
        ('03  票種與張數', ['adult_tickets', 'child_tickets', 'disabled_tickets', 'elder_tickets', 'college_tickets']),
        ('04  訂票人資料', ['personal_id', 'phone_num']),
    ]
    field_positions = {}
    for index, (title, names) in enumerate(groups):
        card = ttk.LabelFrame(form, text=title, padding=14)
        card.grid(row=index // 2 + 1, column=index % 2, sticky='nsew', padx=8, pady=10)
        card.columnconfigure(0, weight=1)
        for row, name in enumerate(names):
            field_positions[name] = (card, row * 2)
    for name, label in FIELDS:
        parent, row = field_positions[name]
        ttk.Label(parent, text=label, style='Field.TLabel').grid(row=row, column=0, sticky='w', pady=(5, 2))
        options = STATIONS if name in ('start_station', 'dest_station') else (
            ['標準', '商務'] if name == 'class_type' else ['standard', 'beta'] if name == 'ocr_model' else None)
        if options:
            widget = ttk.Combobox(parent, textvariable=values[name], values=options, state='readonly')
        else:
            widget = ttk.Entry(parent, textvariable=values[name], show='*' if name == 'personal_id' else '')
        widget.grid(row=row + 1, column=0, sticky='ew', pady=(0, 4))
        controls.append((widget, 'readonly' if options else 'normal'))

    shortcuts = ttk.Frame(form, padding=8)
    shortcuts.grid(row=0, column=0, columnspan=2, sticky='ew')
    for label, callback in [
        ('立即開始', lambda: values['start_at'].set(datetime.now(TAIPEI).strftime('%Y-%m-%d %H:%M:%S'))),
        ('交換起訖站', lambda: swap_stations()),
    ]:
        button = ttk.Button(shortcuts, text=label, command=callback)
        button.pack(side='left', padx=4)
        controls.append((button, 'normal'))

    def swap_stations():
        start = values['start_station'].get()
        values['start_station'].set(values['dest_station'].get())
        values['dest_station'].set(start)

    def scroll_settings(event):
        if notebook.select() == str(settings) and event.widget.winfo_class() != 'TCombobox':
            canvas.yview_scroll(-int(event.delta / 120), 'units')
    root.bind('<MouseWheel>', scroll_settings)

    records_status = tk.StringVar(value='按「重新整理紀錄」查看目前設定檔對應的訂位。')
    ttk.Label(records_page, text='本機訂位紀錄', font=('Microsoft JhengHei UI', 16, 'bold')).pack(anchor='w')
    ttk.Label(records_page, textvariable=records_status, wraplength=920).pack(anchor='w', pady=(8, 12))
    records_toolbar = ttk.Frame(records_page)
    records_toolbar.pack(fill='x', pady=(0, 12))
    records_text = ScrolledText(records_page, wrap='word', state='disabled', background='white',
                                foreground='#24364b', relief='flat', padx=16, pady=16)
    records_text.pack(fill='both', expand=True)

    def refresh_records():
        if active[0]:
            return
        buffer = io.StringIO()
        try:
            show_bookings(Path(path.get()), output=buffer)
        except OSError:
            messagebox.showerror('無法讀取', '請確認紀錄資料夾可以存取。', parent=root)
            return
        records_text.configure(state='normal')
        records_text.delete('1.0', 'end')
        records_text.insert('end', buffer.getvalue())
        records_text.configure(state='disabled')
        records_status.set(f'目前設定：{Path(path.get()).name}｜本機資料，不代表官網即時付款或取消狀態。')

    def archive_current():
        if active[0]:
            return
        state, _ = record_paths(Path(path.get()))
        try:
            data = read_object(state)
            if data.get('status') != 'booked':
                raise ValueError('紀錄結果尚未確認，不能自動封存；請先確認官網訂位。')
            codes = booking_codes(data)
        except (ValueError, OSError) as exc:
            messagebox.showerror('無法封存', str(exc) if isinstance(exc, ValueError)
                                 else '沒有可讀取的成功訂位紀錄。', parent=root)
            return
        code = simpledialog.askstring('封存目前訂位',
                                      '目前訂位代碼：' + '、'.join(codes) +
                                      '\n封存不會取消官網訂位，也不會立即訂下一筆。\n'
                                      '確認原訂位後，請輸入上述代碼以解除本機防重送阻擋：', parent=root)
        if code is None:
            return
        try:
            archive_booking(Path(path.get()), code, output=io.StringIO())
        except (ValueError, OSError) as exc:
            messagebox.showerror('封存失敗', str(exc) if isinstance(exc, ValueError)
                                 else '檔案操作失敗，請確認紀錄及封存程序狀態。', parent=root)
            return
        refresh_records()
        status.set('已封存原紀錄；請更新行程後再啟動，原官網訂位仍存在。')
        messagebox.showinfo('封存完成', '舊紀錄已保留。請更新行程，再自行啟動下一筆訂位。', parent=root)

    def open_records_folder():
        _, folder = record_paths(Path(path.get()))
        if not folder.is_dir():
            messagebox.showinfo('尚無紀錄', '尚未產生執行紀錄資料夾。', parent=root)
            return
        try:
            os.startfile(str(folder))
        except (OSError, AttributeError):
            messagebox.showinfo('紀錄資料夾', str(folder), parent=root)

    for label, callback in [('重新整理紀錄', refresh_records), ('封存目前訂位', archive_current),
                            ('開啟紀錄資料夾', open_records_folder)]:
        button = ttk.Button(records_toolbar, text=label, command=callback)
        button.pack(side='left', padx=(0, 8))
        controls.append((button, 'normal'))

    def populate(data):
        converted = {}
        for name, _ in FIELDS:
            value = data.get(name, '')
            if name in ('start_station', 'dest_station'):
                value = STATIONS[int(value) - 1] if str(value).isdigit() and 1 <= int(value) <= 12 else ''
            elif name == 'class_type':
                value = {0: '標準', 1: '商務'}.get(value, '')
            elif name == 'train_ids':
                value = ', '.join(str(item) for item in value) if isinstance(value, list) else ''
            elif name == 'start_at' and value:
                dt = datetime.fromisoformat(str(value))
                local = dt.replace(tzinfo=TAIPEI) if dt.tzinfo is None else dt.astimezone(TAIPEI)
                value = local.strftime('%Y-%m-%d %H:%M:%S')
            converted[name] = str(value)
        for name, value in converted.items():
            values[name].set(value)

    defaults = dict(start_at=datetime.now(TAIPEI).strftime('%Y-%m-%d %H:%M:%S'),
                    outbound_date=datetime.now(TAIPEI).date().isoformat(), start_station=2, dest_station=12,
                    earliest_departure='09:30', latest_departure='23:59', train_ids=[], adult_tickets=1,
                    child_tickets=0, disabled_tickets=0, elder_tickets=0, college_tickets=0,
                    class_type=0, personal_id='', phone_num='', interval_seconds=1, max_attempts=60,
                    ocr_model='standard')
    populate(defaults)

    def validate():
        try:
            return form_config({key: value.get().strip() for key, value in values.items()})
        except (ValueError, KeyError) as exc:
            messagebox.showerror('請修正設定', str(exc), parent=root)
            return None

    def load():
        selected = filedialog.askopenfilename(parent=root, filetypes=[('JSON 設定', '*.json')])
        if not selected:
            return
        try:
            data = json.loads(Path(selected).read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict) or set(data) - set(values):
                raise ValueError('不是可用的訂票設定檔，或包含未知欄位。')
            populate({**defaults, **data})
            path.set(selected)
            has_save_target[0] = not protected_config_path(selected)
            status.set('已載入，請核對日期與時間。')
            refresh_records()
        except (ValueError, OSError, TypeError):
            messagebox.showerror('載入失敗', '請確認選擇的是訂票設定 JSON，而非狀態或結果檔。', parent=root)

    def save(as_new=False):
        config = validate()
        if config is None:
            return None
        selected = path.get()
        if as_new or not has_save_target[0]:
            selected = filedialog.asksaveasfilename(
                parent=root, initialfile='booking.local.json' if protected_config_path(path.get())
                else Path(path.get()).name, initialdir=str(Path(path.get()).parent),
                defaultextension='.json', filetypes=[('JSON 設定', '*.json')])
        if not selected:
            return None
        if protected_config_path(selected):
            messagebox.showerror('請換檔名', '請使用個人設定檔名稱，例如 booking.local.json。', parent=root)
            return None
        try:
            atomic_json(Path(selected), json.loads(config.json()))
        except OSError:
            messagebox.showerror('儲存失敗', '請確認資料夾可寫入。', parent=root)
            return None
        path.set(selected)
        has_save_target[0] = True
        status.set('已儲存；設定包含明文個資，請自行保管。')
        return config

    def set_active(running):
        active[0] = running
        for widget, enabled in controls:
            widget.configure(state='disabled' if running else enabled)
        stop_button.configure(state='normal' if running else 'disabled')

    def start(query_only):
        config = save()
        if config is None:
            return
        state = Path(path.get()).resolve().with_suffix('.state.json')
        if not query_only and state.exists():
            refresh_records()
            notebook.select(records_page)
            messagebox.showinfo('已有訂位紀錄', '已切換到訂位紀錄頁。請確認原訂位；'
                                '若要準備另一筆，可按「封存目前訂位」。本次未啟動訂位。', parent=root)
            return
        stop.clear()
        set_active(True)
        notebook.select(output)
        status.set('執行中；自動訂位模式會送出訂位但不付款。' if not query_only else '只查票，不訂位。')
        threading.Thread(target=run_background,
                         args=(config, Path(path.get()), query_only, stop, messages), daemon=False).start()

    buttons = ttk.Frame(root)
    buttons.pack(fill='x', padx=12)

    def validate_only():
        if validate() is not None:
            status.set('設定驗證通過，未連線。')

    actions = [('載入設定', load), ('驗證設定', validate_only), ('儲存設定', save), ('另存設定', lambda: save(True)),
               ('只查票', lambda: start(True)), ('自動訂位（不付款）', lambda: start(False))]
    for label, callback in actions:
        button = ttk.Button(buttons, text=label, command=callback,
                            style='Primary.TButton' if label == '自動訂位（不付款）' else 'TButton')
        button.pack(side='left', padx=3, pady=5)
        controls.append((button, 'normal'))

    def request_stop():
        stop.set()
        status.set('正在停止：等待目前網路操作結束；若已送出訂位，請確認結果。')
        stop_button.configure(state='disabled')

    stop_button = ttk.Button(buttons, text='停止', command=request_stop, state='disabled')
    stop_button.pack(side='left', padx=3)
    ttk.Label(root, textvariable=path, wraplength=800).pack(anchor='w', padx=12)
    ttk.Label(root, textvariable=status, wraplength=800).pack(anchor='w', padx=12, pady=(4, 12))

    def poll():
        try:
            while True:
                kind, text = messages.get_nowait()
                if kind == 'text':
                    log.configure(state='normal')
                    log.insert('end', text)
                    log.see('end')
                    log.configure(state='disabled')
                else:
                    set_active(False)
                    status.set(text)
                    refresh_records()
                    if closing[0]:
                        root.destroy()
                        return
        except queue.Empty:
            pass
        root.after(100, poll)

    def close():
        if active[0]:
            closing[0] = True
            request_stop()
        else:
            root.destroy()

    root.protocol('WM_DELETE_WINDOW', close)
    root.after(100, poll)
    root.mainloop()


if __name__ == '__main__':
    main()
