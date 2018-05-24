#!/usr/bin/env python3

import sys
from pathlib import Path
from configparser import ConfigParser
import json
import shutil
from pkg_resources import resource_filename
from ast import literal_eval
import traceback
from appdirs import user_config_dir
from macpy import Key
from .version import appname, vendor
from .phrase import Phrase, PhraseType, PasteMethod, PhraseEncoder, as_phrase


class Settings(ConfigParser):

	def __init__(self):

		super().__init__(empty_lines_in_values=False, interpolation=None)
		with self.default_path.open() as fd:
			self.read_file(fd)
		old_settings = Path('~/.config/xpander.json').expanduser()
		if old_settings.exists():
			with old_settings.open() as fd:
				old_data = json.loads(fd.read())
			self.set('phrase_dir', old_data['phrases_dir'])
			self.setbool('light_theme', not old_data['indicator_theme_light'])
			self.setbool('warn_folder', old_data['warn_folder_delete'])
			self.save()
			old_settings.unlink()
		else:
			self.read(self.user_path)

	@property
	def default_path(self):

		src = Path(__file__).parent / 'data/settings.ini'
		if getattr(sys, 'frozen', False):
			return Path(sys.executable, 'default.ini')
		else:
			if src.exists():
				return src
			else:
				return Path(resource_filename('xpander', 'data/settings.ini'))

	@property
	def user_path(self):

		if getattr(sys, 'frozen', False):
			portable = Path(sys.executable, 'user.ini')
			if portable.exists():
				return portable
		return Path(user_config_dir(appname, vendor), 'settings.ini')

	def getkey(self, option):

		key = literal_eval(super().get('HOTKEY', option))
		if key:
			key_name, mod_names = key
			key = getattr(Key, key_name)
			mods = []
			for name in mod_names:
				mods.append(getattr(Key, name))
			return key, tuple(mods)
		else:
			return key

	def setkey(self, option, key):

		if key:
			key_name = key[0].name
			mod_names = []
			for mod in key[1]:
				mod_names.append(mod.name)
			key = (key_name, tuple(mod_names))
		super().set('HOTKEY', option, repr(key))

	def save(self):

		if not self.user_path.exists():
			self.user_path.parent.mkdir(parents=True, exist_ok=True)
		with self.user_path.open(mode='w') as fd:
			self.write(fd, space_around_delimiters=False)

	def set(self, option, value, **kwargs):

		super().set(None, option, value, **kwargs)

	def setstr(self, option, value, **kwargs):

		super().set('DEFAULT', option, value, **kwargs)

	def setbool(self, option, value, **kwargs):

		super().set(None, option, repr(value), **kwargs)

	def setint(self, option, value, **kwargs):

		super().set(None, option, str(value), **kwargs)

	def get(self, section, option, **kwargs):

		return super().get('DEFAULT', option, **kwargs)

	def getstr(self, option, **kwargs):

		return super().get('DEFAULT', option, **kwargs)

	def getbool(self, option, **kwargs):

		return super().getboolean('DEFAULT', option, **kwargs)

	def getint(self, option, **kwargs):

		return super().getint('DEFAULT', option, **kwargs)

	def reload(self):

		self.read(self.user_path)

