#!/usr/bin/env python3

import threading
import queue
import collections
import shlex
import subprocess
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from . import shared, CONSTANTS


class Service(threading.Thread):

	def __init__(self):

		threading.Thread.__init__(self)
		self.daemon = True
		self.name = 'Listener service'
		self.queue = queue.Queue()
		self.input_stack = collections.deque(maxlen=128)
		shared.service_running = True
		self.method = (
			self.type_string, self.send_clipboard, self.send_clipboard_terminal)
		self.clear_stack = {CONSTANTS.XK.XK_Left, CONSTANTS.XK.XK_Right,
			CONSTANTS.XK.XK_Up, CONSTANTS.XK.XK_Down, CONSTANTS.XK.XK_Home,
			CONSTANTS.XK.XK_Page_Up, CONSTANTS.XK.XK_Page_Down, CONSTANTS.XK.XK_End}

		Gdk.threads_init()

		self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
		self.clipboard_content = ''
		self.store_clipboard()

	def enqueue(self, method, *args):

		self.queue.put_nowait((method, args))

	def run(self):

		while True:
			method, args = self.queue.get()

			if method is None:
				break

			try:
				method(*args)
			except Exception as exc:
				print("Error in the service main loop\n", exc)

			self.queue.task_done()

	def stop(self):

		self.enqueue(None)

	def listener(
		self, keypress, keysym, raw_key, modifiers, window_class, window_title):

		self.enqueue(self.update_window_info, window_class, window_title)
		self.enqueue(self.handle_event, keypress, keysym, raw_key, modifiers)

	def update_window_info(self, window_class, window_title):

		self.window_class = window_class
		self.window_title = window_title

	def handle_event(self, keypress, keysym, raw_key, modifiers):

		if keypress:
			char = shared.interface.keysym_to_char(keysym)
			raw_char = shared.interface.keysym_to_char(raw_key)
			if raw_char == shared.config['key_pause'][0]:
				mod_match = 0
				for mod in shared.config['key_pause'][1]:
					if modifiers[mod]:
						mod_match += 1
				if len(shared.config['key_pause'][1]) == mod_match:
					self.toggle_service_hotkey()
			if raw_char == shared.config['key_show_manager'][0]:
				mod_match = 0
				for mod in shared.config['key_show_manager'][1]:
					if modifiers[mod]:
						mod_match += 1
				if len(shared.config['key_show_manager'][1]) == mod_match:
					GLib.idle_add(shared.menu_show_manager.activate)
			if shared.service_running:
				if keysym in self.clear_stack:
					self.input_stack.clear()
				if keysym == CONSTANTS.XK.XK_BackSpace:
					if len(self.input_stack):
						self.input_stack.pop()
				if char and not (
					modifiers['<Alt>'] or
					modifiers['<Control>'] or
					modifiers['<Super>']):
					if char not in {' ', '\n', '\t'}:
						self.input_stack.append(char)
					else:
						phrase = self.match_phrase()
						if phrase:
							if ((not phrase['window_class'] and not phrase['window_title']) or
								self.match_class(phrase['window_class']) or
								self.match_title(phrase['window_title'])):
								if '$|' in phrase['body']:
									if phrase['command']:
										self.send_backspace(phrase['string'])
										output = self.get_output(phrase['body'])
										string, count = self.get_caret_pos(output)
										self.store_clipboard()
										string = string.replace('$C', self.clipboard_content)
										self.method[phrase['method']](string)
										self.move_caret(count)
									else:
										self.send_backspace(phrase['string'])
										string, count = self.get_caret_pos(phrase['body'])
										self.store_clipboard()
										string = string.replace('$C', self.clipboard_content)
										self.method[phrase['method']](string)
										self.move_caret(count)
								else:
									if phrase['command']:
										self.send_backspace(phrase['string'])
										output = self.get_output(phrase['body'])
										self.store_clipboard()
										output = output.replace('$C', self.clipboard_content)
										self.method[phrase['method']](output)

									else:
										self.send_backspace(phrase['string'])
										self.store_clipboard()
										string = phrase['body'].replace(
											'$C', self.clipboard_content)
										self.method[phrase['method']](string)
							self.input_stack.clear()

	def match_phrase(self):

		for phrase in shared.phrases:
			if (''.join(self.input_stack).endswith(phrase['string']) and
				phrase['string'] != ''):
				return phrase

	def get_output(self, command):

		output = subprocess.run(shlex.split(command),
								stdout=subprocess.PIPE,
								timeout=1,
								universal_newlines=True).stdout
		return output.strip('\n')

	def send_backspace(self, string):

		keycode, state = shared.interface.keysym_to_keycode(
			CONSTANTS.XK.XK_BackSpace)
		shared.interface.grab_keyboard()
		for char in string:
			shared.interface.send_key_press(keycode, state)
			shared.interface.send_key_release(keycode, state)
		shared.interface.send_key_press(keycode, state)
		shared.interface.send_key_release(keycode, state)
		shared.interface.ungrab_keyboard()

	def type_string(self, string):

		shared.interface.grab_keyboard()
		for char in string:
			keysym = shared.interface.char_to_keysym(char)
			if keysym > 0:
				keycode, state = shared.interface.keysym_to_keycode(keysym)
				shared.interface.send_key_press(keycode, state)
				shared.interface.send_key_release(keycode, state)
		shared.interface.ungrab_keyboard()

	def send_clipboard(self, string):

		keycode, state = shared.interface.keysym_to_keycode(CONSTANTS.XK.XK_v)
		state |= 4    # X.ControlMask

		self.store_clipboard()
		Gdk.threads_enter()
		self.clipboard.set_text(string, -1)
		self.clipboard.store()
		Gdk.threads_leave()
		time.sleep(0.2)

		shared.interface.grab_keyboard()
		shared.interface.send_key_press(keycode, state)
		shared.interface.send_key_release(keycode, state)
		shared.interface.ungrab_keyboard()

		time.sleep(0.2)
		Gdk.threads_enter()
		self.clipboard.set_text(self.clipboard_content, -1)
		self.clipboard.store()
		Gdk.threads_leave()

	def send_clipboard_terminal(self, string):

		keycode, state = shared.interface.keysym_to_keycode(CONSTANTS.XK.XK_v)
		state |= 4 | 1    # X.ControlMask | X.ShiftMask

		self.store_clipboard()
		Gdk.threads_enter()
		self.clipboard.set_text(string, -1)
		self.clipboard.store()
		Gdk.threads_leave()
		time.sleep(0.2)

		shared.interface.grab_keyboard()
		shared.interface.send_key_press(keycode, state)
		shared.interface.send_key_release(keycode, state)
		shared.interface.ungrab_keyboard()

		time.sleep(0.2)
		Gdk.threads_enter()
		self.clipboard.set_text(self.clipboard_content, -1)
		self.clipboard.store()
		Gdk.threads_leave()

	def store_clipboard(self):

		Gdk.threads_enter()
		content = self.clipboard.wait_for_text()
		self.clipboard_content = '' if content is None else content
		Gdk.threads_leave()

	def get_caret_pos(self, string):

		count = len(string) - string.find('$|') - 2
		cleared_string = string.replace('$|', '')
		return cleared_string, count

	def move_caret(self, count):

		keycode, state = shared.interface.keysym_to_keycode(CONSTANTS.XK.XK_Left)
		shared.interface.grab_keyboard()
		for i in range(count):
			shared.interface.send_key_press(keycode, state)
			shared.interface.send_key_release(keycode, state)
		shared.interface.ungrab_keyboard()

	def match_class(self, window_class):

		if window_class is None:
			return False
		if window_class == self.window_class:
			return True
		else:
			return False

	def match_title(self, window_title):

		if window_title is None:
			return False
		if window_title in self.window_title:
			return True
		else:
			return False

	def toggle_service(self):

		shared.service_running = not shared.service_running

	def toggle_service_hotkey(self):

		GLib.idle_add(shared.menu_toggle_service.set_active, shared.service_running)

	def grab_hotkeys(self):

		pause_keysym = shared.interface.char_to_keysym(shared.config['key_pause'][0])
		if pause_keysym:
			pause_keycode = shared.interface.keysym_to_keycode(pause_keysym)[0]
			pause_state = 0
			for mod in shared.config['key_pause'][1]:
				pause_state |= shared.interface.MODIFIER_MASK[mod]
		else:
			pause_keycode, pause_state = (0, 0)

		manager_keysym = shared.interface.char_to_keysym(
			shared.config['key_show_manager'][0])
		if manager_keysym:
			manager_keycode = shared.interface.keysym_to_keycode(manager_keysym)[0]
			manager_state = 0
			for mod in shared.config['key_show_manager'][1]:
				manager_state |= shared.interface.MODIFIER_MASK[mod]
		else:
			manager_keycode, manager_state = (0, 0)

		if pause_keycode:
			shared.interface.grab_key(pause_keycode, pause_state)
		if manager_keycode:
			shared.interface.grab_key(manager_keycode, manager_state)

		self.grabbed_keys = ((pause_keycode, pause_state),
							(manager_keycode, manager_state))

	def ungrab_hotkeys(self):

		for key in self.grabbed_keys:
			shared.interface.ungrab_key(*key)
