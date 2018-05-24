#!/usr/bin/env python3

from enum import Enum
import json
from macpy import Key


class PhraseType(Enum):

	PLAINTEXT = 1
	RICHTEXT = 2
	MARKDOWN = 3
	COMMAND = 4
	HTML = 5


class PasteMethod(Enum):

	TYPE = 1
	PASTE = 2
	ALTPASTE = 3


class Phrase(dict):

	def __init__(
		self, hotstring, triggers, phrasetype, body, method, wm_class, wm_title,
		hotkey):

		self.__dict__['name'] = None
		self.__dict__['path'] = None
		self.__dict__['events'] = ()
		self['hotstring'] = str(hotstring)
		if all(isinstance(trigger, str) for trigger in triggers):
			self['triggers'] = tuple(triggers)
		else:
			raise TypeError('Invalid triggers')
		if isinstance(phrasetype, PhraseType):
			self['type'] = phrasetype
		else:
			self['type'] = PhraseType(phrasetype)
		self['body'] = str(body)
		if isinstance(method, PasteMethod):
			self['method'] = method
		else:
			self['method'] = PasteMethod(method)
		if all(isinstance(class_, str) for class_ in wm_class):
			self['wm_class'] = tuple(wm_class)
		else:
			raise TypeError('Invalid wm_class')
		self['wm_title'] = str(wm_title)
		if hotkey is not None:
			if (isinstance(hotkey[0], str)
					and all(isinstance(key, str) for key in hotkey[1])):
				self['hotkey'] = (
					getattr(Key, hotkey[0]),
					tuple(getattr(Key, key) for key in hotkey[1]))
			elif (isinstance(hotkey[0], Key)
					and all(isinstance(key, Key) for key in hotkey[1])):
				self['hotkey'] = hotkey
			else:
				raise TypeError('Invalid hotkey')
		else:
			self['hotkey'] = None

	def __getattr__(self, attr):

		if attr in self:
			return self[attr]
		elif attr in self.__dict__:
			return self.__dict__[attr]
		else:
			return getattr(super(), attr)

	def __setattr__(self, attr, value):

		if attr in self:
			self[attr] = value
		elif attr in self.__dict__:
			self.__dict__[attr] = value
		else:
			raise AttributeError(
				'{0} has no attribute {1}'.format(type(self).__name__, attr))

	def __setitem__(self, key, value):

		if key == 'hotstring':
			super().__setitem__(key, str(value))
		elif key == 'triggers':
			if all(isinstance(trigger, str) for trigger in value):
				super().__setitem__(key, tuple(value))
			else:
				raise TypeError('Invalid triggers')
		elif key == 'type':
			if isinstance(value, PhraseType):
				super().__setitem__(key, value)
			else:
				super().__setitem__(key, PhraseType(value))
		elif key == 'body':
			super().__setitem__(key, str(value))
		elif key == 'method':
			if isinstance(value, PasteMethod):
				super().__setitem__(key, value)
			else:
				super().__setitem__(key, PasteMethod(value))
		elif key == 'wm_class':
			if all(isinstance(class_, str) for class_ in value):
				super().__setitem__(key, tuple(value))
			else:
				raise TypeError('Invalid wm_class')
		elif key == 'wm_title':
			super().__setitem__(key, str(value))
		elif key == 'hotkey':
			super().__setitem__(key, value)
		else:
			raise KeyError(key)

	def __hash__(self):

		return hash((self.path, self.name))


class PhraseEncoder(json.JSONEncoder):

	def default(self, obj):

		if isinstance(obj, Enum):
			return obj.value
		return super().default(obj)


def as_phrase(dct):

	return Phrase(
		dct['hotstring'], dct['triggers'], dct['type'], dct['body'],
		dct['method'], dct['wm_class'], dct['wm_title'], dct['hotkey'])


