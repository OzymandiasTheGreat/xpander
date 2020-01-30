import json
from pathlib import Path
from configparser import ConfigParser
# from ast import literal_eval
from shutil import copytree
from traceback import format_tb
from appdirs import user_config_dir
from macpy import Key
from .phrase import asPhrase
from .server import Server
from .context import PHRASES


PKG = json.loads(Path("package.json").read_text())


class Settings(object):
	parser = ConfigParser()

	@classmethod
	def defaultConfig(cls):
		return Path('data/settings.ini')

	@classmethod
	def userConfig(cls):
		return Path(user_config_dir()) / PKG['name'] / 'settings.ini'

	@classmethod
	def getHotkey(cls, option):
		# key = literal_eval(cls.parser.get('HOTKEY', option))
		key = json.loads(json.loads(cls.parser.get('HOTKEY', option)))
		if key:
			keyName, modNames = key
			mainKey = getattr(Key, keyName)
			mods = []
			for modName in modNames:
				mods.append(getattr(Key, modName))
			return mainKey, tuple(mods)
		else:
			return key

	@classmethod
	def setHotkey(cls, option, hotkey):
		if hotkey:
			keyName = hotkey[0].name
			modNames = []
			for mod in hotkey[1]:
				modNames.append(mod.name)
			string = json.dumps((keyName, tuple(modNames)))
			cls.parser.set('HOTKEY', option, string)

	@classmethod
	def get(cls, option):
		return cls.parser.get('DEFAULT', option)

	@classmethod
	def set(cls, option, value):
		cls.parser.set('DEFAULT', option, str(value))

	@classmethod
	def getBool(cls, option):
		return cls.parser.getboolean('DEFAULT', option)

	@classmethod
	def getPath(cls, option):
		return Path(cls.parser.get('DEFAULT', option))

	@classmethod
	def load(cls):
		return cls.parser.read((cls.defaultConfig(), cls.userConfig()))

	@classmethod
	def save(cls):
		with cls.userConfig().open(mode='w') as fd:
			cls.parser.write(fd)


class Manager(object):

	def __init__(self):
		super().__init__()
		self.default = Path('data/phrases')
		self.phrases = {}

	def load(self):
		root = Settings.getPath('phrase_dir').expanduser()
		if not root.exists():
			self.writeDefaults(root)
		for filepath in root.glob('**/*.json'):
			phrase = self.loadPhrase(filepath, root)
			self.phrases[str(filepath.resolve())] = phrase
			PHRASES[phrase.name] = phrase

	def loadPhrase(self, filepath, root):
		filepath = filepath if isinstance(filepath, Path) else Path(filepath)
		try:
			with filepath.open() as fd:
				phrase = json.loads(fd.read(), object_hook=asPhrase)
				phrase.name = filepath.stem
				phrase.path = filepath.expanduser().relative_to(root)
		except Exception as e:
			msg = {
				'type': 'phraseLoad',
				'message': 'Error loading phrase at {}'.format(filepath),
				'error': repr(e),
				'traceback': format_tb(e.__traceback__),
			}
			Server.sendError(msg)
		return phrase

	def writeDefaults(self, dest):
		copytree(str(self.default.resolve()), str(dest.expanduser().resolve()))
