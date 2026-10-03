import json

from thsr_ticket.diagnostics import safe_event, snapshot


def test_export_excludes_private_fields_and_untrusted_text():
    secret = 'PRIVATE-ID-PHONE-CODE-PATH'
    events = [{'event': 'run_stopped', 'reason': 'network_timeout', 'phase': 'query',
               'attempt': 2, 'elapsed_ms': 21.125, 'exception': secret, 'path': secret,
               'personal_id': secret, 'code': secret, 'outcome': secret},
              {'event': 'train_selected', 'train_id': secret},
              {'event': secret}, {'event': 'stage', 'phase': secret, 'attempt': secret}]
    result = snapshot(events, secret, secret, False)
    assert secret not in json.dumps(result)
    assert result['events'][0] == {'event': 'run_stopped', 'reason': 'network_timeout',
                                   'phase': 'query', 'attempt': 2, 'elapsed_ms': 21.125}
    assert result['task'] == 'unknown'


def test_malformed_fields_and_nonfinite_timing_are_omitted():
    assert safe_event({'event': []}) is None
    assert safe_event({'event': 'stage', 'phase': {}, 'elapsed_ms': float('nan'),
                       'attempt': True}) == {'event': 'stage'}
    assert snapshot([], [], {}, False)['task'] == 'unknown'


def test_snapshot_is_bounded_and_detached():
    events = [{'event': 'stage', 'attempt': n} for n in range(300)]
    result = snapshot(events, 'network', '', False)
    assert len(result['events']) == 200
    assert result['events'][0]['attempt'] == 100
    events[-1]['attempt'] = 12345
    assert result['events'][-1]['attempt'] == 299
