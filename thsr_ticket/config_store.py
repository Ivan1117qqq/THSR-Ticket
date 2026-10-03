"""Atomic config storage with optional Windows user-scoped DPAPI protection."""
import base64
import ctypes
import json
import os
from pathlib import Path
from uuid import uuid4

from thsr_ticket.run_records import atomic_json

PRIVATE_FIELDS = ('personal_id', 'phone_num')
SCHEMA_VERSION = 1
VERSION_KEY = '_schema_version'


class ConfigVersionError(ValueError):
    """Safe fixed text suitable for displaying without exposing file contents."""


def config_payload(data):
    if not isinstance(data, dict):
        raise ValueError('設定必須是 JSON 物件。')
    if VERSION_KEY in data:
        version = data[VERSION_KEY]
        if type(version) is not int or version != SCHEMA_VERSION:
            raise ConfigVersionError('不支援此設定格式版本，請使用相容版本的程式；原檔未變更。')
    return {key: value for key, value in data.items() if key != VERSION_KEY}


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
    data = config_payload(json.loads(Path(path).read_text(encoding='utf-8-sig')))
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
    path = Path(path)
    stored = config_payload(data)
    original = None
    if path.exists():
        original = path.read_bytes()
        previous = json.loads(original.decode('utf-8-sig'))
        config_payload(previous)  # Never overwrite unknown future formats or damaged JSON.
        if VERSION_KEY in previous:
            original = None
    stored[VERSION_KEY] = SCHEMA_VERSION
    for key in PRIVATE_FIELDS:
        if protect and stored.get(key):
            stored[key] = {'protection': 'windows-dpapi',
                           'value': base64.b64encode(_dpapi(str(stored[key]).encode('utf-8'))).decode('ascii')}
    if original is not None:
        backups = path.parent / (path.name + '.config-backups')
        backups.mkdir(exist_ok=True)
        with (backups / (uuid4().hex + '.json')).open('xb') as handle:
            handle.write(original)
            handle.flush()
            os.fsync(handle.fileno())
    atomic_json(path, stored)
