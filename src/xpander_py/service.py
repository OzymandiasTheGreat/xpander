import time
from threading import Thread
from queue import Queue
from macpy import Keyboard, HotString, Key, Platform, PLATFORM, Window
from markupsafe import Markup
from .server import Server
from .fs import Settings
from .output import Output
from .phrase import PhraseType, PasteMethod
from .context import CONTEXT


class Service(Thread):

	def __init__(self):
		super().__init__(name='xpander service', daemon=True)
		self.pause = False
		self.phrases = {}
		self.queue = Queue()
		self.keyboard = Keyboard()
		self.output = Output(self.keyboard)
		self.tabKey = None
		self.pauseKey = None
		self.managerKey = None
		self.tabPos = []

		self.keyboard.install_keyboard_hook(lambda event: None)
		self.keyboard.init_hotkeys()

	def registerPhrase(self, phrase):
		if phrase.hotstring:
			triggers = phrase.triggers
			hotstring = self.keyboard.register_hotstring(
				phrase.hotstring, triggers, self.callback
			)
			self.phrases[hotstring] = phrase
		if phrase.hotkey:
			hotkey = self.keyboard.register_hotkey(
				phrase.hotkey[0], phrase.hotkey[1], self.callback
			)
			self.phrases[hotkey] = phrase
		if phrase.hotstring and phrase.hotkey:
			phrase.events = (hotstring, hotkey)
		elif phrase.hotstring:
			phrase.events = (hotstring, )
		elif phrase.hotkey:
			phrase.events = (hotkey, )

	def unregisterPhrase(self, phrase):
		for event in phrase.events:
			if (event) in self.phrases:
				del self.phrases[event]
			if isinstance(event, HotString):
				self.keyboard.unregister_hotstring(event)
			else:
				self.keyboard.unregister_hotkey(event)
		phrase.events = ()

	def registerHotkeys(self):
		if Settings.getBool('use_tab') and PLATFORM is not Platform.WAYLAND:
			self.tabKey = self.keyboard.register_hotkey(
				Key.KEY_TAB, (), self.callback
			)
		pauseKey = Settings.getHotkey('pause')
		if pauseKey:
			self.pauseKey = self.keyboard.register_hotkey(
				*pauseKey, self.callback
			)
		managerKey = Settings.getHotkey('manager')
		if managerKey:
			self.managerKey = self.keyboard.register_hotkey(
				*managerKey, self.callback
			)

	def unregisterHotkeys(self):
		if self.tabKey:
			self.keyboard.unregister_hotkey(self.tabKey)
		if self.pauseKey:
			self.keyboard.unregister_hotkey(self.pauseKey)
		if self.managerKey:
			self.keyboard.unregister_hotkey(self.managerKey)

	def callback(self, event):
		try:
			phrase = self.phrases[event]
			self.enqueue(phrase, event)
		except KeyError:
			if event == self.tabKey and PLATFORM is not Platform.WAYLAND:
				if self.tabPos:
					self.output.forward(self.tabPos.pop())
				else:
					self.output.tab()
			elif event == self.pauseKey:
				self.togglePause()
				Server.send({
					'type': 'main',
					'action': 'pause',
					'state': self.pause,
				})
			elif event == self.managerKey:
				Server.send({
					'type': 'manager',
					'action': 'show',
				})
			else:
				Server.sendError({
					'type': 'event',
					'message': 'Unrecognized event. Shouldn\'t happen!',
					'event': str(event),
				})

	def enqueue(self, phrase, event):
		self.queue.put_nowait((phrase, event))

	def run(self):

		while True:
			phrase, event = self.queue.get()
			if phrase is None:
				break
			if (
				not self.pause
				and self.filterWindows(phrase.wm_class, phrase.wm_title)
			):
				if phrase.hotstring:
					self.output.backspace(
						len(phrase.hotstring)
						+ (1 if getattr(event, 'trigger', '') else 0)
					)
				body = phrase.render(CONTEXT)
				keepTrig = Settings.getBool('keep_trig')
				if (keepTrig and getattr(event, 'trigger', '')):
					trigger = getattr(event, 'trigger', '')
				else:
					trigger = ''
				if '$+' in body and getattr(event, 'trigger', ''):
					body = body.replace('$+', '')
					trigger = getattr(event, 'trigger', '')
				elif '$-' in body:
					body = body.replace('$-', '')
					trigger = ''
				if 'class="xpander-fillin"' in body:
					Server.send({
						'type': 'phrase',
						'action': 'fillin',
						'body': body,
						'method': phrase.method.value,
						'trigger': trigger,
						'richText': True if phrase.type is PhraseType.RICHTEXT else False,  # noqa
					})
				else:
					if phrase.type is PhraseType.RICHTEXT:
						richText = body
						body = Markup(body).striptags()
					else:
						richText = None
					if '$|' in body:
						body, richText = self.getTabStops(body, richText)
					self.output.send(
						phrase.method,
						body + trigger,
						(richText + trigger) if richText else None,
					)
					if self.tabPos:
						self.output.backward(
							len(body + trigger) - self.tabPos.pop()
						)

	def fillin(self, phrase):
		time.sleep(0.05)
		if phrase['richText']:
			richText = phrase['body']
			plainText = Markup(phrase['body']).striptags()
		else:
			richText = None
			plainText = phrase['body']
		self.output.send(
			PasteMethod(phrase['method']),
			plainText + phrase['trigger'],
			(richText + phrase['trigger']) if richText else None,
		)
		if self.tabPos:
			self.output.backward(
				len(plainText + phrase['trigger']) - self.tabPos.pop()
			)

	def getTabStops(self, plainText, richText):
		self.tabPos = []
		richText = richText.replace('$|', '') if richText else None
		for i in range(plainText.count('$|')):
			self.tabPos.append(plainText.index('$|'))
			plainText = plainText.replace('$|', '', 1)
		self.tabPos.reverse()
		return plainText, richText

	def filterWindows(self, wm_class, wm_title):
		if PLATFORM is Platform.WAYLAND:
			return True
		expand = False
		window = Window.get_active()
		if window.wm_class in wm_class or not wm_class:
			expand = True
		if wm_title:
			if wm_title in window.title:
				expand = True
			else:
				expand = False
		return expand

	def quit(self):
		self.keyboard.close()
		self.output.quit()

	def togglePause(self, state=None):
		if state is not None:
			self.pause = state
			Server.send({'type': 'main', 'action': 'pause', 'state': state})
		else:
			self.pause = not self.pause
			Server.send({'type': 'main', 'action': 'pause', 'state': self.pause})
