#!/usr/bin/env python3

import sys
import json


class Server(object):
	listeners = {}

	@classmethod
	def start(cls):
		while True:
			msg = sys.stdin.readline()
			msg = json.loads(msg) if msg else {'type': 'none'}
			cls.callback(msg)

	@classmethod
	def callback(cls, msg):
		if msg['type'] in cls.listeners:
			for listener in cls.listeners[msg['type']]:
				listener(msg)
		else:
			cls.sendError({'type': 'unknownMessage', 'message': msg['type']})

	@classmethod
	def listen(cls, msgType, callback):
		if msgType in cls.listeners:
			cls.listeners[msgType].append(callback)
		else:
			cls.listeners[msgType] = [callback]

	@classmethod
	def send(cls, msg):
		print(json.dumps(msg))

	@classmethod
	def sendError(cls, msg):
		print(json.dumps(msg), file=sys.stderr)
