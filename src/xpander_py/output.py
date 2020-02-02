import sys
import time
import re
from markupsafe import escape_silent
from macpy import Window, Pointer
from macpy import Key, KeyState, KeyboardEvent, PointerEventButton
from macpy import PLATFORM, Platform
from klembord import Selection
from .phrase import PasteMethod
if sys.platform.startswith('win32'):
	from ctypes import windll, c_void_p, c_uint, c_int, c_bool, POINTER, byref


KEYMATCH = re.compile(r'\${{(?P<key>[A-Z]+):?(?P<state>UP|DOWN)?}}\$')
KEYSPLIT = re.compile(r'(\${{[A-Z]+:?(?:UP|DOWN)?}}\$)')


LOCKS = {
	'NUMLOCK': False,
	'CAPSLOCK': False,
	'SCROLLLOCK': False,
}
MODS = {
	'SHIFT': False,
	'ALTGR': False,
	'CTRL': False,
	'ALT': False,
	'META': False,
}


class Output(object):
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
		windll.user32.GetWindowThreadProcessId.argtypes = (c_void_p, POINTER(c_uint))
		windll.user32.GetWindowThreadProcessId.restype = c_uint

	def __init__(self, keyboard):
		super().__init__()
		self.clipboard = Selection()
		if sys.platform.startswith('linux'):
			self.primary = Selection('PRIMARY')
		self.keyboard = keyboard
		if PLATFORM is Platform.WAYLAND:
			self.pointer = Pointer()

	def paste(self, text, richText):
		# time.sleep(0.05)
		content = self.clipboard.get_with_rich_text()
		time.sleep(0.05)
		if richText:
			self.clipboard.set_with_rich_text(text, richText)
		else:
			# self.clipboard.set_text(text)
			self.clipboard.set_with_rich_text(text, str(escape_silent(text)))
		time.sleep(0.05)
		self.keyboard.keypress(Key.KEY_CTRL, state=KeyState.PRESSED)
		self.keyboard.keypress(Key.KEY_V)
		self.keyboard.keypress(Key.KEY_CTRL, state=KeyState.RELEASED)
		time.sleep(0.3)
		self.clipboard.set_with_rich_text(*(str(s) for s in content))

	def altPaste(self, text, richText):
		if sys.platform.startswith('linux'):
			time.sleep(0.05)
			content = self.primary.get_with_rich_text()
			time.sleep(0.05)
			if richText:
				self.primary.set_with_rich_text(text, richText)
			else:
				self.primary.set_text(text)
			time.sleep(0.05)
			if PLATFORM is not Platform.WAYLAND:
				window = Window.get_active()
				x, y = window.size
				window.send_event(PointerEventButton(
					x // 2,
					y // 2,
					Key.BTN_MIDDLE,
					KeyState.PRESSED,
					MODS,
				))
				window.send_event(PointerEventButton(
					x // 2,
					y // 2,
					Key.BTN_MIDDLE,
					KeyState.RELEASED,
					MODS,
				))
			else:
				self.pointer.click(Key.BTN_MIDDLE)
			time.sleep(0.05)
			self.primary.set_with_rich_text(*content)
		else:
			content = self.clipboard.get_with_rich_text()
			if richText:
				self.clipboard.set_with_rich_text(text, richText)
			else:
				self.clipboard.set_text(text)
			wnd = windll.user32.GetForegroundWindow()
			tId = windll.user32.GetWindowThreadProcessId(wnd, byref(c_uint(0)))
			cId = windll.kernel32.GetCurrentThreadId()
			windll.user32.AttachThreadInput(cId, tId, True)
			hwnd = windll.user32.GetFocus()
			windll.user32.AttachThreadInput(cId, tId, False)
			# WM_PASTE
			windll.user32.PostMessageW(hwnd, 0x0302, 0, 0)
			time.sleep(0.1)
			self.clipboard.set_with_rich_text(*(str(s) for s in content))

	def send(self, method, text, richText):
		def output(method, text, richText):
			if method is PasteMethod.TYPE:
				self.keyboard.type(text)
			elif method is PasteMethod.PASTE:
				self.paste(text, richText)
			else:
				self.altPaste(text, richText)

		if KEYSPLIT.search(text):
			textList = KEYSPLIT.split(text)
			richTextList = KEYSPLIT.split(richText) \
				if richText else KEYSPLIT.split(text)
			for fragment in zip(textList, richTextList):
				match = KEYMATCH.match(fragment[0])
				if match:
					try:
						key = getattr(Key, 'KEY_{}'.format(match.group('key')))
					except AttributeError:
						break
					state = None
					if match.group('state'):
						state = KeyState.PRESSED \
							if match.group('state') == 'DOWN' \
								else KeyState.RELEASED
					self.keyboard.keypress(key, state)
					if sys.platform.startswith('linux'):
						time.sleep(0.01)
				else:
					output(method, fragment[0], fragment[1])
				time.sleep(0.01)
		else:
			output(method, text, richText)

	def backspace(self, amount):
		for i in range(amount):
			self.keyboard.keypress(Key.KEY_BACKSPACE)
			time.sleep(0.05)

	def backward(self, amount):
		for i in range(amount):
			self.keyboard.keypress(Key.KEY_LEFT)
			time.sleep(0.05)

	def forward(self, amount):
		for i in range(amount):
			self.keyboard.keypress(Key.KEY_RIGHT)
			time.sleep(0.05)

	def tab(self):
		# if PLATFORM is Platform.X11:
		window = Window.get_active()
		window.send_event(KeyboardEvent(
			Key.KEY_TAB,
			KeyState.PRESSED,
			None,
			MODS,
			LOCKS,
		))
		window.send_event(KeyboardEvent(
			Key.KEY_TAB,
			KeyState.RELEASED,
			None,
			MODS,
			LOCKS,
		))
		# elif PLATFORM is Platform.WINDOWS:
			# self.keyboard.keypress(Key.KEY_TAB)
			# self.keyboard.type('\t')

	def quit(self):
		if PLATFORM is Platform.WAYLAND:
			self.pointer.close()
