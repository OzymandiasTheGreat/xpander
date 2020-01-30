#!/usr/bin/env python3

import re
import os
import shutil
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango, GdkPixbuf
from macpy import Key
from .html import HTMLSerializer, PlainText, CACHE
from .version import __version__, appname, vendor, author, author_email
from .version import homepage


FILLIN = re.compile(r'\$fill(?P<type>(?:entry)|(?:multi)|(?:choice)|(?:option))'
	+ r'(?:\:name=(?P<name>.+?))?(?:\:(?P<options>.+?))?\$')
OPTIONS = re.compile(r'(?:(?P<option>(?:default)|(?:width)|(?:height))\=)?'
	+ '(?P<value>[^\:]+)')
VALUE = re.compile(r'(?P<value>\d+)(?P<measure>(?:chr)|(?:px))')
LICENSE = """MIT License

Copyright (c) 2017 Tomas Ravinskas

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
IMAGESFILTER = Gtk.FileFilter()
IMAGESFILTER.add_pixbuf_formats()
IMAGESFILTER.set_name('Images')


class FillDialog(Gtk.Dialog):

	def __init__(self, string, richtext=False):

		Gtk.Dialog.__init__(
			self, 'Fill In', None, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				Gtk.STOCK_OK, Gtk.ResponseType.OK))
		self.set_default_response(Gtk.ResponseType.OK)
		self.hotkeys = Gtk.AccelGroup()
		self.add_accel_group(self.hotkeys)
		self.add_accelerator(
			'activate-default', self.hotkeys, Gdk.KEY_Return,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.connect('show', self.focus_first)
		color = self.get_style_context().get_background_color(0)
		color = 'rgb({0},{1},{2})'.format(
			int(color.red*255), int(color.green*255), int(color.blue*255))
		CSS = ('.bg_view > text {\n\t'
			+ 'background-color: {0};'.format(color) + '\n}'
			+ '.fillin_multi {\n\tpadding: 5px;\n}'
			)
		style_provider = Gtk.CssProvider()
		style_provider.load_from_data(CSS.encode())
		Gtk.StyleContext.add_provider_for_screen(
			Gdk.Screen.get_default(),
			style_provider,
			Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

		box = self.get_content_area()
		self.scrolled_window = Gtk.ScrolledWindow()
		box.pack_start(self.scrolled_window, True, True, 0)
		self.textview = Gtk.TextView()
		self.textview.get_style_context().add_class('bg_view')
		self.scrolled_window.add(self.textview)
		self.textview.set_editable(False)
		self.textview.set_cursor_visible(False)
		self.textview.connect_after('button-press-event', self.multi_focus_fix)
		self.pango_context = self.textview.get_pango_context()
		font_metrics = self.pango_context.get_metrics()
		self.char_width = round(
			font_metrics.get_approximate_char_width() / 1024)
		self.char_height = round(
			(font_metrics.get_ascent() + font_metrics.get_descent()) / 1024)
		self.textbuffer = self.textview.get_buffer()
		self.create_tags()

		self.string = string
		self.richtext = richtext
		self.html = HTMLSerializer(self.textview)
		self.plaintext = PlainText()
		self.fill_char = chr(0xFFFC)
		self.focus_widget = self

	def create_tags(self):

		self.textbuffer.create_tag('bold', weight=Pango.Weight.BOLD)
		self.textbuffer.create_tag('italic', style=Pango.Style.ITALIC)
		self.textbuffer.create_tag(
			'underline', underline=Pango.Underline.SINGLE)
		self.textbuffer.create_tag('strikethrough', strikethrough=True)
		self.textbuffer.create_tag('subscript', rise=-4 * 1024, scale=0.6)
		self.textbuffer.create_tag('superscript', rise=4 * 1024, scale=0.6)
		self.textbuffer.create_tag(
			'text-align: left', justification=Gtk.Justification.LEFT)
		self.textbuffer.create_tag(
			'text-align: center', justification=Gtk.Justification.CENTER)
		self.textbuffer.create_tag(
			'text-align: right', justification=Gtk.Justification.RIGHT)
		self.textbuffer.create_tag(
			'text-align: justify', justification=Gtk.Justification.FILL)
		self.private = self.textbuffer.create_tag(
			'private', editable=False, invisible=True)

	def run(self):

		fillins = []
		offset = 0
		if self.richtext:
			plainstring = self.plaintext.extract(self.string, True)
		else:
			plainstring = self.string
		fullstring = plainstring
		for match in FILLIN.finditer(plainstring):
			fillin = {
				'type': match['type'],
				'name': match['name'],
				'pos': match.start() - offset}
			offset += match.end() - match.start() - 1
			plainstring = FILLIN.sub('', plainstring, count=1)
			self.string = FILLIN.sub('', self.string, count=1)
			values = []
			for match in OPTIONS.finditer(match['options']):
				if match['option']:
					if match['option'] == 'default':
						fillin['default'] = match['value']
						values.append(match['value'])
					elif match['option'] == 'width':
						fillin['width'] = match['value']
					elif match['option'] == 'height':
						fillin['height'] = match['value']
				else:
					values.append(match['value'])
			fillin['values'] = values
			fillins.append(fillin)

		if self.richtext:
			self.textbuffer.set_text('', -1)
			self.html.deserialize(self.string, True)
		else:
			self.textbuffer.set_text(self.string, -1)

		entry_buffers = {}
		multi_buffers = {}
		choice_models = {}
		option_buttons = {}
		for fillin in fillins:
			# ~ text_iter = self.textbuffer.get_iter_at_offset(fillin['pos'])
			text_iter = self.textbuffer.get_start_iter()
			text_iter.forward_visible_cursor_positions(int(fillin['pos']))
			check_iter = text_iter.copy()
			check_iter.forward_char()
			if check_iter.has_tag(self.private):
				text_iter.forward_visible_cursor_position()
				# ~ text_iter.backward_char()
			anchor = self.textbuffer.create_child_anchor(text_iter)

			if fillin['type'] == 'entry':
				if fillin['name']:
					if fillin['name'] in entry_buffers:
						entry = Gtk.Entry.new_with_buffer(
							entry_buffers[fillin['name']])
					else:
						entry = Gtk.Entry()
						entry_buffers[fillin['name']] = entry.get_buffer()
					entry.set_placeholder_text(fillin['name'])
				else:
					entry = Gtk.Entry()
				if 'default' in fillin:
					entry.set_text(fillin['default'])
				if 'width' in fillin:
					match = VALUE.match(fillin['width'])
					if match:
						if match['measure'] == 'chr':
							entry.set_width_chars(int(match['value']))
						else:
							value = round(int(match['value']) / self.char_width)
							entry.set_width_chars(value)
				self.textview.add_child_at_anchor(entry, anchor)
				if fillins.index(fillin) is 0:
					self.focus_widget = entry

			if fillin['type'] == 'multi':
				if fillin['name']:
					if fillin['name'] in multi_buffers:
						multi = Gtk.TextView.new_with_buffer(
							multi_buffers[fillin['name']])
					else:
						multi = Gtk.TextView()
						multi_buffers[fillin['name']] = multi.get_buffer()
				else:
					multi = Gtk.TextView()
				multi.set_accepts_tab(False)
				multi.get_style_context().add_class('fillin_multi')
				# ~ multi.connect_after('button-press-event', self.multi_focus_fix)
				scrolled_window = Gtk.ScrolledWindow()
				scrolled_window.set_shadow_type(1)
				scrolled_window.add(multi)
				if 'default' in fillin:
					multi.get_buffer().set_text(fillin['default'], -1)
				if 'width' in fillin:
					match = VALUE.match(fillin['width'])
					if match:
						if match['measure'] == 'chr':
							width = (int(match['value']) * self.char_width) + 4
						else:
							width = int(match['value'])
					else:
						width = (20 * self.char_width) + 10
				else:
					width = (20 * self.char_width) + 10
				if 'height' in fillin:
					match = VALUE.match(fillin['height'])
					if match:
						if match['measure'] == 'chr':
							height = (
								(int(match['value']) * self.char_height) + 4)
						else:
							height = int(match['value'])
					else:
						height = (3 * self.char_height) + 10
				else:
					height = (3 * self.char_height) + 10
				scrolled_window.set_size_request(width, height)
				# ~ scrolled_window.connect_after(
					# ~ 'button-press-event', self.multi_focus_fix)
				self.textview.add_child_at_anchor(scrolled_window, anchor)
				if fillins.index(fillin) is 0:
					self.focus_widget = multi

			if fillin['type'] == 'choice':
				if fillin['name']:
					if fillin['name'] in choice_models:
						choice = Gtk.ComboBoxText()
						choice.set_model(choice_models[fillin['name']])
					else:
						choice = Gtk.ComboBoxText()
						choice_models[fillin['name']] = choice.get_model()
				else:
					choice = Gtk.ComboBoxText()
				if fillin['values']:
					for value in fillin['values']:
						choice.append(value, value)
				if 'default' in fillin:
					choice.set_active_id(fillin['default'])
				self.textview.add_child_at_anchor(choice, anchor)
				if fillins.index(fillin) is 0:
					self.focus_widget = choice

			if fillin['type'] == 'option':
				if fillin['values']:
					if fillin['name']:
						option = Gtk.CheckButton.new_with_label(
							fillin['values'][0])
						option_buttons[fillin['name']] = option
					else:
						option = Gtk.CheckButton.new_with_label(
							fillin['values'][0])
				else:
					if fillin['name']:
						if fillin['name'] in option_buttons:
							option = Gtk.CheckButton.new_with_label(
								option_buttons[fillin['name']].get_label())
						else:
							option = None
					else:
						option = None
				option.connect('key-press-event', self.toggle_option)
				if 'default' in fillin:
					option.set_active(True)
				if option:
					self.textview.add_child_at_anchor(option, anchor)
					if fillins.index(fillin) is 0:
						self.focus_widget = option

		self.show_all()
		minimum, natural = self.textview.get_preferred_size()
		extra_height = 0
		for line in fullstring.splitlines():
			if '$fillmulti' in line:
				extra_height += 45
			elif '$fillchoice' in line:
				extra_height += 20
			elif '$fillentry' in line:
				extra_height += 15
		layout = Pango.Layout.new(self.pango_context)
		layout.set_text(plainstring, -1)
		width, height = layout.get_pixel_size()
		width = (minimum.width if minimum.width > width else width) + 40
		height += extra_height
		height = (
			(minimum.height if minimum.height > height else height) + 60)
		self.resize(width, height)
		self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
		return Gtk.Dialog.run(self)

	def focus_first(self, window):

		self.focus_widget.grab_focus()

	def multi_focus_fix(self, textview, event):

		if event.button is 1:
			x, y = self.textview.window_to_buffer_coords(1, event.x, event.y)
			over, text_iter, trailing = self.textview.get_iter_at_position(x, y)
			anchor = text_iter.get_child_anchor()
			if anchor:
				widgets = anchor.get_widgets()
				if widgets:
					if type(widgets[0]) is Gtk.ScrolledWindow:
						multi = widgets[0].get_child()
						multi.grab_focus()
					else:
						self.focus_widget = widgets[0]
			else:
				self.focus_widget.grab_focus()

	def toggle_option(self, option, event):

		if event.keyval == Gdk.KEY_space:
			option.activate()

	def get_string(self):

		start, end = self.textbuffer.get_bounds()
		return self.html.serialize(start, end, self.richtext)


class AboutDialog(Gtk.AboutDialog):

	def __init__(self):

		Gtk.AboutDialog.__init__(self)
		self.set_program_name(appname)
		self.set_copyright('Copyright © 2018 {}'.format(vendor))
		self.set_authors(('{0} <{1}>'.format(author, author_email), ))
		self.set_website(homepage)
		self.set_website_label('Homepage')
		self.set_license(LICENSE)
		logo_file = os.path.abspath('data/xpander.svg')
		logo_name = 'xpander'
		if os.path.exists(logo_file):
			pixbuf = GdkPixbuf.Pixbuf.new_from_file(logo_file)
			self.set_logo(pixbuf)
		else:
			self.set_logo_icon_name(logo_name)
		self.show_all()


class FolderWarning(Gtk.Dialog):

	def __init__(self):

		Gtk.Dialog.__init__(
			self, 'Warning', None, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				Gtk.STOCK_OK, Gtk.ResponseType.OK))
		self.set_default_response(Gtk.ResponseType.CANCEL)

		box = self.get_content_area()
		title = Gtk.Label()
		title.set_markup('<b>Warning:</b>')
		box.pack_start(title, True, True, 0)
		message = Gtk.Label(
			'Deleting folder will delete all phrases and subfolders!')
		message.set_line_wrap(True)
		box.pack_start(message, True, True, 0)
		self.show_all()


class InsertLink(Gtk.Dialog):

	def __init__(self, parent, title):

		Gtk.Dialog.__init__(
			self, 'Insert Link', parent, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				'Insert', Gtk.ResponseType.OK))
		self.set_default_size(200, 150)
		self.set_skip_taskbar_hint(True)
		self.set_default_response(Gtk.ResponseType.OK)
		self.set_border_width(6)

		box = self.get_content_area()
		switcher = Gtk.StackSwitcher()
		box.pack_start(switcher, False, False, 6)
		self.stack = Gtk.Stack()
		self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
		switcher.set_stack(self.stack)
		box.pack_start(self.stack, True, True, 6)

		self.title = Gtk.Entry(placeholder_text='Title')
		self.stack.add_titled(self.title, 'title', 'Title')
		if title:
			self.title.set_text(title)

		self.image = Gtk.FileChooserButton('Image', Gtk.FileChooserAction.OPEN)
		self.image.add_filter(IMAGESFILTER)
		self.stack.add_titled(self.image, 'image', 'Image')

		self.url = Gtk.Entry(placeholder_text='URL')
		self.url.set_activates_default(True)
		box.pack_start(self.url, True, True, 6)

		self.show_all()
		if title:
			self.url.grab_focus()

	def get_link(self):

		if self.stack.get_visible_child_name() == 'title':
			title = self.title.get_text()
			is_text = True
		else:
			title = self.image.get_filename()
			if os.path.dirname(title) != os.path.abspath(CACHE):
				title = shutil.copy(title, CACHE)
			is_text = False
		return is_text, title, self.url.get_text()


class InsertImage(Gtk.Dialog):

	def __init__(self, parent):

		Gtk.Dialog.__init__(
			self, 'Insert Link', parent, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				'Insert', Gtk.ResponseType.OK))
		self.set_default_size(200, 70)
		self.set_skip_taskbar_hint(True)
		self.set_default_response(Gtk.ResponseType.OK)
		self.set_border_width(6)

		box = self.get_content_area()
		self.image = Gtk.FileChooserButton('Image', Gtk.FileChooserAction.OPEN)
		self.image.add_filter(IMAGESFILTER)
		box.pack_start(self.image, True, True, 6)

		self.show_all()

	def get_image(self):

		image = self.image.get_filename()
		if image and os.path.dirname(image) != os.path.abspath(CACHE):
			image = shutil.copy(image, CACHE)
		return image


class InsertDateMath(Gtk.Dialog):

	def __init__(self, parent, sign, unit):

		self.unit = unit.title()
		Gtk.Dialog.__init__(
			self, self.unit, parent, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				'Insert', Gtk.ResponseType.OK))
		self.set_default_size(200, 70)
		self.set_skip_taskbar_hint(True)
		self.set_default_response(Gtk.ResponseType.OK)
		self.set_border_width(6)
		self.sign = '+' if sign == 'add' else '-' if sign == 'sub' else None

		box = self.get_content_area()
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		self.amount = Gtk.SpinButton.new_with_range(0, 10000, 1)
		hbox.pack_start(self.amount, True, True, 6)
		label = Gtk.Label(self.unit)
		hbox.pack_start(label, False, False, 6)
		box.pack_start(hbox, True, True, 6)
		self.show_all()

	def get_macro(self):

		template = '%@{0}{1}{2}'
		if self.unit in {'Year', 'Month', 'Week', 'Day'}:
			unit = self.unit[0]
		else:
			unit = self.unit[0].casefold()
		return template.format(self.sign, self.amount.get_value_as_int(), unit)


class InsertEntry(Gtk.Dialog):

	def __init__(self, parent):

		Gtk.Dialog.__init__(
			self, 'Entry', parent, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				'Insert', Gtk.ResponseType.OK))
		self.set_skip_taskbar_hint(True)
		self.set_default_response(Gtk.ResponseType.OK)
		self.set_border_width(6)

		mainbox = self.get_content_area()
		namebox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(namebox, True, True, 6)
		name_label = Gtk.Label('Name:')
		namebox.pack_start(name_label, False, False, 6)
		self.name = Gtk.Entry()
		self.name.set_placeholder_text('Name')
		self.name.set_activates_default(True)
		namebox.pack_start(self.name, True, True, 6)
		defaultbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(defaultbox, True, True, 6)
		default_label = Gtk.Label('Default:')
		defaultbox.pack_start(default_label, False, False, 6)
		self.default = Gtk.Entry()
		self.default.set_placeholder_text('Default Value')
		self.default.set_activates_default(True)
		defaultbox.pack_start(self.default, True, True, 6)
		widthbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(widthbox, True, True, 6)
		width_label = Gtk.Label('Width:')
		widthbox.pack_start(width_label, False, False, 6)
		self.width = Gtk.SpinButton.new_with_range(0, 1024, 1)
		self.width.set_activates_default(True)
		widthbox.pack_start(self.width, True, True, 6)
		self.unit = Gtk.ComboBoxText()
		self.unit.append_text('chr')
		self.unit.append_text('px')
		self.unit.set_active(0)
		widthbox.pack_start(self.unit, False, False, 6)
		self.show_all()

	def get_macro(self):

		template = '$fillentry{}$'
		name_t = ':name={}'
		default_t = ':default={}'
		width_t = ':width={0}{1}'
		name = self.name.get_text()
		default = self.default.get_text()
		width = self.width.get_value_as_int()
		unit = self.unit.get_active_text()
		insert = ''
		if name:
			insert += name_t.format(name)
		if default:
			insert += default_t.format(default)
		if width:
			insert += width_t.format(width, unit)
		return template.format(insert)


class InsertMulti(Gtk.Dialog):

	def __init__(self, parent):

		Gtk.Dialog.__init__(
			self, 'Multi', parent, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				'Insert', Gtk.ResponseType.OK))
		self.set_skip_taskbar_hint(True)
		self.set_default_response(Gtk.ResponseType.OK)
		self.set_border_width(6)

		mainbox = self.get_content_area()
		namebox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(namebox, True, True, 6)
		name_label = Gtk.Label('Name:')
		namebox.pack_start(name_label, False, False, 6)
		self.name = Gtk.Entry()
		self.name.set_placeholder_text('Name')
		self.name.set_activates_default(True)
		namebox.pack_start(self.name, True, True, 6)
		defaultbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(defaultbox, True, True, 6)
		default_label = Gtk.Label('Default:')
		defaultbox.pack_start(default_label, False, False, 6)
		self.default = Gtk.Entry()
		self.default.set_placeholder_text('Default Value')
		self.default.set_activates_default(True)
		defaultbox.pack_start(self.default, True, True, 6)
		widthbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(widthbox, True, True, 6)
		width_label = Gtk.Label('Width:')
		widthbox.pack_start(width_label, False, False, 6)
		self.width = Gtk.SpinButton.new_with_range(0, 1024, 1)
		self.width.set_activates_default(True)
		widthbox.pack_start(self.width, True, True, 6)
		self.wunit = Gtk.ComboBoxText()
		self.wunit.append_text('chr')
		self.wunit.append_text('px')
		self.wunit.set_active(0)
		widthbox.pack_start(self.wunit, False, False, 6)
		heightbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(heightbox, True, True, 6)
		height_label = Gtk.Label('Height:')
		heightbox.pack_start(height_label, False, False, 6)
		self.height = Gtk.SpinButton.new_with_range(0, 1024, 1)
		self.height.set_activates_default(True)
		heightbox.pack_start(self.height, True, True, 6)
		self.hunit = Gtk.ComboBoxText()
		self.hunit.append_text('chr')
		self.hunit.append_text('px')
		self.hunit.set_active(0)
		heightbox.pack_start(self.hunit, False, False, 6)
		self.show_all()

	def get_macro(self):

		template = '$fillmulti{}$'
		name_t = ':name={}'
		default_t = ':default={}'
		width_t = ':width={0}{1}'
		height_t = ':height={0}{1}'
		name = self.name.get_text()
		default = self.default.get_text()
		width = self.width.get_value_as_int()
		height = self.height.get_value_as_int()
		insert = ''
		if name:
			insert += name_t.format(name)
		if default:
			insert += default_t.format(default)
		if width:
			insert += width_t.format(width, self.wunit.get_active_text())
		if height:
			insert += height_t.format(height, self.hunit.get_active_text())
		return template.format(insert)


class InsertChoice(Gtk.Dialog):

	def __init__(self, parent):

		Gtk.Dialog.__init__(
			self, 'Choice', parent, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				'Insert', Gtk.ResponseType.OK))
		self.set_skip_taskbar_hint(True)
		self.set_default_response(Gtk.ResponseType.OK)
		self.set_border_width(6)

		mainbox = self.get_content_area()
		namebox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(namebox, True, True, 6)
		name_label = Gtk.Label('Name:')
		namebox.pack_start(name_label, False, False, 6)
		self.name = Gtk.Entry()
		self.name.set_placeholder_text('Name')
		self.name.set_activates_default(True)
		namebox.pack_start(self.name, True, True, 6)
		defaultbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(defaultbox, True, True, 6)
		default_label = Gtk.Label('Default:')
		defaultbox.pack_start(default_label, False, False, 6)
		self.default = Gtk.Entry()
		self.default.set_placeholder_text('Default Choice')
		self.default.set_activates_default(True)
		defaultbox.pack_start(self.default, True, True, 6)
		choicebox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(choicebox, True, True, 6)
		choice_label = Gtk.Label('Choices:')
		choicebox.pack_start(choice_label, False, False, 6)
		self.choices = Gtk.Entry()
		self.choices.set_placeholder_text('1st Choice, 2nd Choice, ...')
		self.choices.set_activates_default(True)
		choicebox.pack_start(self.choices, True, True, 6)
		self.show_all()

	def get_macro(self):

		template = '$fillchoice{}$'
		name_t = ':name={}'
		default_t = ':default={}'
		choice_t = ':{}'
		name = self.name.get_text()
		default = self.default.get_text()
		choices = ''
		for choice in self.choices.get_text().split(','):
			choices += choice_t.format(choice.strip())
		insert = ''
		if name:
			insert += name_t.format(name)
		if default:
			insert += default_t.format(default)
		if choices:
			insert += choices
		return template.format(insert)


class InsertOption(Gtk.Dialog):

	def __init__(self, parent):

		Gtk.Dialog.__init__(
			self, 'Option', parent, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				'Insert', Gtk.ResponseType.OK))
		self.set_skip_taskbar_hint(True)
		self.set_default_response(Gtk.ResponseType.OK)
		self.set_border_width(6)

		mainbox = self.get_content_area()
		namebox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(namebox, True, True, 6)
		name_label = Gtk.Label('Name:')
		namebox.pack_start(name_label, False, False, 6)
		self.name = Gtk.Entry()
		self.name.set_placeholder_text('Name')
		self.name.set_activates_default(True)
		namebox.pack_start(self.name, True, True, 6)
		valuebox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(valuebox, True, True, 6)
		value_label = Gtk.Label('Value:')
		valuebox.pack_start(value_label, False, False, 6)
		self.value = Gtk.Entry()
		self.value.set_placeholder_text('Value')
		self.value.set_activates_default(True)
		valuebox.pack_start(self.value, True, True, 6)
		self.show_all()

	def get_macro(self):

		template = '$filloption{}$'
		name_t = ':name={}'
		value_t = ':{}'
		name = self.name.get_text()
		value = self.value.get_text()
		insert = ''
		if name:
			insert += name_t.format(name)
		if value:
			insert += value_t.format(value)
		return template.format(insert)


class InsertKey(Gtk.Dialog):

	def __init__(self, parent):

		Gtk.Dialog.__init__(
			self, 'Key', parent, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				'Insert', Gtk.ResponseType.OK))
		self.set_skip_taskbar_hint(True)
		self.set_default_response(Gtk.ResponseType.OK)
		self.set_border_width(6)

		mainbox = self.get_content_area()
		keybox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		mainbox.pack_start(keybox, True, True, 6)
		self.key = Gtk.Entry()
		self.key.set_placeholder_text('Press Any Key...')
		self.key.connect('key-press-event', self.key_pressed)
		keybox.pack_start(self.key, True, True, 6)
		self.state = Gtk.ComboBoxText()
		self.state.append_text('Up/Down')
		self.state.append_text('Down')
		self.state.append_text('Up')
		self.state.set_active(0)
		keybox.pack_start(self.state, False, False, 6)
		self.show_all()

	def key_pressed(self, entry, event):

		key = Key.from_ec(event.hardware_keycode - 8)
		entry.set_text(key.name)
		return True

	def get_macro(self):

		template = '${{{}}}'
		state_t = ':{}'
		key = self.key.get_text()
		state = self.state.get_active_text()
		insert = ''
		if key:
			insert += key
			if state == 'Down':
				insert += state_t.format('down')
			elif state == 'Up':
				insert += state_t.format('up')
			return template.format(insert)
		return ''


class InsertPhrase(Gtk.Dialog):

	def __init__(self, parent):

		Gtk.Dialog.__init__(
			self, 'Phrase', parent, 0,
			(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
				'Insert', Gtk.ResponseType.OK))
		self.set_skip_taskbar_hint(True)
		self.set_default_response(Gtk.ResponseType.OK)
		self.set_border_width(6)

		model = Gtk.ListStore(str)
		for phrase in parent.manager.phrases.values():
			model.append((phrase.name, ))
		complete = Gtk.EntryCompletion(model=model, text_column=0)

		box = self.get_content_area()
		self.phrase = Gtk.Entry()
		self.phrase.set_placeholder_text('Enter label...')
		self.phrase.set_activates_default(True)
		self.phrase.set_completion(complete)
		box.pack_start(self.phrase, True, True, 6)
		self.show_all()

	def get_macro(self):

		template = '$<{}>'
		phrase = self.phrase.get_text()
		if phrase:
			return template.format(phrase)
		return ''
