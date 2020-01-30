#!/usr/bin/env python3

import traceback
from threading import Thread
from queue import Queue
import sys
import time
import shlex
import subprocess
import re
from datetime import datetime, timedelta
if sys.platform.startswith('win32'):
	from ctypes import windll, c_void_p, c_uint, c_int, c_bool, POINTER, byref
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from markdown2 import Markdown
from macpy import Keyboard, HotString, HotKey, Key, KeyState, Window, Pointer
from macpy import PointerEventButton, KeyboardEvent
from macpy.platform import Platform, PLATFORM
if sys.platform.startswith('linux'):
	import klembord as Primary
	del sys.modules['klembord']
import klembord as Clipboard
from .phrase import Phrase, PhraseType, PasteMethod
from .gtk_dialogs import FILLIN, FillDialog
from .html import PlainText


Clipboard.init()
if sys.platform.startswith('linux'):
	Primary.init('PRIMARY')
CARET = '$|'
CLIPBOARD = '$C'
PRIMARY = '$S'
TRIGKEEP = '$+'
TRIGREM = '$-'
REKEY = re.compile(r'\$\{(?P<key>KEY_\w+)(?:\:(?P<state>(?:down)|(?:up)))?\}')
REMATH = re.compile(
	r'(?:\%\@(?P<sign>\+|\-)(?P<value>\d+)(?P<measure>[YMDWhms]))')
REFORMAT = re.compile(
	r'(?P<format>(?:\%[AaBbcdHIjMmpSUWwXxYyZz](?:[^\%](?<!\%@))*)+)')
REPHRASE = re.compile(r'\$\<(?P<phrase>.+?)\>')


