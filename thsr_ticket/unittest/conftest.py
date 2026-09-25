import pytest


def pytest_addoption(parser):
    parser.addoption('--live', action='store_true', help='Run live website checks (GET only).')
    parser.addoption('--browser-tests', action='store_true', help='Run offline tests in installed Chrome.')


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--browser-tests'):
        for item in items:
            if 'browser' in item.keywords:
                item.add_marker(pytest.mark.skip(reason='Use --browser-tests to test browser transport.'))
    if not config.getoption('--live'):
        for item in items:
            if 'integration' in item.keywords:
                item.add_marker(pytest.mark.skip(reason='Use --live to check the website.'))
