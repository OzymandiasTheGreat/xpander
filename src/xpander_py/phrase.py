from enum import Enum
from jinja2 import Template
from macpy import Key


class PhraseType(Enum):
	PLAINTEXT = 'plaintext'
	RICHTEXT = 'richtext'


class PasteMethod(Enum):
	TYPE = 'type'
	PASTE = 'paste'
	ALTPASTE = 'altpaste'


class Phrase(object):

	def __init__(
		self, hotstring, triggers, phrasetype, body, method, wm_class, wm_title,
		hotkey):
		super().__init__()
		self.name = None
		self.path = None
		self.events = ()
		self.hotstring = hotstring
		self.triggers = tuple(triggers)
		self.type = PhraseType(phrasetype)
		self.body = body
		self.template = Template(body)
		self.method = PasteMethod(method)
		self.wm_class = tuple(wm_class)
		self.wm_title = wm_title
		self.hotkey = None
		if hotkey is not None:
			self.hotkey = (
				getattr(Key, hotkey[0]),
				tuple(getattr(Key, mod) for mod in hotkey[1])
			)

	def __hash__(self):
		return hash(self.name, self.path)

	def render(self, ctx):
		return self.template.render(ctx)


def asPhrase(dct):
	return Phrase(
		dct['hotstring'], dct['triggers'], dct['type'], dct['body'],
		dct['method'], dct['wm_class'], dct['wm_title'], dct['hotkey']
	)


def phraseToDict(phrase):
	return {
		'hotstring': phrase.hotstring,
		'triggers': phrase.triggers,
		'type': phrase.type.value,
		'body': phrase.body,
		'method': phrase.method.value,
		'wm_class': phrase.wm_class,
		'wm_title': phrase.wm_title,
		'hotkey': (
			phrase.hotkey[0].name, tuple(mod.name for mod in phrase.hotkey[1])
		),
	}
