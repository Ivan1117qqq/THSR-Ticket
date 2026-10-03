"""Explicit update checks; open the known release page, never auto-execute downloaded code."""
import re
import requests

RELEASES = 'https://github.com/Ivan1117qqq/THSR-Ticket/releases'
LATEST_API = 'https://api.github.com/repos/Ivan1117qqq/THSR-Ticket/releases/latest'


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('Unsupported version')
    return tuple(int(part) for part in value.lstrip('v').split('.'))


def check_release(current, get=requests.get):
    response = get(LATEST_API, timeout=(5, 10), allow_redirects=False,
                   headers={'Accept': 'application/vnd.github+json'})
    if response.status_code == 404:
        return {'message': '尚未發布正式版本。', 'available': False}
    response.raise_for_status()
    data = response.json()
    version = data.get('tag_name')
    if data.get('draft') or data.get('prerelease'):
        return {'message': '目前沒有新的正式版本。', 'available': False}
    newer = version_tuple(version) > version_tuple(current)
    return {'message': f'有新版本 {version}，可開啟發行頁查看。' if newer else '目前已是最新版本。',
            'available': newer}
