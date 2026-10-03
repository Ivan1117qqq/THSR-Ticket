"""Allowlisted support snapshots, without raw logs or booking data."""
import platform
import sys
import math

from thsr_ticket.task_status import CODES
from thsr_ticket.version import VERSION

EVENTS = {'stage', 'attempt_finished', 'run_started', 'run_stopped', 'run_finished',
          'ocr', 'result_save_failed', 'state_update_failed'}
PHASES = {'prepare', 'schedule', 'homepage', 'captcha_image', 'ocr', 'query',
          'select_train', 'submit_ticket', 'parse_result'}
REASONS = {'interrupted', 'booking_unconfirmed', 'network_timeout', 'http_error', 'network_error',
           'website_rejected', 'ocr_unavailable', 'invalid_response_or_config', 'operation_failed'}


def allowed(value, choices):
    return isinstance(value, str) and value in choices


def safe_event(value):
    if not isinstance(value, dict) or not allowed(value.get('event'), EVENTS):
        return None
    result = {'event': value['event']}
    if allowed(value.get('phase'), PHASES):
        result['phase'] = value['phase']
    attempt = value.get('attempt')
    if type(attempt) is int and 0 <= attempt <= 1000000:
        result['attempt'] = attempt
    for key, choices in [('reason', REASONS), ('outcome', REASONS | {
            'completed', 'failed', 'success', 'attempt_limit', 'candidate', 'no_candidate'})]:
        if allowed(value.get(key), choices):
            result[key] = value[key]
    elapsed = value.get('elapsed_ms')
    if type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= 86400000:
        result['elapsed_ms'] = round(elapsed, 3)
    return result


def snapshot(events, task, guard, running):
    return {
        'schema_version': 1,
        'app_version': VERSION,
        'python_version': '.'.join(map(str, sys.version_info[:3])),
        'platform': platform.system(),
        'scope': 'current_app_session_only; latest 200 events; no historical files',
        'task': task if allowed(task, CODES | {'summary_unreadable'}) else 'unknown',
        'booking_guard': guard if allowed(guard, {'booked', 'pending', 'unreadable'}) else 'none',
        'running': bool(running),
        'events': [clean for event in list(events)[-200:] if (clean := safe_event(event))],
    }
