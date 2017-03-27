#!/usr/bin/env python3

import os
import shutil
import json
from . import shared


class Config(object):

	def __init__(self):

		self.config_path = os.path.join(shared.config['config_dir'], 'xpander.json')

		try:
			self.read_config()
		except FileNotFoundError as not_found:
			print('No user configuration\n', not_found)
			self.write_config()

	def write_config(self):

		with open(self.config_path, 'w') as config:
			config.write(json.dumps(shared.config, ensure_ascii=False, indent='\t'))

	def read_config(self):

		with open(self.config_path) as config:
			shared.config = json.loads(config.read())

	def edit(self, key, value):

		if key not in shared.config:
			raise KeyError('Configuration key does not exist')
		shared.config[key] = value


class Phrases(object):

	def __init__(self):

		shared.phrases = []
		shared.phrase_paths = {}

		if not os.path.isdir(shared.config['phrases_dir']):
			source = os.path.join(os.path.dirname(__file__), 'Examples')
			shutil.copytree(
				source, os.path.join(shared.config['phrases_dir'], 'Examples'))
		self.load_phrases()

	def load_phrases(self, folder=shared.config['phrases_dir']):

		for entry in os.scandir(folder):
			if entry.is_dir():
				self.load_phrases(entry.path)
			else:
				path, ext = os.path.splitext(entry.path)
				if ext == '.json':
					with open(entry.path) as phrase_file:
						phrase = json.loads(phrase_file.read())
						phrase['name'] = os.path.basename(path)
						shared.phrases.append(phrase)
						shared.phrase_paths[phrase['name']] = os.path.relpath(
							os.path.dirname(entry.path), shared.config['phrases_dir'])

	def new_phrase(
		self, name, string, body, command, method, window_class, window_title, path):

		phrase = {}
		phrase['name'] = name
		phrase['string'] = string
		phrase['body'] = body
		phrase['command'] = command
		phrase['method'] = method
		phrase['window_class'] = window_class
		phrase['window_title'] = window_title

		shared.phrases.append(phrase)
		shared.phrase_paths[name] = path

		file_path = os.path.join(shared.config['phrases_dir'], path, name + '.json')
		dir_path = os.path.dirname(file_path)
		if not os.path.isdir(dir_path):
			os.mkdir(dir_path)
		written_phrase = phrase.copy()
		written_phrase.pop('name')
		with open(file_path, 'w') as phrase_file:
			phrase_file.write(
				json.dumps(written_phrase, ensure_ascii=False, indent='\t'))
		del written_phrase

	def edit_phrase(self, name, **kwargs):

		phrase = next((phrase for phrase in shared.phrases if phrase['name'] == name))
		for arg in kwargs:
			if arg not in phrase:
				raise KeyError('Phrase key does not exist')
			phrase[arg] = kwargs[arg]

		path = os.path.join(shared.config['phrases_dir'],
							shared.phrase_paths[name],
							name + '.json')
		written_phrase = phrase.copy()
		written_phrase.pop('name')
		with open(path, 'w') as phrase_file:
			phrase_file.write(
				json.dumps(written_phrase, ensure_ascii=False, indent='\t'))
		del written_phrase

	def move_phrase(self, old_name, new_name, path):

		phrase = next((
			phrase for phrase in shared.phrases if phrase['name'] == old_name))
		old_path = os.path.join(shared.config['phrases_dir'],
								shared.phrase_paths[old_name],
								old_name + '.json')
		new_path = os.path.join(
			shared.config['phrases_dir'], path, new_name + '.json')

		phrase['name'] = new_name
		shared.phrase_paths.pop(old_name)
		shared.phrase_paths[new_name] = path
		os.renames(old_path, new_path)

	def remove_phrase(self, name):

		phrase = next((phrase for phrase in shared.phrases if phrase['name'] == name))
		path = os.path.join(shared.config['phrases_dir'],
							shared.phrase_paths[name],
							name + '.json')
		dir_path = os.path.dirname(path)
		shared.phrases.remove(phrase)
		shared.phrase_paths.pop(name)
		os.remove(path)
		if not os.listdir(dir_path):
			os.rmdir(dir_path)
