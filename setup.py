from setuptools import setup, find_packages
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parent
VERSION = runpy.run_path(str(ROOT / 'thsr_ticket/version.py'))['VERSION']


def direct_requirements(name):
    return [line.strip() for line in (ROOT / name).read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.lstrip().startswith(('#', '-r', '-c'))]


requirements = direct_requirements('requirements.txt')
automation = direct_requirements('requirements-automation.txt')
desktop = automation + direct_requirements('requirements-desktop.txt')

setup(
    name='thsr-ticket',
    version=VERSION,
    description='An automatic booking program for Taiwan High Speed Railway(THSR).',
    author='BreezeWhite',
    author_email='miyashita2010@tuta.io',
    packages=find_packages(exclude=['thsr_ticket.unittest', 'thsr_ticket.unittest.*']),
    install_requires=requirements,
    package_data={'thsr_ticket.desktop': ['qml/*.qml', 'assets/*.svg']},
    extras_require={'automation': automation, 'desktop': desktop},
    entry_points={'console_scripts': ['thsr-ticket = thsr_ticket.main:main'],
                  'gui_scripts': ['thsr-ticket-gui = thsr_ticket.desktop.__main__:main',
                                  'thsr-ticket-gui-legacy = thsr_ticket.gui:main']}
)
