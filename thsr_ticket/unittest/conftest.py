import pytest


def pytest_addoption(parser):
    parser.addoption('--require-desktop', action='store_true',
                     help='Fail unless every desktop suite runs without skips (Windows CI).')
    parser.addoption('--live', action='store_true', help='Run live website checks (GET only).')
    parser.addoption('--browser-tests', action='store_true', help='Run offline tests in installed Chrome.')


class DesktopGate:
    required = {'test_desktop.py', 'test_desktop_acceptance.py',
                'test_desktop_release.py', 'test_task_status.py', 'test_single_instance.py'}

    def __init__(self):
        self.passed = set()
        self.skipped = set()

    def record(self, report):
        name = report.nodeid.split('::')[0].replace('\\', '/').rsplit('/', 1)[-1]
        if name in self.required:
            if report.skipped:
                self.skipped.add(report.nodeid)
            elif getattr(report, 'when', None) == 'call' and report.passed:
                self.passed.add(name)

    pytest_collectreport = record
    pytest_runtest_logreport = record

    def pytest_sessionfinish(self, session, exitstatus):
        if self.required - self.passed or self.skipped:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter):
        missing = self.required - self.passed
        if missing or self.skipped:
            terminalreporter.write_sep('=', 'Desktop gate failed', red=True)
            terminalreporter.write_line('Missing passing suites: ' + ', '.join(sorted(missing)))
            terminalreporter.write_line('Skipped desktop tests: ' + ', '.join(sorted(self.skipped)))


def pytest_configure(config):
    if config.getoption('--require-desktop'):
        config.pluginmanager.register(DesktopGate(), 'desktop-gate')


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--browser-tests'):
        for item in items:
            if 'browser' in item.keywords:
                item.add_marker(pytest.mark.skip(reason='Use --browser-tests to test browser transport.'))
    if not config.getoption('--live'):
        for item in items:
            if 'integration' in item.keywords:
                item.add_marker(pytest.mark.skip(reason='Use --live to check the website.'))