# This code is copy-pasted from stdlib json.encoder module with changes
# marked as such in comments
def monkey_patch(markers, _default, _encoder, _indent, _floatstr,
		_key_separator, _item_separator, _sort_keys, _skipkeys, _one_shot,
		## HACK: hand-optimized bytecode; turn globals into locals
		ValueError=ValueError,
		dict=dict,
		float=float,
		id=id,
		int=int,
		isinstance=isinstance,
		list=list,
		str=str,
		tuple=tuple,
		_intstr=int.__str__,
	):

	if _indent is not None and not isinstance(_indent, str):
		_indent = ' ' * _indent

	def _iterencode_list(lst, _current_indent_level):
		# Detection and special handling for macpy.Key instances
		if isinstance(lst, Key):
			yield '"{}"'.format(lst.name)
			return
		if not lst:
			yield '[]'
			return
		if markers is not None:
			markerid = id(lst)
			if markerid in markers:
				raise ValueError("Circular reference detected")
			markers[markerid] = lst
		buf = '['
		if _indent is not None:
			_current_indent_level += 1
			newline_indent = '\n' + _indent * _current_indent_level
			separator = _item_separator + newline_indent
			buf += newline_indent
		else:
			newline_indent = None
			separator = _item_separator
		first = True
		for value in lst:
			if first:
				first = False
			else:
				buf = separator
			if isinstance(value, str):
				yield buf + _encoder(value)
			elif value is None:
				yield buf + 'null'
			elif value is True:
				yield buf + 'true'
			elif value is False:
				yield buf + 'false'
			elif isinstance(value, int):
				# Subclasses of int/float may override __str__, but we still
				# want to encode them as integers/floats in JSON. One example
				# within the standard library is IntEnum.
				yield buf + _intstr(value)
			elif isinstance(value, float):
				# see comment above for int
				yield buf + _floatstr(value)
			else:
				yield buf
				if isinstance(value, (list, tuple)):
					chunks = _iterencode_list(value, _current_indent_level)
				elif isinstance(value, dict):
					chunks = _iterencode_dict(value, _current_indent_level)
				else:
					chunks = _iterencode(value, _current_indent_level)
				yield from chunks
		if newline_indent is not None:
			_current_indent_level -= 1
			yield '\n' + _indent * _current_indent_level
		yield ']'
		if markers is not None:
			del markers[markerid]

	def _iterencode_dict(dct, _current_indent_level):
		if not dct:
			yield '{}'
			return
		if markers is not None:
			markerid = id(dct)
			if markerid in markers:
				raise ValueError("Circular reference detected")
			markers[markerid] = dct
		yield '{'
		if _indent is not None:
			_current_indent_level += 1
			newline_indent = '\n' + _indent * _current_indent_level
			item_separator = _item_separator + newline_indent
			yield newline_indent
		else:
			newline_indent = None
			item_separator = _item_separator
		first = True
		if _sort_keys:
			items = sorted(dct.items(), key=lambda kv: kv[0])
		else:
			items = dct.items()
		for key, value in items:
			if isinstance(key, str):
				pass
			# JavaScript is weakly typed for these, so it makes sense to
			# also allow them.  Many encoders seem to do something like this.
			elif isinstance(key, float):
				# see comment for int/float in _make_iterencode
				key = _floatstr(key)
			elif key is True:
				key = 'true'
			elif key is False:
				key = 'false'
			elif key is None:
				key = 'null'
			elif isinstance(key, int):
				# see comment for int/float in _make_iterencode
				key = _intstr(key)
			elif _skipkeys:
				continue
			else:
				raise TypeError("key " + repr(key) + " is not a string")
			if first:
				first = False
			else:
				yield item_separator
			yield _encoder(key)
			yield _key_separator
			if isinstance(value, str):
				yield _encoder(value)
			elif value is None:
				yield 'null'
			elif value is True:
				yield 'true'
			elif value is False:
				yield 'false'
			elif isinstance(value, int):
				# see comment for int/float in _make_iterencode
				yield _intstr(value)
			elif isinstance(value, float):
				# see comment for int/float in _make_iterencode
				yield _floatstr(value)
			else:
				if isinstance(value, (list, tuple)):
					chunks = _iterencode_list(value, _current_indent_level)
				elif isinstance(value, dict):
					chunks = _iterencode_dict(value, _current_indent_level)
				else:
					chunks = _iterencode(value, _current_indent_level)
				yield from chunks
		if newline_indent is not None:
			_current_indent_level -= 1
			yield '\n' + _indent * _current_indent_level
		yield '}'
		if markers is not None:
			del markers[markerid]

	def _iterencode(o, _current_indent_level):
		if isinstance(o, str):
			yield _encoder(o)
		elif o is None:
			yield 'null'
		elif o is True:
			yield 'true'
		elif o is False:
			yield 'false'
		elif isinstance(o, int):
			# see comment for int/float in _make_iterencode
			yield _intstr(o)
		elif isinstance(o, float):
			# see comment for int/float in _make_iterencode
			yield _floatstr(o)
		elif isinstance(o, (list, tuple)):
			yield from _iterencode_list(o, _current_indent_level)
		elif isinstance(o, dict):
			yield from _iterencode_dict(o, _current_indent_level)
		else:
			if markers is not None:
				markerid = id(o)
				if markerid in markers:
					raise ValueError("Circular reference detected")
				markers[markerid] = o
			o = _default(o)
			yield from _iterencode(o, _current_indent_level)
			if markers is not None:
				del markers[markerid]
	return _iterencode


json.encoder._make_iterencode = monkey_patch
