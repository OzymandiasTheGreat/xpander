#!/usr/bin/env python3

import time
from pathlib import Path
from enum import Flag, IntEnum
from threading import Thread
from multiprocessing import AuthenticationError
from multiprocessing.connection import Listener, Client, wait as conn_wait
from collections import namedtuple
import subprocess
import sys
import traceback
import inspect


ADDR = ('127.0.0.1', 60777)
PASSWORD = b'BIENVENUE CHEZ MOI'


class ClientType(Flag):

	CONTROLLER = 1
	EDITOR = 2

class MsgType(IntEnum):

	EXIT = 0
	STATUS = 1
	PAUSE = 2
	EDITOR = 3
	ADD = 4
	EDIT = 5
	HOTKEY = 6
	MOVE = 7
	DEL = 8
	SETTINGS = 9

MSG = namedtuple('MSG', ('type', 'data'))


class Server(Thread):

	def __init__(self, service, manager, settings):

		super().__init__(name='xpanderd server', daemon=True)
		self.service = service
		self.manager = manager
		self.settings = settings
		self.listener = Listener(ADDR, None, True, PASSWORD)
		self.receiver = Thread(target=self.receive, name='xpanderd receiver')
		self.stop = False
		self.connections = {}
		self.editor = None

	def start(self):

		self.receiver.start()
		super().start()

	def run(self):

		while not self.stop:
			try:
				conn = self.listener.accept()
				conn.poll(None)
				client = conn.recv()
				if type(client[0]) is ClientType and type(client[1]) is str:
					self.connections[client] = conn
				else:
					conn.close()
			except AuthenticationError:
				pass

	def send(self, client_type, msg):

		for client, conn in tuple(self.connections.items()):
			if client[0] & client_type:
				try:
					conn.send(msg)
				except BrokenPipeError:
					del self.connections[client]

	def broadcast(self, msg):

		for client, conn in tuple(self.connections.items()):
			try:
				conn.send(msg)
			except BrokenPipeError:
				del self.connections[client]

	def receive(self):

		while not self.stop:
			for conn in conn_wait(self.connections.values(), 0.5):
				try:
					msg = conn.recv()
					self.process_msg(msg, conn)
				except (EOFError, ConnectionResetError):
					pass
			time.sleep(0.5)

	def close(self):

		self.broadcast(MSG(type=MsgType.EXIT, data=None))
		self.stop = True

	def process_msg(self, msg, conn):

		if msg.type:
			if msg.type is MsgType.STATUS:
				conn.send(MSG(MsgType.STATUS, self.service.pause))
			elif msg.type is MsgType.PAUSE:
				self.toggle_pause(conn)
			elif msg.type is MsgType.EDITOR:
				self.run_editor()
			elif msg.type is MsgType.ADD:
				phrase = self.manager.added(msg.data)
				self.service.register_phrase(phrase)
			elif msg.type in {MsgType.EDIT, MsgType.HOTKEY}:
				if msg.type is MsgType.EDIT:
					phrase = self.manager.edited(*msg.data)
				else:
					phrase = self.manager.hotkey_set(*msg.data)
				self.service.unregister_phrase(phrase)
				self.service.register_phrase(phrase)
			elif msg.type is MsgType.MOVE:
				self.manager.moved(*msg.data)
			elif msg.type is MsgType.DEL:
				phrase = self.manager.deleted(msg.data)
				self.service.unregister_phrase(phrase)
			elif msg.type is MsgType.SETTINGS:
				self.settings.reload()
				self.manager.reload_phrases()
				self.service.unregister_hotkeys()
				self.service.register_hotkeys()
				for phrase in tuple(self.service.phrases.values()):
					self.service.unregister_phrase(phrase)
				for phrase in self.manager.phrases.values():
					self.service.register_phrase(phrase)
				self.broadcast(MSG(MsgType.SETTINGS, None))
		else:
			self.service.close()
			self.close()

	def run_editor(self):

		def runner():

			xpander_gui = getattr(self, 'daemon_path', None)
			if xpander_gui:
				xpander_gui /= 'xpander-gui'
			if sys.platform.startswith('win32'):
				if xpander_gui.exists():
					subprocess.run(['python3', str(xpander_gui)])
				else:
					try:
						subprocess.run([str(xpander_gui.with_suffix('.exe'))])
					except FileNotFoundError:
						try:
							subprocess.run(['xpander-gui.exe'])
						except FileNotFoundError:
							print("Can't find Phrase Editor")
			else:
				if xpander_gui.exists():
					subprocess.run([str(xpander_gui)])
				else:
					try:
						subprocess.run(['xpander-gui'])
					except FileNotFoundError:
						print("Can't find Phrase Editor")

		if self.editor and self.editor.is_alive():
			self.send(ClientType.EDITOR, MSG(MsgType.EXIT, None))
		else:
			self.editor = Thread(target=runner, name='xpander editor thread')
			self.editor.start()

	def toggle_pause(self, conn):

		self.service.toggle_pause()
		if conn:
			conn.send(MSG(MsgType.PAUSE, self.service.pause))
		self.send(
			ClientType.CONTROLLER,
			MSG(MsgType.STATUS, self.service.pause))


class BaseClient(Thread):

	def __init__(self, name, client):

		super().__init__(name=name)
		self.client = client
		self.conn = Client(ADDR, None, PASSWORD)
		self.conn.send(client)
		self.stop = False

	def run(self):

		while not self.stop:
			if self.conn.poll(0.5):
				try:
					msg = self.conn.recv()
					self.process_msg(msg)
				except EOFError:
					self.conn.close()
					self.close()
					break

	def close(self):

		self.stop = True

	def send(self, msg):

		self.conn.send(msg)

	def process_msg(self, msg):

		if msg.type:
			pass
		else:
			self.close()
