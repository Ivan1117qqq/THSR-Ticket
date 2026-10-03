import json
import os
from unittest.mock import Mock

import pytest

from thsr_ticket.config_store import read_config_data, write_config_data
from thsr_ticket.desktop.updates import check_release


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_dpapi_round_trip_without_plaintext_on_disk(tmp_path):
    path = tmp_path / 'config.json'
    original = {'personal_id': 'A123456789', 'phone_num': '0912345678', 'adult_tickets': 1}
    write_config_data(path, original, protect=True)
    text = path.read_text(encoding='utf-8')
    assert original['personal_id'] not in text and original['phone_num'] not in text
    assert read_config_data(path) == original
    damaged = json.loads(text)
    damaged['personal_id']['value'] = 'broken'
    path.write_text(json.dumps(damaged), encoding='utf-8')
    with pytest.raises(ValueError):
        read_config_data(path)
    assert json.loads(path.read_text()) == damaged


def test_update_checks_never_use_response_download_url():
    reply = Mock(status_code=200)
    reply.json.return_value = {'tag_name': 'v0.4.0', 'html_url': 'https://untrusted.invalid/file.exe'}
    get = Mock(return_value=reply)
    result = check_release('0.3.0', get=get)
    assert result['available']
    assert 'untrusted' not in str(result)
    assert get.call_args.kwargs['allow_redirects'] is False
    reply.json.return_value = {'tag_name': 'not-a-version'}
    with pytest.raises(ValueError):
        check_release('0.3.0', get=get)
    reply.status_code = 404
    assert not check_release('0.3.0', get=get)['available']