class Service(Thread):

	if sys.platform.startswith('win32'):
		windll.user32.GetForegroundWindow.argtypes = ()
		windll.user32.GetForegroundWindow.restype = c_void_p
		windll.user32.PostMessageW.argtypes = (c_void_p, c_uint, c_int, c_uint)
		windll.user32.PostMessageW.restype = c_bool
		windll.user32.GetFocus.argtypes = ()
		windll.user32.GetFocus.restype = c_void_p
		windll.kernel32.GetCurrentThreadId.argtypes = ()
		windll.kernel32.GetCurrentThreadId.restype = c_uint
		windll.user32.AttachThreadInput.argtypes = (c_uint, c_uint, c_bool)
		windll.user32.AttachThreadInput.restype = c_bool
		windll.user32.GetWindowThreadProcessId.argtypes = (
			c_void_p, POINTER(c_uint))
		windll.user32.GetWindowThreadProcessId.restype = c_uint

	def __init__(self, settings):

		super().__init__(name='xpander service')
		self.settings = settings
		self.server = None
		self.queue = Queue()
		self.keyboard = Keyboard()
		self.keyboard.install_keyboard_hook(lambda event: None)
		# ~ self.keyboard.install_keyboard_hook(lambda event: print(event.char))
		self.keyboard.init_hotkeys()
		if PLATFORM is Platform.WAYLAND:
			self.pointer = Pointer()
		self.caret_pos = []
		self.markdown = Markdown()
		self.plaintext = PlainText()
		self.phrases = {}
		self.names = {}
		self.pause = False

		self.tab_key = None
		self.pause_key = None
		self.editor_key = None
		self.mods = {'SHIFT': False, 'ALTGR': False, 'CTRL': False, 'ALT': False,
			'META': False}
		self.locks = {'NUMLOCK': False, 'CAPSLOCK': False, 'SCROLLLOCK': False}
		self.tab_down_event = KeyboardEvent(
			Key.KEY_TAB, KeyState.PRESSED, None, self.mods, self.locks)
		self.tab_up_event = KeyboardEvent(
			Key.KEY_TAB, KeyState.RELEASED, None, self.mods, self.locks)
		self.right_down_event = KeyboardEvent(
			Key.KEY_RIGHT, KeyState.PRESSED, None, self.mods, self.locks)
		self.right_up_event = KeyboardEvent(
			Key.KEY_RIGHT, KeyState.RELEASED, None, self.mods, self.locks)

	def register_hotkeys(self):

		if self.settings.getbool('use_tab'):
			self.tab_key = self.keyboard.register_hotkey(
				Key.KEY_TAB, (), self.callback)
		pause_key = self.settings.getkey('pause')
		if pause_key:
			self.pause_key = self.keyboard.register_hotkey(
				*pause_key, self.callback)
		editor_key = self.settings.getkey('manager')
		if editor_key:
			self.editor_key = self.keyboard.register_hotkey(
				*editor_key, self.callback)

	def unregister_hotkeys(self):

		if self.tab_key:
			self.keyboard.unregister_hotkey(self.tab_key)
		if self.pause_key:
			self.keyboard.unregister_hotkey(self.pause_key)
		if self.editor_key:
			self.keyboard.unregister_hotkey(self.editor_key)

	def register_phrase(self, phrase):

		if phrase.hotstring:
			triggers = phrase.triggers
			if sys.platform.startswith('win32') and '\n' in triggers:
				triggers = list(triggers)
				triggers.remove('\n')
				triggers.append('\r')
			hotstring = self.keyboard.register_hotstring(
				phrase.hotstring, triggers, self.callback)
			self.phrases[hotstring] = phrase
		if phrase.hotkey:
			hotkey = self.keyboard.register_hotkey(
				phrase.hotkey[0], phrase.hotkey[1], self.callback)
			self.phrases[hotkey] = phrase
		self.names[phrase.name] = phrase
		if phrase.hotstring and phrase.hotkey:
			phrase.events = (hotstring, hotkey)
		if phrase.hotstring and not phrase.hotkey:
			phrase.events = (hotstring, )
		if not phrase.hotstring and phrase.hotkey:
			phrase.events = (hotkey, )

	def unregister_phrase(self, phrase):

		for event in phrase.events:
			del self.phrases[event]
			if isinstance(event, HotString):
				self.keyboard.unregister_hotstring(event)
			else:
				self.keyboard.unregister_hotkey(event)
		phrase.events = ()

	def callback(self, event):

		# ~ print(event)
		if event == self.tab_key and PLATFORM is not Platform.WAYLAND:
			window = Window.get_active()
			try:
				steps = self.caret_pos.pop(0)
				self.cycle_caret(steps, window)
			except IndexError:
				window.send_event(self.tab_down_event)
				window.send_event(self.tab_up_event)
		elif event == self.pause_key:
			if self.server:
				self.server.toggle_pause(None)
		elif event == self.editor_key:
			if self.server:
				self.server.run_editor()
		else:
			try:
				phrase = self.phrases[event]
				self.enqueue(phrase, event)
			except KeyError as e:
				print(
					'Error in xpander service callback:\n',
					traceback.format_exception(
						type(e), e, e.__traceback__))

	def enqueue(self, method, *args):

		self.queue.put_nowait((method, args))

	def run(self):

		while True:
			method, args = self.queue.get()
			if method is None:
				break
			elif not isinstance(method, Phrase):
				try:
					method(*args)
				except Exception as e:
					print(
						'Exception in xpander service:\n',
						traceback.format_exception(
							type(e), e, e.__traceback__))
			else:
				try:
					if not self.pause:
						phrase = method
						event = args[0]
						if self.match_wm(phrase):
							if isinstance(event, HotString):
								hotstring = event
							else:
								hotstring = None
							if hotstring:
								self.backspace(hotstring)
							richtext = False
							keep_trig = self.settings.getbool('keep_trig')
							if phrase.type in {PhraseType.RICHTEXT,
									PhraseType.HTML, PhraseType.MARKDOWN}:
								richtext = True
							body = phrase.body
							if REPHRASE.search(body):
								body = self.embed(body, richtext)
							if keep_trig:
								if TRIGREM in body:
									keep_trig = False
									body = body.replace(TRIGREM, '')
							else:
								if TRIGKEEP in body:
									keep_trig = True
									body = body.replace(TRIGKEEP, '')
							if phrase.type is PhraseType.MARKDOWN:
								body = self.markdown.convert(body)
							if REMATH.search(body) or REFORMAT.search(body):
								body = self.datetime(body)
							if CLIPBOARD in body or PRIMARY in body:
								body = self.expand_selections(body, richtext)
							if phrase.type is PhraseType.COMMAND:
								body = self.run_command(body)
							if FILLIN.search(body):
								dialog = FillDialog(body, richtext)
								response = dialog.run()
								if response == Gtk.ResponseType.OK:
									body = dialog.get_string()
								dialog.destroy()
								while Gtk.events_pending():
									Gtk.main_iteration()
							move_caret = False
							if CARET in body:
								if richtext:
									body_wc = self.plaintext.extract(
										body, False)
								else:
									body_wc = body
								body = body.replace(CARET, '')
								move_caret = True
							time.sleep(0.05)
							if sys.platform.startswith('linux'):
								body = body.replace('\r\n', '\n')
							else:
								body = body.replace('\n', '\r\n')
							if REKEY.search(body):
								self.send_with_keys(phrase, body, richtext)
							else:
								self.send(phrase, body, richtext)
							if keep_trig and hotstring:
								self.send(phrase, hotstring.trigger, False)
								if move_caret:
									body_wc += hotstring.trigger
							if move_caret:
								self.move_caret(body_wc)
				except Exception as e:
					print(
						'Error while expanding:\n',
						*traceback.format_exception(
							type(e), e, e.__traceback__))

	def match_wm(self, phrase):

		if PLATFORM is Platform.WAYLAND:
			return True
		window = Window.get_active()
		if phrase.wm_class:
			class_match = False
			for wm_class in phrase.wm_class:
				if wm_class == window.wm_class:
					class_match = True
		else:
			class_match = True
		title_match = True if phrase.wm_title in window.title else False
		return class_match and title_match

	def backspace(self, hotstring):

		length = len(hotstring.string)
		if self.settings.getbool('use_tab') and hotstring.trigger == '\t':
			length - 1
		if hotstring.triggers:
			length += 1
		for i in range(length):
			self.keyboard.keypress(Key.KEY_BACKSPACE)
		if sys.platform.startswith('win32'):
			time.sleep(0.2)

	def embed(self, string, richtext):

		for match in REPHRASE.finditer(string):
			if match['phrase'] in self.names:
				phrase = self.names[match['phrase']]
				body = phrase.body
				if (not richtext and phrase.type in {PhraseType.RICHTEXT,
						PhraseType.HTML, PhraseType.MARKDOWN}):
					body = self.plaintext.extract(body, False)
				string = string.replace(match[0], body)
		return string

	def expand_selections(self, string, richtext):

		content  = Clipboard.get_with_rich_text()
		content = (content[0] if content[0] else '', content[1])
		if richtext:
			string = string.replace(
				CLIPBOARD, content[1] if content[1] else content[0])
		else:
			string = string.replace(CLIPBOARD, content[0])
		pcontent = ('', '')
		if sys.platform.startswith('linux'):
			pcontent = Primary.get_with_rich_text()
			pcontent = (
				pcontent[0] if pcontent[0] else '', pcontent[1])
		if richtext:
			string = string.replace(
				PRIMARY, pcontent[1] if pcontent[1] else pcontent[0])
		else:
			string = string.replace(PRIMARY, pcontent[0])
		return string

	def datetime(self, string):

		new_string = string
		now = datetime.now()
		dates = []
		for match in REMATH.finditer(string):
			date = {}
			if match['measure'] == 'Y':
				if match['sign'] == '+':
					dt = now.replace(year=now.year + int(match['value']))
				else:
					dt = now.replace(year=now.year - int(match['value']))
			elif match['measure'] == 'M':
				year = 0
				month = int(match['value'])
				if month > 12:
					year = month // 12
					month = month % 12
				if match['sign'] == '+':
					dt = now.replace(
						year=now.year + year, month=now.month + month)
				else:
					dt = now.replace(
						year=now.year - year, month=now.month - month)
			elif match['measure'] == 'D':
				delta = timedelta(days=int(match['value']))
				if match['sign'] == '+':
					dt = now + delta
				else:
					dt = now - delta
			elif match['measure'] == 'W':
				delta = timedelta(weeks=int(match['value']))
				if match['sign'] == '+':
					dt = now + delta
				else:
					dt = now - delta
			elif match['measure'] == 'h':
				delta = timedelta(hours=int(match['value']))
				if match['sign'] == '+':
					dt = now + delta
				else:
					dt = now - delta
			elif match['measure'] == 'm':
				delta = timedelta(minutes=int(match['value']))
				if match['sign'] == '+':
					dt = now + delta
				else:
					dt = now - delta
			elif match['measure'] == 's':
				delta = timedelta(seconds=int(match['value']))
				if match['sign'] == '+':
					dt = now + delta
				else:
					dt = now - delta
			date['date'] = dt
			date['start'] = match.start()
			if dates:
				dates[-1]['end'] = match.start()
			dates.append(date)
		if dates:
			dates[-1]['end'] = len(string)

		for match in REFORMAT.finditer(string):
			if dates:
				if dates[0]['start'] < match.start() < dates[0]['end']:
					new_string = new_string.replace(
						match[0], dates[0]['date'].strftime(match[0]), 1)
				elif match.start() < dates[0]['start']:
					new_string = new_string.replace(
						match[0], now.strftime(match[0]), 1)
				else:
					dates.pop(0)
					new_string = new_string.replace(
						match[0], dates[0]['date'].strftime(match[0]), 1)
			else:
				new_string = new_string.replace(
					match[0], now.strftime(match[0]), 1)

		new_string = REMATH.sub('', new_string)
		return new_string

	def run_command(self, string):

		process = subprocess.run(
			shlex.split(string),
			stdout=subprocess.PIPE,
			timeout=1,
			universal_newlines=True)
		return process.stdout.strip()

	def type(self, string, richtext):

		if richtext:
			string = self.plaintext.extract(string, False)
		self.keyboard.type(string)

	def paste(self, string, richtext):

		content = Clipboard.get_with_rich_text()
		if richtext:
			plaintext = self.plaintext.extract(string, False)
			Clipboard.set_with_rich_text(plaintext, string)
		else:
			Clipboard.set_text(string)
		if PLATFORM is not Platform.WAYLAND:
			window = Window.get_active()
			mods = {'SHIFT': False, 'ALTGR': False, 'CTRL': True, 'ALT': False,
				'META': False}
			vd = KeyboardEvent(
				Key.KEY_V, KeyState.PRESSED, None, mods, self.locks)
			vu = KeyboardEvent(
				Key.KEY_V, KeyState.RELEASED, None, mods, self.locks)
			window.send_event(vd)
			window.send_event(vu)
		else:
			self.keyboard.keypress(Key.KEY_CTRL, state=KeyState.PRESSED)
			self.keyboard.keypress(Key.KEY_V)
			self.keyboard.keypress(Key.KEY_CTRL, state=KeyState.RELEASED)
		if sys.platform.startswith('linux'):
			time.sleep(0.1)
		Clipboard.set_with_rich_text(*content)

	def altpaste(self, string, richtext):

		if sys.platform.startswith('linux'):
			content = Primary.get_with_rich_text()
			if richtext:
				plaintext = self.plaintext.extract(string, False)
				Primary.set_with_rich_text(plaintext, string)
			else:
				Primary.set_text(string)
			if PLATFORM is not Platform.WAYLAND:
				window = Window.get_active()
				x, y = window.size
				dev = PointerEventButton(
					x // 2, y // 2, Key.BTN_MIDDLE, KeyState.PRESSED, self.mods)
				uev = PointerEventButton(
					x // 2, y // 2, Key.BTN_MIDDLE, KeyState.RELEASED, self.mods)
				window.send_event(dev)
				window.send_event(uev)
			else:
				self.pointer.click(Key.BTN_MIDDLE)
			time.sleep(0.1)
			Primary.set_with_rich_text(*content)
		else:
			content = Clipboard.get_with_rich_text()
			if richtext:
				plaintext = self.plaintext.extract(string, False)
				Clipboard.set_with_rich_text(plaintext, string)
			else:
				Clipboard.set_text(string)
			wnd = windll.user32.GetForegroundWindow()
			tId = windll.user32.GetWindowThreadProcessId(wnd, byref(c_uint(0)))
			cId = windll.kernel32.GetCurrentThreadId()
			windll.user32.AttachThreadInput(cId, tId, True)
			hwnd = windll.user32.GetFocus()
			windll.user32.AttachThreadInput(cId, tId, False)
			# WM_PASTE
			windll.user32.PostMessageW(hwnd, 0x0302, 0, 0)
			time.sleep(0.1)
			Clipboard.set_with_rich_text(*content)

	def send(self, phrase, body, richtext):

		if phrase.method is PasteMethod.TYPE:
			self.type(body, richtext)
		elif phrase.method is PasteMethod.PASTE:
			self.paste(body, richtext)
		else:
			self.altpaste(body, richtext)

	def send_with_keys(self, phrase, body, richtext):

		states = {'down': KeyState.PRESSED, 'up': KeyState.RELEASED}
		last_pos = 0
		for match in REKEY.finditer(body):
			# ~ time.sleep(0.1)
			if (match.start() - last_pos) > 0:
				fragment = body[last_pos:match.start()]
				self.send(phrase, fragment, richtext)
				time.sleep(0.05)
			last_pos = match.end()
			key = getattr(Key, match['key'], None)
			# ~ time.sleep(0.1)
			if match['state']:
				state = states[match['state']]
				if key:
					if (key is Key.KEY_TAB
							and self.settings.getbool('use_tab')
							and PLATFORM is not Platform.WAYLAND):
						window = Window.get_active()
						if state is KeyState.PRESSED:
							window.send_event(self.tab_down_event)
						else:
							window.send_event(self.tab_up_event)
					else:
						self.keyboard.keypress(key, state)
			else:
				if key:
					if (key is Key.KEY_TAB
							and self.settings.getbool('use_tab')
							and PLATFORM is not Platform.WAYLAND):
						window = Window.get_active()
						window.send_event(self.tab_down_event)
						window.send_event(self.tab_up_event)
					else:
						self.keyboard.keypress(key)
			time.sleep(0.05)
		if last_pos < len(body):
			# ~ time.sleep(0.1)
			self.send(phrase, body[last_pos:], richtext)
			time.sleep(0.05)

	def move_caret(self, string):

		count = string.count(CARET)
		self.caret_pos = []
		caret_pos = 0
		start = string.find(CARET)
		for i in range(count):
			if i is 0:
				temp_string = string.replace(CARET, '')
				caret_pos = len(temp_string) - start
				string = string.replace(CARET, '', 1)
			else:
				temp_string = string.replace(CARET, '', 1)
				next_pos = string.find(CARET)
				self.caret_pos.append(next_pos - start)
				start = next_pos
				string = temp_string
		time.sleep(0.05)
		for i in range(caret_pos):
			self.keyboard.keypress(Key.KEY_LEFT)

	def cycle_caret(self, steps, window):

		for i in range(steps):
			# ~ self.keyboard.keypress(Key.KEY_RIGHT)
			window.send_event(self.right_down_event)
			window.send_event(self.right_up_event)

	def close(self):

		if PLATFORM is Platform.WAYLAND:
			self.pointer.close()
		self.keyboard.close()
		self.enqueue(None)

	def toggle_pause(self):

		self.pause = not self.pause
