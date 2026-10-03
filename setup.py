from setuptools import setup, find_packages
from thsr_ticket.version import VERSION

with open("requirements.txt", "r") as in_file:
    requirements = in_file.readlines()

setup(
    name='thsr-ticket',
    version=VERSION,
    description='An automatic booking program for Taiwan High Speed Railway(THSR).',
    author='BreezeWhite',
    author_email='miyashita2010@tuta.io',
    packages=find_packages(),
    install_requires=requirements,
    package_data={'thsr_ticket.desktop': ['qml/*.qml', 'assets/*.svg']},
    extras_require={'automation': ['playwright==1.63.0', 'ddddocr==1.6.1'],
                    'desktop': ['PySide6==6.10.2', 'playwright==1.63.0', 'ddddocr==1.6.1']},
    entry_points={'console_scripts': ['thsr-ticket = thsr_ticket.main:main'],
                  'gui_scripts': ['thsr-ticket-gui = thsr_ticket.desktop.__main__:main',
                                  'thsr-ticket-gui-legacy = thsr_ticket.gui:main']}
)
