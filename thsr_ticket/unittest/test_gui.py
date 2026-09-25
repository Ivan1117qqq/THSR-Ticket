import queue
import json
import threading
from datetime import datetime
from unittest.mock import Mock

import pytest

from thsr_ticket.automation import TAIPEI
from thsr_ticket.gui import StoppableClient, form_config, run_background


def values():
    return dict(start_at=datetime.now(TAIPEI).isoformat(), outbound_date='2099-01-01',
                start_station='台北', dest_station='左營', earliest_departure='09:30', latest_departure='12:00',
                train_ids='0615，617', adult_tickets='1', child_tickets='0', disabled_tickets='0',
                elder_tickets='0', college_tickets='0', class_type='標準', personal_id='A123456789',
                phone_num='', interval_seconds='0.5', max_attempts='3', ocr_model='standard')


def test_form_mapping_and_validation():
    config = form_config(values())
    assert config.start_station == 2 and config.dest_station == 12
    assert config.train_ids == [615, 617]
    assert config.interval_seconds == 0.5
    for field, value in [('adult_tickets', '1.5'), ('max_attempts', '0'), ('personal_id', 'invalid')]:
        with pytest.raises(ValueError):
            form_config({**values(), field: value})


def test_stop_prevents_new_network_calls():
    stop = threading.Event()
    client = Mock()
    wrapper = StoppableClient(client, stop)
    wrapper.request_booking_page()
    stop.set()
    with pytest.raises(KeyboardInterrupt):
        wrapper.submit_ticket({})
    client.submit_ticket.assert_not_called()


def drain(messages):
    result = []
    while not messages.empty():
        result.append(messages.get_nowait())
    return result


@pytest.mark.parametrize('query_only', [True, False])
def test_worker_cleans_up_and_keeps_mode(tmp_path, monkeypatch, query_only):
    factory = Mock()
    flow = Mock()
    flow.return_value.run.return_value = True
    monkeypatch.setattr('thsr_ticket.gui.AutomationRunner', flow)
    messages = queue.Queue()
    run_background(form_config(values()), tmp_path / 'booking.local.json', query_only,
                   threading.Event(), messages, factory, Mock())
    flow.return_value.run.assert_called_once_with(query_only)
    factory.return_value.close.assert_called_once()
    assert drain(messages)[-1][0] == 'done'


def test_worker_existing_state_does_not_open_browser(tmp_path):
    path = tmp_path / 'booking.local.json'
    path.with_suffix('.state.json').write_text('{}')
    factory = Mock()
    messages = queue.Queue()
    run_background(form_config(values()), path, False, threading.Event(), messages, factory, Mock())
    factory.assert_not_called()
    assert drain(messages)[-1][0] == 'done'


def test_worker_cancel_wait_cleans_browser_without_query(tmp_path, monkeypatch):
    config = form_config({**values(), 'start_at': '2099-01-01T00:00:00+08:00'})
    stop = threading.Event()
    factory = Mock()
    reader = Mock()
    reader.return_value.prepare.side_effect = lambda: (stop.set() or True)
    flow = Mock()
    monkeypatch.setattr('thsr_ticket.gui.AutomationRunner', flow)
    messages = queue.Queue()
    run_background(config, tmp_path / 'booking.local.json', False, stop, messages, factory, reader)
    flow.assert_not_called()
    factory.return_value.close.assert_called_once()
    assert '已停止' in drain(messages)[-1][1]


def test_worker_exception_does_not_leak_private_message(tmp_path, monkeypatch):
    flow = Mock(side_effect=RuntimeError('A123456789 private'))
    monkeypatch.setattr('thsr_ticket.gui.AutomationRunner', flow)
    messages = queue.Queue()
    factory = Mock()
    run_background(form_config(values()), tmp_path / 'booking.local.json', False,
                   threading.Event(), messages, factory, Mock())
    output = str(drain(messages))
    assert 'A123456789' not in output
    factory.return_value.close.assert_called_once()


def test_missing_ocr_shows_actionable_message(tmp_path):
    factory = Mock()
    reader = Mock()
    reader.return_value.prepare.return_value = False
    messages = queue.Queue()
    run_background(form_config(values()), tmp_path / 'booking.local.json', False,
                   threading.Event(), messages, factory, reader)
    assert 'requirements-automation-lock.txt' in drain(messages)[-1][1]
    factory.return_value.close.assert_called_once()


