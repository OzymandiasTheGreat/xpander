#!/usr/bin/env python3

import os
import sys
from pathlib import Path
if sys.platform.startswith('linux'):
	from setuptools import setup
else:
	from cx_Freeze import setup, Executable
from xpander.version import __version__, appname, homepage, author
from xpander.version import author_email


if sys.argv[-1] == '--debug':
	DEBUG = True
	sys.argv.pop(-1)
else:
	DEBUG = False
if DEBUG:
	GUIBASE = 'Console'
else:
	GUIBASE = 'Win32GUI'


ROOT = Path(__file__).resolve().parent
DESCRIPTION = 'Text expander for Linux and Windows'


if sys.platform.startswith('linux'):
	with (ROOT / 'README.md').open() as fd:
		LONG_DESCRIPTION = fd.read()

	CLASSIFIERS = [
		'Development Status :: 4 - Beta',
		'Environment :: Win32 (MS Windows)',
		'Environment :: X11 Applications',
		'Intended Audience :: End Users/Desktop',
		'License :: OSI Approved :: MIT License',
		'Operating System :: Microsoft :: Windows',
		'Operating System :: POSIX :: Linux',
		'Programming Language :: Python :: 3.6',
		'Topic :: Utilities']

	DATA_FILES = (
		('share/icons/hicolor/scalable/apps', ('data/xpander.svg', )),
		('share/icons/hicolor/scalable/status', (
			'data/xpander-active.svg',
			'data/xpander-paused.svg',
			'data/xpander-active-light.svg',
			'data/xpander-paused-light.svg')),
		('share/applications', (
			'data/xpander-indicator.desktop',
			'data/xpander-gui.desktop')))

	setup(
		name=appname,
		version=__version__,
		description=DESCRIPTION,
		long_description=LONG_DESCRIPTION,
		url=homepage,
		author=author,
		author_email=author_email,
		license='MIT Licence',
		classifiers=CLASSIFIERS,
		package_dir={'xpander': 'xpander'},
		packages=['xpander'],
		package_data={'xpander': ('data/Examples/*.json', 'data/settings.ini')},
		data_files=DATA_FILES,
		scripts=('xpanderd', 'xpander-indicator', 'xpander-gui', 'xpander-cli'),
		install_requires=('macpy', 'klembord', 'appdirs', 'markdown2'))
else:
	INCLUDE_FILES = []
	SEARCH_PATH = os.getenv('PATH', os.defpath).split(os.pathsep)
	DLLS = (
		'libatk-1.0-0.dll',
		'libepoxy-0.dll',
		'libgdk-3-0.dll',
		'libgdk_pixbuf-2.0-0.dll',
		'libgio-2.0-0.dll',
		'libglib-2.0-0.dll',
		'libgtk-3-0.dll',
		'libgtksourceview-3.0-1.dll',
		'libpango-1.0-0.dll',
		'libpangocairo-1.0-0.dll',
		'libpangoft2-1.0-0.dll',
		'libpangowin32-1.0-0.dll',
		'librsvg-2-2.dll')
	GI_NAMESPACES = (
		'Atk-1.0',
		'cairo-1.0',
		'GdkPixbuf-2.0',
		'Gdk-3.0',
		'Gio-2.0',
		'GLib-2.0',
		'GModule-2.0',
		'GObject-2.0',
		'Gtk-3.0',
		'GtkSource-3.0',
		'Pango-1.0')
	PACKAGES = ('gi', 'xpander', 'pkg_resources._vendor.packaging', 'pyparsing')
	for icon in (ROOT / 'data').glob('*.svg'):
		INCLUDE_FILES.append(
			(str(icon.resolve()), 'data/{}'.format(icon.name)))
	for example in (ROOT / 'xpander/data/Examples').glob('*.json'):
		INCLUDE_FILES.append(
			(str(example.resolve()), 'data/Examples/{}'.format(example.name)))
	INCLUDE_FILES.append(
		(str(ROOT / 'xpander/data/settings.ini'), 'data/settings.ini'))
	INCLUDE_FILES.append((str(ROOT / 'README.md'), 'README.md'))
	INCLUDE_FILES.append((str(ROOT / 'LICENCE'), 'LICENCE'))
	for dll in DLLS:
		dll_path = None
		for path in SEARCH_PATH:
			path = Path(path, dll)
			if path.exists():
				dll_path = str(path)
				break
		assert dll_path is not None, "Can't find {} in 'PATH'".format(dll)
		INCLUDE_FILES.append((dll_path, dll))
	for namespace in GI_NAMESPACES:
		subpath = 'lib/girepository-1.0/{}.typelib'.format(namespace)
		fullpath = Path(sys.prefix, subpath)
		assert fullpath.exists(), 'Typelib missing: {}'.format(str(fullpath))
		INCLUDE_FILES.append((str(fullpath), subpath))
	# Include GdkPixbuf loaders
	INCLUDE_FILES.append(
		(r'C:\msys32\mingw32\lib\gdk-pixbuf-2.0', r'lib\gdk-pixbuf-2.0'))
	# Include date files, Gtk theme and icons
	INCLUDE_FILES.append(
		(r'C:\msys32\mingw32\share\glib-2.0\schemas',
		r'share\glib-2.0\schemas'))
	INCLUDE_FILES.append(
		(r'C:\msys32\mingw32\share\gtksourceview-3.0',
		r'share\gtksourceview-3.0'))
	INCLUDE_FILES.append(
		(r'C:\msys32\mingw32\share\icons\Adwaita', r'share\icons\Adwaita'))
	INCLUDE_FILES.append(
		(r'C:\msys32\mingw32\share\mime', r'share\mime'))
	INCLUDE_FILES.append(
		(r'C:\msys32\mingw32\share\themes\Default\gtk-3.0',
		r'share\themes\Default\gtk-3.0'))

	daemon = Executable(
		script='xpanderd',
		targetName='xpanderd.exe',
		base=GUIBASE,
		icon=str(ROOT / 'data/xpander.ico'),
		shortcutName='xpander daemon',
		shortcutDir='ProgramMenuFolder')

	indicator = Executable(
		script='xpander-indicator',
		targetName='xpander-indicator.exe',
		base=GUIBASE,
		icon=str(ROOT / 'data/xpander.ico'),
		shortcutName='xpander indicator',
		shortcutDir='ProgramMenuFolder')

	editor = Executable(
		script='xpander-gui',
		targetName='xpander-gui.exe',
		base=GUIBASE,
		icon=str(ROOT / 'data/xpander.ico'),
		shortcutName='Phrase Editor',
		shortcutDir='ProgramMenuFolder')

	console = Executable(
		script='xpander-cli',
		targetName='xpander-cli.exe',
		base='Console')

	setup(
		name=appname,
		author=author,
		author_email=author_email,
		version=__version__,
		url=homepage,
		description=DESCRIPTION,
		options={
			'build_exe': {
				'include_files': INCLUDE_FILES,
				'silent': True,
				'packages': PACKAGES,
				'include_msvcr': True},
			'bdist_msi': {
				'add_to_path': True,
				'upgrade_code': '573'}},
		executables=(daemon, indicator, editor, console))
