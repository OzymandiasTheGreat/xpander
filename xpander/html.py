#!/usr/bin/env python3

import os
import shutil
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import urlopen
from urllib.error import URLError
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf
from appdirs import user_cache_dir
from .version import appname, vendor


CACHE = user_cache_dir(appname, vendor)


class HTMLSerializer(HTMLParser):

	def __init__(self, textview):

		super().__init__()
		self.include_unknown = False
		self.textview = textview
		self.textbuffer = textview.get_buffer()
		self.tag_table = self.textbuffer.get_tag_table()
		self.pango_context = textview.get_pango_context()
		self.families = {family.get_name()
			for family in self.pango_context.list_families()}
		self.icon_theme = Gtk.IconTheme.get_default()

		self.simple_tags = {
			'b': 'bold',
			'i': 'italic',
			'u': 'underline',
			's': 'strikethrough',
			'sub': 'subscript',
			'sup': 'superscript',
			'em': 'italic',
			'strong': 'bold',
			'strike': 'strikethrough',
			'del': 'strikethrough'}
		self.complex_tags = {'span', 'code', 'p'}
		self.replace_map = {
			'\\xa0': ' ',
			'\\x00': ''}
		self.start_tags = {
			'bold': '<b>',
			'italic': '<i>',
			'underline': '<u>',
			'strikethrough': '<s>',
			'subscript': '<sub>',
			'superscript': '<sup>'}
		self.end_tags = {
			'bold': '</b>',
			'italic': '</i>',
			'underline': '</u>',
			'strikethrough': '</s>',
			'subscript': '</sub>',
			'superscript': '</sup>'}
		self.string = ''
		self.string_set = True
		self.tags = []
		self.open_tags = []
		self.count = []
		self.obj = chr(0xFFFC)
		self.reobj = re.compile(self.obj)

	def deserialize(self, html, include_unknown):

		self.include_unknown = include_unknown
		super().feed(html)
		self.close()

	def handle_starttag(self, tag, attrs):

		if tag in self.simple_tags:
			text_tag = {}
			text_tag['name'] = self.simple_tags[tag]
			text_tag['tag'] = tag
			text_tag['start'] = len(self.string)
			self.tags.append(text_tag)
			self.open_tags.append(text_tag)
			self.count.append(1)

		elif tag in self.complex_tags:
			found_tags = []
			font_family = None
			font_size = None
			unknown_styles = []
			unknown_attrs = []
			for attr, value in attrs:
				unknown_styles = []
				unknown_attrs = []
				if attr == 'style':
					style_attrs = value.split(';')
					for style_attr in style_attrs:
						style_attr = style_attr.strip()
						if style_attr.startswith('font-family:'):
							family_list = style_attr.replace(
								'font-family:', '').split(',')
							for family in family_list:
								family = family.strip('" ')
								if family == 'sans-serif':
									font_family = 'Sans'
									break
								elif family == 'serif':
									font_family = 'Serif'
									break
								elif family == 'monospace':
									font_family = 'Monospace'
									break
								elif family in self.families:
									font_family = family
									break
								else:
									font_family = 'Sans'
						elif style_attr.startswith('font-size:'):
							size = style_attr.replace(
								'font-size:', '').strip('" ')
							if size[-2:] == 'pt':
								font_size = size[:-2]
							elif size[-2:] == 'px':
								font_size = str(float(size[:-2]) / (96 / 72))
							else:
								font_size = ''
						elif style_attr.startswith('font-style:'):
							style = style_attr.replace(
								'font-style:', '').strip('" ')
							if style == 'italic' or style == 'oblique':
								style_tag = {}
								style_tag['name'] = 'italic'
								style_tag['tag'] = tag
								style_tag['start'] = len(self.string)
								found_tags.append(style_tag)
						elif style_attr.startswith('font-weight:'):
							weight = style_attr.replace(
								'font-weight:', '').strip('" ')
							if weight.isdigit() and int(weight) >= 600:
								bold = True
							elif weight == 'bold' or weight == 'bolder':
								bold = True
							else:
								bold = False
							if bold:
								weight_tag = {}
								weight_tag['name'] = 'bold'
								weight_tag['tag'] = tag
								weight_tag['start'] = len(self.string)
								found_tags.append(weight_tag)
						elif style_attr.startswith('text-decoration'):
							if 'underline' in style_attr:
								under_tag = {}
								under_tag['name'] = 'underline'
								under_tag['tag'] = tag
								under_tag['start'] = len(self.string)
								found_tags.append(under_tag)
							if 'line-through' in style_attr:
								strike_tag = {}
								strike_tag['name'] = 'strikethrough'
								strike_tag['tag'] = tag
								strike_tag['start'] = len(self.string)
								found_tags.append(strike_tag)
						elif style_attr.startswith('color:'):
							color = style_attr.replace(
								'color:', '').strip('" ')
							if color.startswith('rgb('):
								name = 'foreground=' + color
								foreground_tag = {}
								foreground_tag['name'] = name
								foreground_tag['tag'] = tag
								foreground_tag['start'] = len(self.string)
								rgba = Gdk.RGBA()
								rgba.parse(color)
								if (rgba.red != 0 and rgba.green != 0
									and rgba.blue != 0):
									if not self.tag_table.lookup(name):
										self.textbuffer.create_tag(
											name, foreground_rgba=rgba)
									found_tags.append(foreground_tag)
						elif style_attr.startswith('background-color:'):
							color = style_attr.replace(
								'background-color:', '').strip('" ')
							if color.startswith('rgb('):
								name = 'background=' + color
								background_tag = {}
								background_tag['name'] = name
								background_tag['tag'] = tag
								background_tag['start'] = len(self.string)
								rgba = Gdk.RGBA()
								rgba.parse(color)
								if (rgba.red != 1 and rgba.green != 1
									and rgba.blue != 1):
									if not self.tag_table.lookup(name):
										self.textbuffer.create_tag(
											name, background_rgba=rgba)
									found_tags.append(background_tag)
						elif style_attr.startswith('text-align:'):
							name = None
							if style_attr.endswith('left'):
								name = 'text-align: left'
							elif style_attr.endswith('center'):
								name = 'text-align: center'
							elif style_attr.endswith('right'):
								name = 'text-align: right'
							elif style_attr.endswith('justify'):
								name = 'text-align: justify'
							if name:
								align_tag = {}
								align_tag['name'] = name
								align_tag['tag'] = tag
								align_tag['start'] = len(self.string)
								found_tags.append(align_tag)
						else:
							unknown_styles.append(style_attr + ';')
						if font_family and font_size is not None:
							font_tag = {}
							font = font_family + ' ' + font_size
							font_tag['name'] = 'font=' + font
							font_tag['tag'] = tag
							font_tag['start'] = len(self.string)
							if not self.tag_table.lookup(font_tag['name']):
								self.textbuffer.create_tag(
									font_tag['name'], font=font)
								bold = self.tag_table.lookup('bold')
								italic = self.tag_table.lookup('italic')
								tag_table_size = self.tag_table.get_size()
								bold.set_priority(tag_table_size - 1)
								italic.set_priority(tag_table_size - 2)
							found_tags.append(font_tag)
				else:
					unknown_attrs.append('{0}="{1}"'.format(attr, value))
			if found_tags:
				self.tags.extend(found_tags)
				self.open_tags.extend(found_tags)
				self.count.append(len(found_tags))
			if unknown_styles and self.include_unknown:
				style_tag = {}
				style_tag['name'] = 'private'
				style_tag['tag'] = tag
				style_tag['start'] = len(self.string)
				self.string += '<{0} style="{1}">'.format(
					tag, ' '.join(unknown_styles))
				style_tag['end'] = len(self.string)
				self.tags.append(style_tag)
				self.open_tags.append(style_tag)
				if self.count:
					self.count[-1] += 1
				else:
					self.count.append(1)
			if unknown_attrs and self.include_unknown:
				unknown_tag = {}
				unknown_tag['name'] = 'private'
				unknown_tag['tag'] = tag
				unknown_tag['start'] = len(self.string)
				self.string += '<{0} {1}>'.format(tag, ' '.join(unknown_attrs))
				unknown_tag['end'] = len(self.string)
				self.tags.append(unknown_tag)
				self.open_tags.append(unknown_tag)
				if self.count:
					self.count[-1] += 1
				else:
					self.count.append(1)
			if tag == 'p':
				self.string += '\n'

		elif tag == 'a':
			for attr, value in attrs:
				if attr == 'href':
					link_tag = {}
					link_tag['name'] = None
					link_tag['tag'] = tag
					link_tag['start'] = len(self.string)
					link_tag['href'] = value.strip('" ')
					self.tags.append(link_tag)
					self.open_tags.append(link_tag)
					self.count.append(1)

		elif tag == 'img':
			for attr, value in attrs:
				src = value.strip('" ')
				if attr == 'src':
					if not src.startswith('file://'):
						try:
							with urlopen(src, timeout=1) as response:
								file_name = os.path.basename(urlsplit(src).path)
								path = os.path.join(CACHE, file_name)
								with open(path, 'wb') as fd:
									shutil.copyfileobj(response, fd)
							src = path
						except URLError:
							src = 'MISSING'
					else:
						src = src.replace('file://', '')
						if not os.path.isfile(src):
							src = 'MISSING'
						else:
							if os.path.dirname(src) != CACHE:
								try:
									src = shutil.copy(src, CACHE)
								except shutil.SameFileError:
									pass
					if self.open_tags and self.open_tags[-1]['tag'] == 'a':
						self.open_tags[-1]['image'] = src
						self.string += self.obj
					else:
						img_tag = {}
						img_tag['name'] = None
						img_tag['tag'] = tag
						img_tag['start'] = len(self.string)
						img_tag['src'] = src
						self.string += self.obj
						self.tags.append(img_tag)
						self.open_tags.append(img_tag)
						self.count.append(1)

		elif tag == 'br':
			self.string += '\n'

		elif tag == 'head':
			self.string_set = False

		elif (tag != 'html' and tag != 'body' and self.string_set
			and self.include_unknown):
			unknown_attrs = []
			for attr, value in attrs:
				unknown_attrs.append('{0}="{1}"'.format(attr, value))
			unknown_tag = {}
			unknown_tag['name'] = 'private'
			unknown_tag['tag'] = tag
			unknown_tag['start'] = len(self.string)
			self.string += '<{0} {1}>'.format(tag, ' '.join(unknown_attrs))
			unknown_tag['end'] = len(self.string)
			self.tags.append(unknown_tag)
			self.open_tags.append(unknown_tag)
			self.count.append(1)

	def handle_data(self, data):

		if self.string_set:
			data = data.strip('\n\t').replace('\n', ' ')
			for text_tag in self.open_tags:
				if 'start' not in text_tag:
					text_tag['start'] = len(self.string)
				if 'href' in text_tag:
					text_tag['title'] = data
					data = self.obj
			for char, sub in self.replace_map.items():
				data = data.replace(char, sub)
			self.string += data

	def handle_endtag(self, tag):

		for text_tag in reversed(self.open_tags):
			if text_tag['tag'] == tag:
				if self.count[-1]:
					if 'end' in text_tag:
						unknown_tag = {}
						unknown_tag['name'] = 'private'
						unknown_tag['tag'] = tag
						unknown_tag['start'] = len(self.string)
						self.string += '</{0}>'.format(tag)
						unknown_tag['end'] = len(self.string)
						self.tags.append(unknown_tag)
					else:
						text_tag['end'] = len(self.string)
					self.open_tags.remove(text_tag)
					self.count[-1] -= 1
					if not self.count[-1]:
						self.count.pop(-1)
						break
		if tag == 'p':
			if not self.string.endswith('\n'):
				self.string += '\n'
		elif tag == 'head':
			self.string_set = True

	def close(self):

		super().close()
		cursor = self.textbuffer.get_insert()
		text_iter = self.textbuffer.get_iter_at_mark(cursor)
		offset = text_iter.get_offset()
		obj_pos = [match.start()
			for match in self.reobj.finditer(self.string)]
		self.string = self.string.replace(self.obj, '')
		self.textbuffer.insert(text_iter, self.string, -1)

		for index, obj_tag in enumerate(tag for tag in self.tags
			if tag['name'] is None and ('href' in tag or 'src' in tag)):
			pos = obj_pos[index] + offset
			obj_iter = self.textbuffer.get_iter_at_offset(pos)
			if 'href' in obj_tag:
				anchor = self.textbuffer.create_child_anchor(obj_iter)
				if 'image' in obj_tag:
					link_button = Gtk.LinkButton.new_with_label(
						obj_tag['href'], '')
					if obj_tag['image'] != 'MISSING':
						image = Gtk.Image.new_from_file(obj_tag['image'])
					else:
						image = Gtk.Image.new_from_icon_name('image-missing', 4)
					link_button.set_image(image)
					link_button.props.always_show_image = True
				else:
					link_button = Gtk.LinkButton.new_with_label(
						obj_tag['href'], obj_tag['title'])
				link_button.get_style_context().add_class('text_link')
				link_button.show()
				self.textview.add_child_at_anchor(link_button, anchor)
			elif 'src' in obj_tag:
				if obj_tag['src'] != 'MISSING':
					pixbuf = GdkPixbuf.Pixbuf.new_from_file(obj_tag['src'])
				else:
					pixbuf = self.icon_theme.load_icon('image-missing', 16, 0)
				pixbuf.path = obj_tag['src']
				self.textbuffer.insert_pixbuf(obj_iter, pixbuf)

		for text_tag in (tag for tag in self.tags if tag['name'] is not None):
			start = self.textbuffer.get_iter_at_offset(
				text_tag['start'] + offset)
			end = self.textbuffer.get_iter_at_offset(text_tag['end'] + offset)
			self.textbuffer.apply_tag_by_name(text_tag['name'], start, end)

		self.string = ''
		self.tags.clear()

	def serialize(self, start, end, ashtml=True):

		html_list = []
		open_tags = set()
		start_tags = start.get_tags()
		for tag in start_tags:
			if tag.props.name in self.simple_tags.values():
				html_list.append(self.start_tags[tag.props.name])
			elif tag.props.name.startswith('font='):
				family = tag.props.family
				size = str(tag.props.size / 1024)
				html_list.append(
				'<span style="font-family: {0}; font-size: {1}pt">'.format(
				family, size))
			elif tag.props.name.startswith('foreground='):
				fg_color = tag.props.name.replace('foreground=', '')
				html_list.append(
					'<span style="color: {0}">'.format(fg_color))
			elif tag.props.name.startswith('background='):
				bg_color = tag.props.name.replace('background=', '')
				html_list.append(
					'<span style="background-color: {0}">'.format(bg_color))
			elif tag.props.name.startswith('text-align: '):
				html_list.append('<p style="{0}">'.format(tag.props.name))
		open_tags.update(start_tags)
		while True:
			next_iter = start.copy()
			next_iter.forward_to_tag_toggle(None)
			next_iter = (next_iter if next_iter.compare(end) < 0 else end)
			data = self.textbuffer.get_slice(start, next_iter, True)
			if self.obj in data:
				obj_tags = []
				obj_list = []
				obj_iter = start.copy()
				while True:
					obj_match = obj_iter.forward_search(
						self.obj, Gtk.TextSearchFlags.VISIBLE_ONLY, next_iter)
					if obj_match:
						obj_list.append(obj_match[0].get_child_anchor()
							if obj_match[0].get_child_anchor()
							else obj_match[0].get_pixbuf())
						obj_iter = obj_match[0]
						obj_iter.forward_char()
					else:
						break
				for found_obj in obj_list:
					if type(found_obj) is GdkPixbuf.Pixbuf:
						uri = 'file://' + found_obj.path
						obj_tag = '<img src="{0}">'.format(uri)
						obj_tags.append(obj_tag)
					else:
						widgets = found_obj.get_widgets()
						for widget in widgets:
							if type(widget) is Gtk.LinkButton:
								title = widget.get_label()
								if title == '':
									image = widget.get_image()
									path = (image.props.file
										if image.props.file else 'MISSING')
									uri = 'file://' + path
									title = '<img src="{0}">'.format(uri)
								url = widget.get_uri()
								obj_tags.append((url, title))
							if type(widget) is Gtk.Entry:
								text = widget.get_text()
								obj_tags.append(text)
							if type(widget) is Gtk.ScrolledWindow:
								textview = widget.get_child()
								textbuffer = textview.get_buffer()
								bounds = textbuffer.get_bounds()
								text = textbuffer.get_text(*bounds, False)
								obj_tags.append(text)
							if type(widget) is Gtk.ComboBoxText:
								obj_tags.append(widget.get_active_text())
							if type(widget) is Gtk.CheckButton:
								if widget.get_active():
									obj_tags.append(
										widget.get_label().strip('_'))
				substrings = (obj_tag if type(obj_tag) is str
					else '<a href="{0}">{1}</a>'.format(*obj_tag)
					for obj_tag in obj_tags)
				for substring in substrings:
					data = data.replace(self.obj, substring, 1)
			if ashtml:
				data = data.replace('\n', '<br>')
			html_list.append(data)
			start = next_iter
			end_tags = start.get_toggled_tags(False)
			for tag in end_tags:
				if tag.props.name in self.simple_tags.values():
					html_list.append(self.end_tags[tag.props.name])
				elif (tag.props.name.startswith('font=')
					or tag.props.name.startswith('foreground=')
					or tag.props.name.startswith('background=')):
					html_list.append('</span>')
				elif tag.props.name.startswith('text-align: '):
					html_list.append('</p>')
				open_tags.remove(tag)
			if start.compare(end) >= 0:
				for tag in open_tags:
					if tag.props.name in self.simple_tags.values():
						html_list.append(self.end_tags[tag.props.name])
					elif (tag.props.name.startswith('font=')
						or tag.props.name.startswith('foreground=')
						or tag.props.name.startswith('background=')):
						html_list.append('</span>')
					elif tag.props.name.startswith('text-align: '):
						html_list.append('</p>')
				open_tags.clear()
				break
			start_tags = start.get_toggled_tags(True)
			for tag in start_tags:
				if tag.props.name in self.simple_tags.values():
					html_list.append(self.start_tags[tag.props.name])
				elif tag.props.name.startswith('font='):
					family = tag.props.family
					size = str(tag.props.size / 1024)
					html_list.append(
					'<span style="font-family: {0}; font-size: {1}pt">'.format(
					family, size))
				elif tag.props.name.startswith('foreground='):
					fg_color = tag.props.name.replace('foreground=', '')
					html_list.append(
						'<span style="color: {0}">'.format(fg_color))
				elif tag.props.name.startswith('background='):
					bg_color = tag.props.name.replace('background=', '')
					html_list.append(
						'<span style="background-color: {0}">'.format(bg_color))
				elif tag.props.name.startswith('text-align: '):
					html_list.append('<p style="{0}">'.format(tag.props.name))
				open_tags.update(start_tags)
		return ''.join(html_list)