@pytest.mark.parametrize('action', ['save', 'save_as', 'cancel', 'query', 'book', 'template'])
def test_desktop_load_validate_save_without_network(tmp_path, monkeypatch, action):
    tk = pytest.importorskip('tkinter')
    from tkinter import filedialog, messagebox, ttk
    from thsr_ticket.gui import main
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('Tk display unavailable')
    root.withdraw()
    source = tmp_path / ('booking.example.json' if action == 'template' else 'source.json')
    target = tmp_path / 'booking.local.json'
    source.write_text(form_config(values()).json(), encoding='utf-8')
    original = source.read_bytes()
    monkeypatch.setattr(tk, 'Tk', lambda: root)
    monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kwargs: str(source))
    save_dialog = Mock(return_value='' if action == 'cancel' else str(target))
    monkeypatch.setattr(filedialog, 'asksaveasfilename', save_dialog)
    thread = Mock()
    monkeypatch.setattr('thsr_ticket.gui.threading.Thread', thread)
    errors = Mock()
    monkeypatch.setattr(messagebox, 'showerror', errors)
    forbidden = Mock(side_effect=AssertionError('Must not start worker'))
    monkeypatch.setattr('thsr_ticket.gui.run_background', forbidden)
    failures = []

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    def interact():
        try:
            buttons = {widget.cget('text'): widget for widget in widgets(root) if isinstance(widget, ttk.Button)}
            buttons['載入設定'].invoke()
            buttons['驗證設定'].invoke()
            button = {'save_as': '另存設定', 'cancel': '另存設定', 'query': '只查票',
                      'book': '自動訂位（不付款）'}.get(action, '儲存設定')
            buttons[button].invoke()
            if action == 'cancel':
                assert not target.exists() and source.read_bytes() == original
                # Cancelling Save As retains the original save target.
                buttons['儲存設定'].invoke()
            expected = target if action in ('save_as', 'template') else source
            assert expected.exists()
            from thsr_ticket.automation import AutomationConfig
            saved = AutomationConfig.load(expected)
            assert saved.start_station == 2 and saved.train_ids == [615, 617]
            if action in ('save_as', 'template'):
                assert source.read_bytes() == original
            if action in ('save', 'query', 'book'):
                save_dialog.assert_not_called()
            else:
                save_dialog.assert_called_once()
            if action in ('query', 'book'):
                assert thread.call_args.kwargs['args'][1] == source
                assert thread.call_args.kwargs['args'][2] == (action == 'query')
                thread.return_value.start.assert_called_once()
            else:
                thread.assert_not_called()
            errors.assert_not_called()
            forbidden.assert_not_called()
        except BaseException as exc:
            failures.append(exc)
        finally:
            root.destroy()
    root.after(100, interact)
    main()
    if failures:
        raise failures[0]


@pytest.mark.parametrize('mode', ['archive', 'cancel', 'wrong_code', 'pending', 'blocked_start'])
def test_desktop_record_management(tmp_path, monkeypatch, mode):
    tk = pytest.importorskip('tkinter')
    from tkinter import filedialog, messagebox, simpledialog, ttk
    from thsr_ticket.gui import main
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('Tk display unavailable')
    root.withdraw()
    path = tmp_path / 'booking.local.json'
    path.write_text(form_config(values()).json(), encoding='utf-8')
    state = path.with_suffix('.state.json')
    state.write_text(json.dumps({'status': 'submission_pending' if mode == 'pending' else 'booked',
                                 'booking_codes': ['TEST1234']}))
    original = state.read_bytes()
    monkeypatch.setattr(tk, 'Tk', lambda: root)
    monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kwargs: str(path))
    monkeypatch.setattr(filedialog, 'asksaveasfilename', lambda **kwargs: str(path))
    errors, info = Mock(), Mock()
    monkeypatch.setattr(messagebox, 'showerror', errors)
    monkeypatch.setattr(messagebox, 'showinfo', info)
    prompt = Mock(return_value=None if mode == 'cancel' else 'WRONG' if mode == 'wrong_code' else 'TEST1234')
    monkeypatch.setattr(simpledialog, 'askstring', prompt)
    forbidden = Mock(side_effect=AssertionError('Must not start worker'))
    monkeypatch.setattr('thsr_ticket.gui.run_background', forbidden)
    failures = []

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    def interact():
        try:
            all_widgets = list(widgets(root))
            buttons = {widget.cget('text'): widget for widget in all_widgets if isinstance(widget, ttk.Button)}
            buttons['載入設定'].invoke()
            buttons['重新整理紀錄'].invoke()
            if mode == 'blocked_start':
                buttons['自動訂位（不付款）'].invoke()
                tabs = next(widget for widget in all_widgets if isinstance(widget, ttk.Notebook))
                assert tabs.tab(tabs.select(), 'text') == '訂位紀錄'
            else:
                buttons['封存目前訂位'].invoke()
            if mode == 'archive':
                assert not state.exists()
                archives = list((tmp_path / 'booking.local.runs').glob('archives/*/state.json'))
                assert len(archives) == 1 and archives[0].read_bytes() == original
                errors.assert_not_called()
            else:
                assert state.read_bytes() == original
            if mode == 'pending':
                prompt.assert_not_called()
            forbidden.assert_not_called()
        except BaseException as exc:
            failures.append(exc)
        finally:
            root.destroy()
    root.after(100, interact)
    main()
    if failures:
        raise failures[0]
