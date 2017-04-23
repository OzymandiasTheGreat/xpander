#!/usr/bin/env python3

import os
from setuptools import setup

src_dir = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(src_dir, 'README.md')) as readme:
	long_description = readme.read()

classifiers = ['Programming Language :: Python :: 3.5']
data_files = [
	('share/icons/hicolor/scalable/apps', [
		'data/xpander.svg',
		'data/xpander-active.svg',
		'data/xpander-paused.svg',
		'data/xpander-active-dark.svg',
		'data/xpander-paused-dark.svg']),
	('share/applications', [
		'data/xpander-indicator.desktop'])]

setup(
	name='xpander',
	version='1.0.0-beta1',
	description='Text expander for Linux',
	long_description=long_description,
	url='https://github.com/OzymandiasTheGreat/xpander',
	author='Tomas Ravinskas',
	author_email='tomas.rav@gmail.com',
	license='',
	classifiers=classifiers,
	package_dir={'xpander': 'lib'},
	packages=['xpander'],
	package_data={'xpander': ['Examples/*.json']},
	data_files=data_files,
	scripts=['xpander-indicator'],
	install_requires=['python3-xlib'],
)
