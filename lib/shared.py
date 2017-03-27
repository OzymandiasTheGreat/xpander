#!/usr/bin/env python3

import os

manager_shown = False

config = {
	'config_dir': os.path.expanduser('~/.config'),
	'phrases_dir': os.path.expanduser('~/.phrases'),

	'key_pause': ('p', ('<Shift>', '<Super>')),
	'key_show_manager': ('m', ('<Shift>', '<Super>')),

	'indicator_theme_light': True,
	'warn_folder_delete': True}
