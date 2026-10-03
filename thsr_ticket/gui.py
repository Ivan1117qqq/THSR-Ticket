"""Local Tk configuration editor and cooperative background automation."""
import json
import io
import os
import queue
import threading
import webbrowser
import calendar
from datetime import datetime
from pathlib import Path

from thsr_ticket.automation import AutomationRunner, TAIPEI
from thsr_ticket.config_store import read_config_data, write_config_data, is_protected
from thsr_ticket.booking_records import record_paths, record_entries, archive_booking, resolve_pending


from thsr_ticket.application import STATIONS, FIELDS, INTEGER_FIELDS, protected_config_path, form_config
from thsr_ticket.application import StoppableClient  # noqa: F401 - legacy public import
from thsr_ticket.application import run_background as run_booking


def run_background(config, path, query_only, stop, messages, client_factory=None, reader_factory=None):
    return run_booking(config, path, query_only, stop, messages, client_factory, reader_factory,
                       runner_factory=AutomationRunner)


def masked_entry(parent, variable):
    """Reusable masked field with a keyboard-accessible, font-independent eye icon."""
    import tkinter as tk
    from tkinter import ttk

    frame = ttk.Frame(parent, style='Card.TFrame')
    entry = ttk.Entry(frame, textvariable=variable, show='*', width=12)
    entry.pack(side='left', fill='x', expand=True)
    icons = []
    for crossed in (False, True):
        icon = tk.PhotoImage(master=parent, width=24, height=24)
        for y in range(24):
            for x in range(24):
                lid = abs(abs(y - 11.5) - 6 * (1 - ((x - 11.5) / 10) ** 2)) < 0.9 and 2 <= x <= 21
                pupil = (x - 11.5) ** 2 + (y - 11.5) ** 2 < 8
                slash = crossed and abs(y - x) < 1.3 and 3 <= x <= 20
                if lid or pupil or slash:
                    icon.put('#526878', (x, y))
        icons.append(icon)

    def hide():
        entry.configure(show='*')
        button.configure(image=icons[0], text='顯示')

    def toggle():
        if entry.cget('show'):
            entry.configure(show='')
            button.configure(image=icons[1], text='隱藏')
        else:
            hide()

    button = ttk.Button(frame, image=icons[0], text='顯示', compound='left',
                        command=toggle, style='Reveal.TButton', takefocus=True)
    button.pack(side='right', padx=(6, 0))
    button.eye_images = icons
    return frame, entry, button, hide


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title('高鐵訂票小幫手')
    root.geometry('1120x800')
    root.minsize(980, 700)
    root.configure(background='#eef3f7')
    root.option_add('*Font', ('Microsoft JhengHei UI', 10))
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Microsoft JhengHei UI', 10))
    style.configure('TFrame', background='#eef3f7')
    style.configure('TLabel', background='#eef3f7', foreground='#24364b')
    style.configure('Title.TLabel', font=('Microsoft JhengHei UI', 22, 'bold'))
    style.configure('Hint.TLabel', foreground='#61738a')
    style.configure('TButton', padding=(14, 9), background='white', foreground='#33495c',
                    borderwidth=1, bordercolor='#dce4ea', lightcolor='white', darkcolor='white')
    style.map('TButton', background=[('active', '#e4eef2'), ('pressed', '#d5e5ea')],
              foreground=[('disabled', '#94a3af')])
    style.configure('Card.TFrame', background='white')
    style.configure('Reveal.TButton', padding=(5, 4), borderwidth=0)
    style.configure('Header.TFrame', background='#142d3b')
    style.configure('Header.TLabel', background='#142d3b', foreground='white',
                    font=('Microsoft JhengHei UI', 24, 'bold'))
    style.configure('Subheader.TLabel', background='#142d3b', foreground='#a9c5ce')
    style.configure('Brand.TLabel', background='#142d3b', foreground='#6fd3c1',
                    font=('Segoe UI', 10, 'bold'))
    style.configure('Primary.TButton', background='#087f8c', foreground='white')
    style.map('Primary.TButton', background=[('active', '#096874'), ('disabled', '#ccd9dd')])
    style.configure('TLabelframe', background='white', bordercolor='#d8e2ec', relief='flat', borderwidth=1)
    style.configure('TLabelframe.Label', background='#eef3f7', foreground='#087f8c',
                    font=('Microsoft JhengHei UI', 11, 'bold'))
    style.configure('Field.TLabel', background='white')
    style.configure('TEntry', padding=8, bordercolor='#dce4ea', lightcolor='white', darkcolor='white')
    style.map('TEntry', bordercolor=[('focus', '#087f8c')])
    style.configure('TCombobox', padding=8, bordercolor='#dce4ea', arrowsize=14)
    style.configure('TSpinbox', padding=8, bordercolor='#dce4ea', arrowsize=12)
    style.configure('TCheckbutton', background='#eef3f7', foreground='#526878', padding=6)
    style.configure('Horizontal.TProgressbar', background='#087f8c', troughcolor='#dce8ed',
                    borderwidth=0, thickness=6)
    style.configure('TNotebook', background='#eef3f7', borderwidth=0)
    style.configure('TNotebook.Tab', padding=(22, 10))
    style.map('TNotebook.Tab', background=[('selected', 'white')], foreground=[('selected', '#087f8c')])
    header = ttk.Frame(root, padding=(30, 20, 30, 20), style='Header.TFrame')
    header.pack(fill='x')
    ttk.Label(header, text='THSR  /  TRAVEL DESK', style='Brand.TLabel').pack(anchor='w', pady=(0, 5))
    ttk.Label(header, text='高鐵訂票小幫手', style='Header.TLabel').pack(anchor='w')
    ttk.Label(header, text='安排下一段旅程', style='Subheader.TLabel').pack(anchor='w', pady=(5, 0))
    path = tk.StringVar(value=str(Path('booking.local.json').resolve()))
    has_save_target = [False]
    status = tk.StringVar(value='載入設定或填寫行程後，即可開始。')
    values = {name: tk.StringVar() for name, _ in FIELDS}
    messages = queue.Queue()
    stop = threading.Event()
    active = [False]
    closing = [False]
    controls = []
    conceal_fields = []
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
    output = ttk.Frame(notebook, padding=20)
    notebook.add(settings, text='訂票設定')
    notebook.add(output, text='執行進度')
    records_page = ttk.Frame(notebook, padding=16)
    notebook.add(records_page, text='訂位紀錄')
    form.columnconfigure((0, 1), weight=1, uniform='cards')
    progress_title = tk.StringVar(value='準備開始')
    progress_count = tk.StringVar(value='尚未查詢')
    ttk.Label(output, textvariable=progress_title, font=('Microsoft JhengHei UI', 22, 'bold')).pack(anchor='w')
    ttk.Label(output, textvariable=progress_count, style='Hint.TLabel').pack(anchor='w', pady=8)
    progress = ttk.Progressbar(output, mode='indeterminate')
    progress.pack(fill='x', pady=(0, 16))
    detail_toggle = tk.BooleanVar(value=False)
    log = ScrolledText(output, wrap='word', state='disabled', background='#132238', foreground='#dce9f4',
                       font=('Microsoft JhengHei UI', 10), relief='flat', padx=16, pady=16)
    ttk.Checkbutton(output, text='顯示詳細紀錄', variable=detail_toggle,
                    command=lambda: log.pack(fill='both', expand=True, pady=8)
                    if detail_toggle.get() else log.pack_forget()).pack(anchor='w')
    groups = [
        ('01  行程與車次', [
            'outbound_date', 'class_type', 'start_station', 'dest_station',
            'earliest_departure', 'latest_departure', 'train_ids']),
        ('02  啟動與重試', ['start_at', 'interval_seconds', 'max_attempts', 'ocr_model']),
        ('03  票種與張數', ['adult_tickets', 'child_tickets', 'disabled_tickets', 'elder_tickets', 'college_tickets']),
        ('04  訂票人資料', ['personal_id', 'phone_num']),
    ]
    field_positions = {}
    for index, (title, names) in enumerate(groups):
        card = ttk.LabelFrame(form, text=title, padding=20)
        card.grid(row=index // 2 + 1, column=index % 2, sticky='nsew', padx=8, pady=10)
        card.columnconfigure((0, 1), weight=1, uniform='fields')
        for row, name in enumerate(names):
            field_positions[name] = (card, (row // 2) * 2, row % 2)

    def pick_date(name):
        dialog = tk.Toplevel(root)
        dialog.title('選擇搭車日期' if name == 'outbound_date' else '選擇啟動日期')
        dialog.transient(root)
        dialog.grab_set()
        try:
            selected = datetime.fromisoformat(values[name].get().split('T')[0].split(' ')[0])
        except ValueError:
            selected = datetime.now(TAIPEI)
        month = [selected.year, selected.month]
        title = tk.StringVar()
        bar = ttk.Frame(dialog, padding=12)
        bar.pack(fill='x')
        days = ttk.Frame(dialog, padding=12)
        days.pack()

        def choose(day):
            date = f'{month[0]:04d}-{month[1]:02d}-{day:02d}'
            if name == 'start_at':
                try:
                    time = datetime.fromisoformat(values[name].get()).strftime('%H:%M:%S')
                except ValueError:
                    time = '00:00:00'
                date += ' ' + time
            values[name].set(date)
            dialog.destroy()

        def render(delta=0):
            index = month[0] * 12 + month[1] - 1 + delta
            month[:] = [index // 12, index % 12 + 1]
            title.set(f'{month[0]} 年 {month[1]} 月')
            for child in days.winfo_children():
                child.destroy()
            for column, label in enumerate('一二三四五六日'):
                ttk.Label(days, text=label, anchor='center').grid(row=0, column=column, sticky='ew')
            for row, week in enumerate(calendar.monthcalendar(*month), 1):
                for column, day in enumerate(week):
                    if day:
                        ttk.Button(days, text=str(day), width=3, command=lambda d=day: choose(d)).grid(
                            row=row, column=column, padx=2, pady=2)
        ttk.Button(bar, text='‹', width=3, command=lambda: render(-1)).pack(side='left')
        ttk.Label(bar, textvariable=title, anchor='center').pack(side='left', expand=True, fill='x')
        ttk.Button(bar, text='›', width=3, command=lambda: render(1)).pack(side='right')
        render()

    for name, label in FIELDS:
        parent, row, column = field_positions[name]
        short_labels = {'start_at': '啟動時間', 'outbound_date': '搭車日期', 'earliest_departure': '最早出發',
                        'latest_departure': '最晚出發', 'train_ids': '偏好車次（可留空）', 'interval_seconds': '查詢間隔（秒）',
                        'phone_num': '手機（選填）'}
        ttk.Label(parent, text=short_labels.get(name, label), style='Field.TLabel').grid(
            row=row, column=column, sticky='w', padx=6, pady=(5, 2))
        options = STATIONS if name in ('start_station', 'dest_station') else (
            ['標準', '商務'] if name == 'class_type' else ['standard', 'beta'] if name == 'ocr_model' else None)
        if options:
            widget = ttk.Combobox(parent, textvariable=values[name], values=options, state='readonly')
        elif name in INTEGER_FIELDS:
            widget = ttk.Spinbox(parent, textvariable=values[name], from_=1 if name == 'max_attempts' else 0,
                                 to=10000 if name == 'max_attempts' else 10, width=8)
        elif name == 'personal_id':
            widget, secret_entry, reveal_button, hide = masked_entry(parent, values[name])
            controls.extend([(secret_entry, 'normal'), (reveal_button, 'normal')])
            conceal_fields.append(hide)
        else:
            widget = ttk.Entry(parent, textvariable=values[name])
        widget.grid(row=row + 1, column=column, sticky='ew', padx=6, pady=(0, 8))
        if name != 'personal_id':
            controls.append((widget, 'readonly' if options else 'normal'))
        if name in ('start_at', 'outbound_date'):
            date_button = ttk.Button(parent, text='日曆', width=4, command=lambda key=name: pick_date(key))
            date_button.grid(row=row, column=column, sticky='e', padx=6)
            controls.append((date_button, 'normal'))

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

    records_status = tk.StringVar(value='選取一筆紀錄查看詳情')
    history_visible = tk.BooleanVar(value=False)
    records_toolbar = ttk.Frame(records_page)
    records_toolbar.pack(fill='x', pady=(0, 12))
    ttk.Label(records_toolbar, text='我的訂位', font=('Microsoft JhengHei UI', 18, 'bold')).pack(side='left')
    ttk.Checkbutton(records_toolbar, text='包含歷史紀錄', variable=history_visible,
                    command=lambda: refresh_records()).pack(side='right')
    ttk.Label(records_page, textvariable=records_status, style='Hint.TLabel').pack(anchor='w', pady=(0, 10))
    columns = ('status', 'date', 'route', 'time', 'train', 'code')
    table_frame = ttk.Frame(records_page)
    table_frame.pack(fill='both', expand=True)
    record_table = ttk.Treeview(table_frame, columns=columns, show='headings', height=7, selectmode='browse')
    record_scroll = ttk.Scrollbar(table_frame, orient='vertical', command=record_table.yview)
    record_table.configure(yscrollcommand=record_scroll.set)
    record_scroll.pack(side='right', fill='y')
    for name, label, width in zip(columns, ('狀態', '日期', '行程', '出發', '車次', '訂位代碼'),
                                  (120, 110, 230, 90, 70, 120)):
        record_table.heading(name, text=label)
        record_table.column(name, width=width, minwidth=60, stretch=name == 'route')
    style.configure('Treeview', rowheight=38, borderwidth=0, background='white', fieldbackground='white')
    style.configure('Treeview.Heading', padding=(8, 10), font=('Microsoft JhengHei UI', 10, 'bold'))
    record_table.tag_configure('pending', foreground='#a15c00', background='#fff5df')
    record_table.pack(side='left', fill='both', expand=True)
    details = ttk.LabelFrame(records_page, text='訂位明細', padding=16)
    details.pack(fill='x', pady=12)
    detail_values = {}
    for index, (key, label) in enumerate([('seat', '座位'), ('price', '金額'),
                                         ('payment_deadline', '繳費期限'), ('ticket_num_info', '票種 / 張數')]):
        cell = ttk.Frame(details)
        cell.grid(row=0, column=index, sticky='ew', padx=10)
        details.columnconfigure(index, weight=1)
        ttk.Label(cell, text=label, style='Hint.TLabel').pack(anchor='w')
        detail_values[key] = tk.StringVar(value='—')
        ttk.Label(cell, textvariable=detail_values[key], font=('Microsoft JhengHei UI', 13, 'bold')).pack(anchor='w')
    record_actions = ttk.Frame(records_page)
    record_actions.pack(fill='x')
    rows = {}

    def selected_record():
        selection = record_table.selection()
        return rows.get(selection[0]) if selection else None

    def update_selection(event=None):
        entry = selected_record()
        for key, variable in detail_values.items():
            variable.set(entry['ticket'].get(key, '—') or '—' if entry else '—')
        archive_button.configure(state='normal' if entry and entry['current'] and
                                 entry['status'] == 'booked' and not active[0] else 'disabled')
        resolve_button.configure(state='normal' if entry and entry['current'] and
                                 entry['status'] == 'submission_pending' and not active[0] else 'disabled')
        if entry and entry['status'] == 'submission_pending':
            records_status.set('送出後未收到確定結果。先核對官網，再按「處理待確認」。')
        elif entry and entry['status'] == 'unreadable':
            records_status.set('紀錄無法讀取。請保留檔案並核對官網，尚未解除阻擋。')
        else:
            records_status.set('移至歷史只處理本機紀錄，不會取消官網訂位。')
    record_table.bind('<<TreeviewSelect>>', update_selection)

    def refresh_records():
        if active[0]:
            return
        try:
            entries = record_entries(Path(path.get()))
        except OSError:
            messagebox.showerror('無法讀取', '請確認紀錄資料夾可以存取。', parent=root)
            return
        record_table.delete(*record_table.get_children())
        rows.clear()
        names = {'booked': '已訂位', 'submission_pending': '結果待確認', 'history': '歷史紀錄',
                 'resolved': '已核對', 'unreadable': '需要檢查'}
        for entry in entries:
            if not entry['current'] and not history_visible.get():
                continue
            ticket = entry['ticket']
            route = ' → '.join(filter(None, (ticket.get('start_station'), ticket.get('dest_station')))) or '—'
            display_values = (names.get(entry['status'], '需要檢查'), ticket.get('date', '—'), route,
                              ticket.get('depart_time', '—'), ticket.get('train_id', '—'),
                              entry['code'] or '尚未取得')
            item = record_table.insert('', 'end', values=display_values,
                                       tags=('pending',) if entry['status'] == 'submission_pending' else ())
            rows[item] = entry
        if rows:
            record_table.selection_set(next(iter(rows)))
        else:
            records_status.set('目前沒有待處理的本機紀錄，可準備下一筆。歷史紀錄可由右上角展開。')
        update_selection()
        if not rows:
            records_status.set('目前沒有待處理的本機紀錄。勾選「包含歷史紀錄」查看已移出的項目。')

    def archive_current():
        entry = selected_record()
        if active[0] or not entry or not entry['current'] or entry['status'] != 'booked':
            return
        if not messagebox.askyesno('移至歷史', f"將訂位 {entry['code']} 移至歷史並準備下一筆？\n"
                                   '官網訂位保留，這不會取消車票。', parent=root):
            return
        try:
            archive_booking(Path(path.get()), entry['code'], output=io.StringIO())
        except (ValueError, OSError, RuntimeError) as exc:
            messagebox.showerror('尚未移出', str(exc), parent=root)
            return
        refresh_records()
        status.set('已移至歷史，可修改行程準備下一筆。')

    def resolve_current():
        entry = selected_record()
        if active[0] or not entry or entry['status'] != 'submission_pending':
            return
        dialog = tk.Toplevel(root)
        dialog.title('核對訂位結果')
        dialog.transient(root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=24)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='請先核對官網的訂位結果', font=('Microsoft JhengHei UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(body, text='不確定時請返回，程式不會替你判定訂位失敗。').pack(anchor='w', pady=8)
        ttk.Button(body, text='開啟高鐵訂票網站', command=open_official).pack(anchor='w', pady=8)
        outcome = tk.StringVar(value='')
        for value, label in [('booked', '已訂位，保留原票並準備下一筆'),
                             ('not_booked', '已查詢，確認沒有成立訂位'), ('cancelled', '已自行在官網取消')]:
            ttk.Radiobutton(body, text=label, variable=outcome, value=value).pack(anchor='w', pady=5)
        ttk.Label(body, text='訂位代碼（選擇已訂位時必填）').pack(anchor='w', pady=(12, 4))
        code = tk.StringVar()
        ttk.Entry(body, textvariable=code).pack(fill='x')
        acknowledged = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text='我已在官網核對，確認上述結果', variable=acknowledged).pack(anchor='w', pady=14)

        def confirm():
            try:
                resolve_pending(Path(path.get()), outcome.get(), entry['fingerprint'],
                                confirmed=acknowledged.get(), code=code.get())
            except (ValueError, OSError, RuntimeError) as exc:
                messagebox.showerror('尚未完成', str(exc), parent=dialog)
                return
            dialog.destroy()
            refresh_records()
            status.set('已保留原始紀錄與核對結果，可準備下一筆。')
        footer = ttk.Frame(body)
        footer.pack(fill='x')
        ttk.Button(footer, text='返回', command=dialog.destroy).pack(side='left')
        ttk.Button(footer, text='確認並移至歷史', command=confirm, style='Primary.TButton').pack(side='right')

    def open_official():
        webbrowser.open('https://irs.thsrc.com.tw/IMINT/')

    def open_records_folder():
        _, folder = record_paths(Path(path.get()))
        if not folder.is_dir():
            messagebox.showinfo('尚無紀錄', '尚未產生執行紀錄資料夾。', parent=root)
            return
        try:
            os.startfile(str(folder))
        except (OSError, AttributeError):
            messagebox.showinfo('紀錄資料夾', str(folder), parent=root)

    archive_button = ttk.Button(record_actions, text='移至歷史', command=archive_current, state='disabled')
    archive_button.pack(side='left', padx=(0, 8))
    resolve_button = ttk.Button(record_actions, text='處理待確認', command=resolve_current, state='disabled')
    resolve_button.pack(side='left', padx=(0, 8))
    controls.extend([(archive_button, 'disabled'), (resolve_button, 'disabled')])
    for label, callback in [('重新整理紀錄', refresh_records), ('開啟高鐵官網', open_official),
                            ('開啟紀錄資料夾', open_records_folder)]:
        button = ttk.Button(record_actions, text=label, command=callback)
        button.pack(side='right', padx=4)
        controls.append((button, 'normal'))

    def populate(data):
        for hide in conceal_fields:
            hide()
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
            data = read_config_data(selected)
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
            previous = json.loads(Path(path.get()).read_text(encoding='utf-8-sig')) if Path(path.get()).exists() else {}
            write_config_data(Path(selected), json.loads(config.json()), protect=is_protected(previous))
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
        if running:
            stop_button.pack(side='right', padx=3)
            progress.start(15)
        else:
            stop_button.pack_forget()
            progress.stop()

    def start(query_only):
        config = save()
        if config is None:
            return
        state = Path(path.get()).resolve().with_suffix('.state.json')
        if not query_only and state.exists():
            refresh_records()
            notebook.select(records_page)
            messagebox.showinfo('已有訂位紀錄', '已切換到訂位紀錄頁。請確認原訂位；'
                                '可選擇「移至歷史」或「處理待確認」。本次未啟動訂位。', parent=root)
            return
        stop.clear()
        progress_count.set('尚未查詢')
        progress_title.set('準備開始')
        set_active(True)
        notebook.select(output)
        status.set('執行中；自動訂位模式會送出訂位但不付款。' if not query_only else '只查票，不訂位。')
        threading.Thread(target=run_background,
                         args=(config, Path(path.get()), query_only, stop, messages), daemon=False).start()

    buttons = ttk.Frame(root)
    buttons.pack(fill='x', padx=12)
    filebar = ttk.Frame(root, padding=(24, 0, 24, 8))
    filebar.pack(fill='x', before=notebook)
    filename = tk.StringVar(value='尚未載入設定')
    path.trace_add('write', lambda *args: filename.set(Path(path.get()).name))
    ttk.Label(filebar, textvariable=filename, style='Hint.TLabel').pack(side='right')

    def validate_only():
        if validate() is not None:
            status.set('設定驗證通過，未連線。')

    actions = [('載入設定', load), ('儲存設定', save), ('另存設定', lambda: save(True)),
               ('只查票', lambda: start(True)), ('自動訂位（不付款）', lambda: start(False))]
    for label, callback in actions:
        parent = buttons if label in ('只查票', '自動訂位（不付款）') else filebar
        button = ttk.Button(parent, text=label, command=callback,
                            style='Primary.TButton' if label == '自動訂位（不付款）' else 'TButton')
        button.pack(side='left', padx=3, pady=5)
        controls.append((button, 'normal'))
    more = ttk.Menubutton(filebar, text='更多')
    menu = tk.Menu(more, tearoff=False)
    menu.add_command(label='檢查設定', command=validate_only)
    menu.add_command(label='開啟紀錄資料夾', command=open_records_folder)
    more.configure(menu=menu)
    more.pack(side='left', padx=6)
    controls.append((more, 'normal'))

    def request_stop():
        stop.set()
        status.set('正在停止：等待目前網路操作結束；若已送出訂位，請確認結果。')
        stop_button.configure(state='disabled')

    stop_button = ttk.Button(buttons, text='停止', command=request_stop, state='disabled')
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
                elif kind == 'phase':
                    progress_title.set(text)
                elif kind == 'event':
                    event = text
                    if event.get('attempt'):
                        progress_count.set(f"第 {event['attempt']} 輪 / 最多 {values['max_attempts'].get()} 輪")
                    phases = {'homepage': '取得訂票頁面', 'captcha_image': '取得驗證碼', 'ocr': '辨識驗證碼',
                              'query': '查詢車次', 'select_train': '選擇車次', 'submit_ticket': '送出訂位'}
                    outcomes = {'captcha_rejected': '驗證碼遭拒，準備重試', 'ocr_no_candidate': '換一張驗證碼重試',
                                'no_matching_train': '沒有符合車次，等待重查', 'booked': '訂位成功',
                                'query_match': '找到符合車次', 'booking_unconfirmed': '訂位結果待確認'}
                    if event.get('phase') in phases:
                        progress_title.set(phases[event['phase']])
                    if event.get('outcome') in outcomes:
                        progress_title.set(outcomes[event['outcome']])
                elif kind == 'done':
                    set_active(False)
                    status.set(text)
                    progress_title.set(text)
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