class PlainText(HTMLParser):

	def __init__(self):

		super().__init__()
		self.include_obj = False
		self.link = False
		self.string = ''
		self.string_set = True
		self.obj = chr(0xFFFC)
		self.replace_map = {
			'\\xa0': ' ',
			'\\x00': ''}

	def extract(self, html, include_obj):

		self.include_obj = include_obj
		super().feed(html)
		return self.close()

	def handle_starttag(self, tag, attrs):

		if tag == 'head':
			self.string_set = False
		elif tag == 'br':
			self.string += '\n'
		elif tag == 'a' and self.include_obj:
			self.string += self.obj
			self.link = True
		elif tag == 'img':
			if self.include_obj:
				if self.link:
					self.link = False
				else:
					self.string += self.obj
			else:
				for attr, value in attrs:
					if attr == 'alt':
						self.string += value

	def handle_data(self, data):

		if self.string_set:
			if self.link:
				self.link = False
			else:
				data = data.strip('\n\t').replace('\n', ' ')
				for char, sub in self.replace_map.items():
					data = data.replace(char, sub)
				self.string += data

	def handle_endtag(self, tag):

		if tag == 'head':
			self.string_set = True
		elif tag == 'p':
			self.string += '\n'

	def close(self):

		super().close()
		string = self.string
		self.string = ''

		return string
