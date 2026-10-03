"""Atomic config storage with optional Windows user-scoped DPAPI protection."""
import base64
import ctypes
import json
import os
from pathlib import Path

from thsr_ticket.run_records import atomic_json

PRIVATE_FIELDS = ('personal_id', 'phone_num')


def _dpapi(data, decrypt=False):
    if os.name != 'nt':
        raise ValueError('此設定的個資保護需要原 Windows 使用者帳號。')
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = (ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob))
    function.restype = wintypes.BOOL
    # UI_FORBIDDEN; deliberately no LOCAL_MACHINE flag.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('無法讀取或保護個資；請使用原 Windows 帳號，原檔未變更。')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree.argtypes = (ctypes.c_void_p,)
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(target.data)


def is_protected(data):
    return any(isinstance(data.get(key), dict) for key in PRIVATE_FIELDS)


def read_config_data(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('設定必須是 JSON 物件。')
    for key in PRIVATE_FIELDS:
        value = data.get(key)
        if isinstance(value, dict):
            if set(value) != {'protection', 'value'} or value['protection'] != 'windows-dpapi':
                raise ValueError('不支援的個資保護格式。')
            try:
                data[key] = _dpapi(base64.b64decode(value['value'], validate=True), decrypt=True).decode('utf-8')
            except (TypeError, UnicodeError) as exc:
                raise ValueError('無法讀取受保護的設定，原檔未變更。') from exc
    return data


def write_config_data(path, data, protect=False):
    stored = dict(data)
    for key in PRIVATE_FIELDS:
        if protect and stored.get(key):
            stored[key] = {'protection': 'windows-dpapi',
                           'value': base64.b64encode(_dpapi(str(stored[key]).encode('utf-8'))).decode('ascii')}
    atomic_json(Path(path), stored)
