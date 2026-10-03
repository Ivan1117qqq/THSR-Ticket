"""Ensure optional GUI tests cannot silently disappear from mandatory Windows CI."""
from types import SimpleNamespace

import pytest

from thsr_ticket.unittest.conftest import DesktopGate


def report(name, *, skipped=False, when='call'):
    return SimpleNamespace(nodeid='thsr_ticket/unittest/' + name,
                           skipped=skipped, passed=not skipped, when=when)


@pytest.mark.parametrize('case', ['complete', 'missing', 'collection_skip', 'runtime_skip', 'setup_only'])
def test_desktop_gate_requires_executed_suites(case):
    gate = DesktopGate()
    for name in gate.required:
        if name == 'test_desktop.py' and case != 'complete':
            if case == 'missing':
                continue
            if case == 'collection_skip':
                gate.pytest_collectreport(report(name, skipped=True, when=None))
            elif case == 'runtime_skip':
                gate.pytest_runtest_logreport(report(name + '::test_one', skipped=True))
                gate.pytest_runtest_logreport(report(name + '::test_two'))
            else:
                gate.pytest_runtest_logreport(report(name + '::test_one', when='setup'))
        else:
            gate.pytest_runtest_logreport(report(name + '::test_one'))
    gate.pytest_runtest_logreport(report('test_browser_request.py::test_optional', skipped=True))
    session = SimpleNamespace(exitstatus=0)
    gate.pytest_sessionfinish(session, 0)
    assert session.exitstatus == (0 if case == 'complete' else pytest.ExitCode.TESTS_FAILED)


def test_gate_preserves_existing_test_failure():
    gate = DesktopGate()
    for name in gate.required:
        gate.pytest_runtest_logreport(report(name + '::test_one'))
    session = SimpleNamespace(exitstatus=pytest.ExitCode.TESTS_FAILED)
    gate.pytest_sessionfinish(session, session.exitstatus)
    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