class Manager(object):

	def __init__(self, settings, daemon_path):

		self.settings = settings
		self.daemon_path = daemon_path
		self.phrases = {}
		self.load_phrases()

	def load_phrases(self):

		self.root = Path(
			self.settings.getstr('phrase_dir')).expanduser().resolve()
		if not self.root.exists():
			self.root.mkdir(parents=True, exist_ok=True)
			if getattr(sys, 'frozen', False):
				examples_src = self.daemon_path / 'data/Examples'
			else:
				examples_src = self.daemon_path / 'xpander/data/Examples'
			if examples_src.exists():
				shutil.copytree(str(examples_src), str(self.root / 'Examples'))
			else:
				examples = resource_filename('xpander', 'data/Examples')
				shutil.copytree(examples, str(self.root / 'Examples'))
		for filepath in self.root.glob('**/*.json'):
			try:
				try:
					with filepath.open() as fd:
						phrase = json.loads(fd.read(), object_hook=as_phrase)
				except KeyError:
					phrase = self.convert(filepath)
				phrase.name = filepath.stem
				phrase.path = filepath.relative_to(self.root)
				self.phrases[str(filepath)] = phrase
			except Exception as e:
				print('Error loading phrase:\n', filepath, '\n',
					*traceback.format_exception(type(e), e, e.__traceback__))

	def reload_phrases(self):

		self.phrases = {}
		self.load_phrases()

	def convert(self, filepath):

		with filepath.open() as fd:
			dct = json.loads(fd.read())
		phrasetype = (PhraseType.COMMAND
			if dct['command'] else PhraseType.PLAINTEXT)
		method = {
			0: PasteMethod.TYPE,
			1: PasteMethod.PASTE,
			2: PasteMethod.ALTPASTE}
		phrase = Phrase(
			dct['string'], (' ', '\n', '\t'), phrasetype, dct['body'],
			method[dct['method']], (dct['window_class'], ), dct['window_title'],
			None)
		with filepath.open(mode='w') as fd:
			fd.write(json.dumps(
				phrase, cls=PhraseEncoder, ensure_ascii=False, indent='\t'))
		return phrase

	def add(self, filepath):

		filepath = Path(filepath)
		filepath.parent.mkdir(parents=True, exist_ok=True)
		phrase = Phrase(
			'', (' ', '\n', '\t'), PhraseType.PLAINTEXT, '', PasteMethod.PASTE,
			(), '', None)
		with filepath.open(mode='w') as fd:
			fd.write(json.dumps(
				phrase, cls=PhraseEncoder, ensure_ascii=False, indent='\t'))
		phrase.name = filepath.stem
		phrase.path = filepath.relative_to(self.root)
		self.phrases[str(filepath)] = phrase

	def added(self, filepath):

		filepath = Path(filepath)
		with filepath.open() as fd:
			phrase = json.loads(fd.read(), object_hook=as_phrase)
		phrase.name = filepath.stem
		phrase.path = filepath.relative_to(self.root)
		self.phrases[str(filepath)] = phrase
		return phrase

	def edit(self, filepath, hotstring, triggers, phrasetype, body, method,
			wm_class, wm_title):

		phrase = self.phrases[filepath]
		phrase.hotstring = hotstring
		phrase.triggers = triggers
		phrase.type = phrasetype
		phrase.body = body
		phrase.method = method
		phrase.wm_class = wm_class
		phrase.wm_title = wm_title
		filepath = Path(filepath)
		with filepath.open(mode='w') as fd:
			fd.write(json.dumps(
				phrase, cls=PhraseEncoder, ensure_ascii=False, indent='\t'))

	def edited(self, filepath, phrase):

		old_phrase = self.phrases[filepath]
		old_phrase.hotstring = phrase.hotstring
		old_phrase.triggers = phrase.triggers
		old_phrase.type = phrase.type
		old_phrase.body = phrase.body
		old_phrase.method = phrase.method
		old_phrase.wm_class = phrase.wm_class
		old_phrase.wm_title = phrase.wm_title
		return old_phrase

	def set_hotkey(self, filepath, hotkey):

		phrase = self.phrases[filepath]
		phrase.hotkey = hotkey
		filepath = Path(filepath)
		with filepath.open(mode='w') as fd:
			fd.write(json.dumps(
				phrase, cls=PhraseEncoder, ensure_ascii=False, indent='\t'))

	def hotkey_set(self, filepath, hotkey):

		phrase = self.phrases[filepath]
		phrase.hotkey = hotkey
		return phrase

	def move(self, old_filepath, new_filepath):

		phrase = self.phrases[old_filepath]
		old_filepath = Path(old_filepath)
		new_filepath = Path(new_filepath)
		new_filepath.parent.mkdir(parents=True, exist_ok=True)
		old_filepath.rename(new_filepath)
		phrase.name = new_filepath.stem
		phrase.path = new_filepath.relative_to(self.root)
		del self.phrases[str(old_filepath)]
		self.phrases[str(new_filepath)] = phrase
		return phrase

	def moved(self, old_filepath, new_filepath, phrase):

		del self.phrases[old_filepath]
		self.phrases[new_filepath] = phrase

	def delete(self, filepath):

		del self.phrases[filepath]
		filepath = Path(filepath)
		filepath.unlink()

	def deleted(self, filepath):

		phrase = self.phrases[filepath]
		del self.phrases[filepath]
		return phrase
