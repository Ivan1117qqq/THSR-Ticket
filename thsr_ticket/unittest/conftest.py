import pytest


def pytest_addoption(parser):
    parser.addoption('--live', action='store_true', help='Run live website checks (GET only).')


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--live'):
        for item in items:
            if 'integration' in item.keywords:
                item.add_marker(pytest.mark.skip(reason='Use --live to check the website.'))
