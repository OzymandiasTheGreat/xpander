#!/usr/bin/env python3
import sys
import time
from xpander_py.server import Server
from xpander_py.fs import Settings, Manager
from xpander_py.service import Service
from xpander_py.util import listWindows
from xpander_py.context import PHRASES
if sys.platform.startswith('win32'):
	from macpy import WinWindow


Settings.load()
Settings.save()
manager = Manager()
manager.load()
service = Service()


def mainHandler(msg):
	if msg['action'] == 'exit':
		service.quit()
	elif msg['action'] == 'pause':
		service.togglePause(state=msg['state'])
	elif msg['action'] == 'focus' and sys.platform.startswith('win32'):
		time.sleep(0.1)
		WinWindow(int(msg['hwnd'])).activate()
		Server.send({'type': 'main', 'action': 'focus'})


def phraseHandler(msg):
	if msg['action'] == 'fillin':
		service.fillin(msg['phrase'])
	elif msg['action'] in {'edit', 'delete'}:
		if msg['path'] in manager.phrases:
			phrase = manager.phrases[msg['path']]
			del manager.phrases[msg['path']]
			if phrase.name in PHRASES:
				del PHRASES[phrase.name]
			service.unregisterPhrase(phrase)
		if msg['action'] == 'edit':
			phrase = manager.loadPhrase(
				msg['path'],
				Settings.getPath('phrase_dir').expanduser()
			)
			manager.phrases[msg['path']] = phrase
			PHRASES[phrase.name] = phrase
			service.registerPhrase(phrase)
	elif msg['action'] == 'reload':
		for phrase in manager.phrases.values():
			service.unregisterPhrase(phrase)
			if phrase.name in PHRASES:
				del PHRASES[phrase.name]
		manager.phrases = {}
		manager.load()
		for phrase in manager.phrases.values():
			service.registerPhrase(phrase)


def managerHandler(msg):
	if msg['action'] == 'listWindows':
		listWindows()


def settingsHandler(msg):
	if msg['action'] == 'reload':
		Settings.load()
		service.unregisterHotkeys()
		service.registerHotkeys()
		phraseHandler({
			'type': 'phrase',
			'action': 'reload',
		})


for filepath, phrase in manager.phrases.items():
	service.registerPhrase(phrase)
service.registerHotkeys()
service.start()
Server.listen('main', mainHandler)
Server.listen('phrase', phraseHandler)
Server.listen('manager', managerHandler)
Server.listen('settings', settingsHandler)
Server.start()
