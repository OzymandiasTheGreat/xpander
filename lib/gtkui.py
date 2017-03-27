#!/usr/bin/env python3

import os
import collections
import time
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from . import shared, CONSTANTS

RESERVED_CHARS = '/\\<>:;*$%!?'
_SEND = {'Keyboard': 0,
		'Clipboard': 1,
		'Clipboard (Terminal)': 2}
SEND = collections.OrderedDict(sorted(_SEND.items(), key=lambda x: x[1]))


class ManagerUI(Gtk.Window):

	def __init__(self):

		Gtk.Window.__init__(self, title="xpander")
		self.set_border_width(6)
		self.gui_hotkeys = Gtk.AccelGroup()
		self.add_accel_group(self.gui_hotkeys)
		self.create_window()

	def create_window(self):

		if os.path.exists('data/xpander.svg'):
			self.set_icon_from_file(os.path.abspath('data/xpander.svg'))
		else:
			self.set_icon_name('xpander')

		# General layout
		main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
							spacing=6)
		self.add(main_box)
		stack = Gtk.Stack(
			transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
		paned = Gtk.Paned()
		stack.add_titled(paned, 'manager', 'Manager')
		prefs_grid = Gtk.Grid(
			column_spacing=10, row_spacing=10, margin=10,
			halign=Gtk.Align.CENTER)
		stack.add_titled(prefs_grid, 'prefs', 'Preferences')
		stack_switcher = Gtk.StackSwitcher(halign=Gtk.Align.CENTER)
		stack_switcher.set_stack(stack)
		main_box.pack_start(stack_switcher, False, True, 0)
		main_box.pack_start(stack, True, True, 0)

		# Manager
		left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		treeview_frame = Gtk.Frame(shadow_type=Gtk.ShadowType.IN)
		scrollable_treelist = Gtk.ScrolledWindow(width_request=200)
		scrollable_treelist.set_vexpand(True)
		# Treeview
		self.treestore = Gtk.TreeStore(str, str, str, Gdk.RGBA)
		self.treeview = Gtk.TreeView.new_with_model(self.treestore)
		self.add_mnemonic(Gdk.KEY_m, self.treeview)
		self.treeview.set_headers_visible(False)
		self.treeview.set_search_column(1)
		icon_renderer = Gtk.CellRendererPixbuf()
		icon_column = Gtk.TreeViewColumn('', icon_renderer, icon_name=0)
		self.treeview.append_column(icon_column)
		text_renderer = Gtk.CellRendererText()
		text_renderer.set_property('editable', True)
		text_column = Gtk.TreeViewColumn('Phrases', text_renderer, text=1)
		self.treeview.append_column(text_column)
		string_renderer = Gtk.CellRendererText()
		context = self.treeview.get_style_context()
		self.color_normal = context.get_background_color(Gtk.StateFlags.NORMAL)
		self.color_disabled = context.get_background_color(
			Gtk.StateFlags.INSENSITIVE)
		string_renderer.set_property('editable', False)
		string_column = Gtk.TreeViewColumn(
			'Abbreviatios', string_renderer, text=2, background_rgba=3)
		self.treeview.append_column(string_column)
		self.load_phrases()
		# Drag and drop
		target = Gtk.TargetEntry.new('row', Gtk.TargetFlags.SAME_WIDGET, 0)
		self.treeview.enable_model_drag_source(
			Gdk.ModifierType.BUTTON1_MASK,
			[target],
			Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
		self.treeview.enable_model_drag_dest(
			[target], Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
		# Selection
		self.selection = self.treeview.get_selection()
		# Toolbar
		toolbar = Gtk.Box(margin=2, spacing=2)
		remove_icon = Gtk.Image.new_from_icon_name('list-remove-symbolic', 0)
		remove_button = Gtk.Button()
		remove_button.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_Delete, 0,  # No modifier mask
			Gtk.AccelFlags.VISIBLE)
		remove_button.add(remove_icon)
		toolbar.pack_end(remove_button, False, False, 0)
		add_menu = Gtk.Menu()
		add_phrase = Gtk.MenuItem('New phrase')
		add_phrase.add_accelerator(
			'activate', self.gui_hotkeys, Gdk.KEY_n,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		add_folder = Gtk.MenuItem('New folder')
		add_folder.add_accelerator(
			'activate', self.gui_hotkeys, Gdk.KEY_n,
			Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK,
			Gtk.AccelFlags.VISIBLE)
		add_menu.append(add_phrase)
		add_menu.append(add_folder)
		add_menu.show_all()
		add_icon = Gtk.Image.new_from_icon_name('list-add-symbolic', 0)
		add_button = Gtk.MenuButton()
		add_button.add(add_icon)
		add_button.set_popup(add_menu)
		toolbar.pack_end(add_button, False, False, 0)
		# Editor
		editor_frame = Gtk.Frame(shadow_type=Gtk.ShadowType.IN)
		self.right_grid = Gtk.Grid(
			column_spacing=6, row_spacing=6, margin=6)
		self.right_grid.set_sensitive(False)
		self.plain_text = Gtk.RadioButton.new_with_mnemonic_from_widget(
			None, '_Plain text')
		self.right_grid.attach(self.plain_text, 0, 0, 1, 1)
		self.command = Gtk.RadioButton.new_with_label_from_widget(
			self.plain_text, 'Command')
		self.right_grid.attach(self.command, 1, 0, 1, 1)
		text_wrap = Gtk.CheckButton.new_with_mnemonic('_Wrap text')
		self.right_grid.attach(text_wrap, 5, 0, 1, 1)
		scrollable_textview = Gtk.ScrolledWindow()
		scrollable_textview.set_hexpand(True)
		scrollable_textview.set_vexpand(True)
		self.textview = Gtk.TextView()
		self.add_mnemonic(Gdk.KEY_b, self.textview)
		scrollable_textview.add(self.textview)
		self.right_grid.attach(scrollable_textview, 0, 1, 6, 5)
		token_label = Gtk.Label(
			'$| marks cursor position. $C inserts clipboard contents.')
		self.right_grid.attach(token_label, 0, 6, 3, 1)
		string_label = Gtk.Label.new_with_mnemonic('_Abbreviation:')
		self.right_grid.attach(string_label, 0, 7, 1, 1)
		self.string = Gtk.Entry(max_length=128)
		string_label.set_mnemonic_widget(self.string)
		self.right_grid.attach_next_to(
			self.string, string_label, Gtk.PositionType.RIGHT, 2, 1)
		send_label = Gtk.Label.new_with_mnemonic('_Send via:')
		self.right_grid.attach(send_label, 3, 7, 1, 1)
		self.send = Gtk.ComboBoxText()
		send_label.set_mnemonic_widget(self.send)
		self.send.set_entry_text_column(0)
		for method in SEND:
			self.send.append_text(method)
		self.right_grid.attach_next_to(
			self.send, send_label, Gtk.PositionType.RIGHT, 2, 1)
		filter_class_label = Gtk.Label.new_with_mnemonic(
			'Filter by window _class:')
		self.right_grid.attach(filter_class_label, 0, 8, 1, 1)
		self.filter_class = Gtk.Entry()
		self.right_grid.attach_next_to(
			self.filter_class, filter_class_label, Gtk.PositionType.RIGHT, 2, 1)
		set_filter_class = Gtk.ToggleButton('Select')
		filter_class_label.set_mnemonic_widget(set_filter_class)
		self.right_grid.attach_next_to(
			set_filter_class, self.filter_class, Gtk.PositionType.RIGHT, 1, 1)
		filter_title_label = Gtk.Label.new_with_mnemonic(
			'_Filter by window title:')
		self.right_grid.attach(filter_title_label, 0, 9, 1, 1)
		self.filter_title = Gtk.Entry()
		self.right_grid.attach_next_to(
			self.filter_title, filter_title_label, Gtk.PositionType.RIGHT, 2, 1)
		set_filter_title = Gtk.ToggleButton('Select')
		filter_title_label.set_mnemonic_widget(set_filter_title)
		self.right_grid.attach_next_to(
			set_filter_title, self.filter_title, Gtk.PositionType.RIGHT, 1, 1)
		self.filter_case = Gtk.CheckButton.new_with_mnemonic('Case _sensitive')
		self.right_grid.attach_next_to(
			self.filter_case, set_filter_title, Gtk.PositionType.RIGHT, 1, 1)
		save_phrase = Gtk.Button('Save')
		save_phrase.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_s,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.right_grid.attach(save_phrase, 0, 10, 6, 1)

		# Preferences
		phrase_dir_label = Gtk.Label.new_with_mnemonic(
			'Phrase _directory (needs restart)'.ljust(62))
		prefs_grid.attach(phrase_dir_label, 0, 0, 2, 1)
		phrase_dir = Gtk.FileChooserButton.new(
			'Phrase directory', Gtk.FileChooserAction.SELECT_FOLDER)
		phrase_dir.set_create_folders(True)
		phrase_dir.set_current_folder(shared.config['phrases_dir'])
		phrase_dir_label.set_mnemonic_widget(phrase_dir)
		prefs_grid.attach(phrase_dir, 4, 0, 1, 1)
		indicator_theme_label = Gtk.Label.new_with_mnemonic(
			'Prefer light _indicator icon theme (needs restart)')
		prefs_grid.attach(indicator_theme_label, 0, 1, 2, 1)
		indicator_theme = Gtk.Switch()
		indicator_theme.set_active(shared.config['indicator_theme_light'])
		indicator_theme_label.set_mnemonic_widget(indicator_theme)
		prefs_grid.attach(indicator_theme, 4, 1, 1, 1)
		folder_warning_label = Gtk.Label.new_with_mnemonic(
			'_Warn when deleting a folder'.ljust(63))
		prefs_grid.attach(folder_warning_label, 0, 2, 2, 1)
		folder_warning_switch = Gtk.Switch()
		folder_warning_switch.set_active(shared.config['warn_folder_delete'])
		folder_warning_label.set_mnemonic_widget(folder_warning_switch)
		prefs_grid.attach(folder_warning_switch, 4, 2, 1, 1)
		pause_expansion_label = Gtk.Label.new_with_mnemonic(
			'_Pause expansion'.ljust(65))
		prefs_grid.attach(pause_expansion_label, 0, 5, 1, 1)
		self.pause_expansion = Gtk.Entry()
		self.pause_expansion.set_editable(False)
		key, mod_strings = shared.config['key_pause']
		key = self.get_key(key)
		if key:
			self.pause_expansion.set_text(''.join(mod_strings) + key)
		else:
			self.pause_expansion.set_text('')
		prefs_grid.attach(self.pause_expansion, 2, 5, 2, 1)
		pause_expansion_set = Gtk.Button('Set')
		pause_expansion_label.set_mnemonic_widget(pause_expansion_set)
		prefs_grid.attach(pause_expansion_set, 4, 5, 1, 1)
		show_manager_label = Gtk.Label.new_with_mnemonic('_Show manager'.ljust(65))
		prefs_grid.attach(show_manager_label, 0, 6, 1, 1)
		self.show_manager = Gtk.Entry()
		self.show_manager.set_editable(False)
		key, mod_strings = shared.config['key_show_manager']
		key = self.get_key(key)
		if key:
			self.show_manager.set_text(''.join(mod_strings) + key)
		else:
			self.show_manager.set_text('')
		prefs_grid.attach(self.show_manager, 2, 6, 2, 1)
		show_manager_set = Gtk.Button('Set')
		show_manager_label.set_mnemonic_widget(show_manager_set)
		prefs_grid.attach(show_manager_set, 4, 6, 1, 1)

		# Packing
		scrollable_treelist.add(self.treeview)
		treeview_frame.add(scrollable_treelist)
		left_box.pack_start(treeview_frame, True, True, 0)
		toolbar_frame = Gtk.Frame(shadow_type=Gtk.ShadowType.IN)
		toolbar_frame.add(toolbar)
		left_box.pack_start(toolbar_frame, False, True, 0)
		paned.add1(left_box)
		editor_frame.add(self.right_grid)
		paned.add2(editor_frame)

		# Signals
		# Manager
		text_renderer.connect('edited', self.row_edited)
		self.treeview.connect('drag-data-get', self.drag_data_get)
		self.treeview.connect('drag-data-received', self.drag_data_received)
		self.treeview.connect('button-press-event', self.treeview_clicked)
		add_phrase.connect('activate', self.new_phrase)
		add_folder.connect('activate', self.new_folder)
		remove_button.connect('clicked', self.remove_item)
		self.selection.connect('changed', self.selection_changed)
		# Editor
		self.string.connect('key-press-event', self.string_handle_keypress)
		text_wrap.connect('toggled', self.wrap_text)
		set_filter_class.connect('toggled', self.set_window_class)
		set_filter_title.connect('toggled', self.set_window_title)
		save_phrase.connect('clicked', self.save_phrase)
		# Preferences
		phrase_dir.connect('file-set', self.set_phrase_dir)
		indicator_theme.connect('notify::active', self.set_indicator_theme)
		folder_warning_switch.connect(
			'notify::active', self.folder_warning_toggle)
		pause_expansion_set.connect('clicked', self.get_pause_expansion)
		show_manager_set.connect('clicked', self.get_show_manager)
		# Avoid deleting window, causes segfault
		self.connect('delete-event', self.close_window)

	def load_phrases(self):

		seen_paths = {'.': None}
		for phrase in shared.phrases:
			path = shared.phrase_paths[phrase['name']]
			if path == '.':
				self.treestore.append(
					None,
					['document', phrase['name'],
					phrase['string'], self.color_disabled])
			elif path in seen_paths:
				self.treestore.append(
					seen_paths[path],
					['document', phrase['name'],
					phrase['string'], self.color_disabled])
			else:
				tree_iter = self.treestore.append(
					None,
					['folder', path, '', self.color_normal])
				seen_paths[path] = tree_iter
				self.treestore.append(
					tree_iter,
					['document', phrase['name'],
					phrase['string'], self.color_disabled])
		self.sort_treeview()

	def sort_treeview(self):

		self.treestore.set_sort_column_id(1, Gtk.SortType.ASCENDING)
		self.treestore.set_sort_column_id(0, Gtk.SortType.DESCENDING)

	def row_edited(self, renderer, path, text):

		if text != '':
			for char in RESERVED_CHARS:
				if char in text:
					dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.WARNING,
								Gtk.ButtonsType.OK, 'Illegal characters')
					dialog.format_secondary_text(
						'/\\<>:;*$%!?' + ' are not allowed.')
					response = dialog.run()
					dialog.destroy()
					return
			if self.treestore[path][0] != 'folder':
				old_phrase = self.treestore[path][1]
				new_phrase = text
				iter_parent = self.treestore.iter_parent(
					self.treestore.get_iter(path))
				if iter_parent is not None:
					phrase_path = self.treestore[iter_parent][1]
				else:
					phrase_path = '.'
				self.treestore[path][1] = text
				shared.pmanager.move_phrase(old_phrase, new_phrase, phrase_path)
			else:
				phrase_path = text
				tree_iter = self.treestore.get_iter(path)
				iter_child = self.treestore.iter_children(tree_iter)
				for child in range(self.treestore.iter_n_children(tree_iter)):
					name = self.treestore[iter_child][1]
					shared.pmanager.move_phrase(name, name, phrase_path)
					iter_child = self.treestore.iter_next(iter_child)
				self.treestore[path][1] = text
			self.sort_treeview()

	def drag_data_get(self, widget, context, data, info, timestamp):

		model, tree_iter = self.selection.get_selected()
		path = model.get_path(tree_iter)
		string = path.to_string()
		data.set(data.get_target(), 0, string.encode())

	def drag_data_received(self, widget, context, x, y, data, info, timestamp):

		model = widget.get_model()
		source_iter = model.get_iter_from_string(data.get_data().decode())
		content = model.get(source_iter, 0, 1)
		name = model[source_iter][1]
		path, pos = widget.get_dest_row_at_pos(x, y)
		dest = model.get_iter(path)
		if model[source_iter][0] == 'folder':
			return
		if pos in {Gtk.TreeViewDropPosition.BEFORE,
					Gtk.TreeViewDropPosition.AFTER}:
			dest = model.iter_parent(dest)
		elif model[dest][0] != 'folder':
			dest = model.iter_parent(dest)
		if dest is not None:
			phrase_path = model[dest][1]
		else:
			phrase_path = '.'
		model.remove(source_iter)
		model.insert(dest, -1, content)
		shared.pmanager.move_phrase(name, name, phrase_path)
		self.sort_treeview()

	def selection_changed(self, selection):

		model, tree_iter = selection.get_selected()
		text_buffer = self.textview.get_buffer()
		if tree_iter is not None and model[tree_iter][0] != 'folder':
			name = model[tree_iter][1]
			phrase = next(
				phrase for phrase in shared.phrases if phrase['name'] == name)
			if phrase['command']:
				self.command.set_active(True)
			else:
				self.plain_text.set_active(True)
			text_buffer.set_text(phrase['body'])
			self.string.set_text(phrase['string'])
			self.send.set_active(phrase['method'])
			self.filter_class.set_text(
				phrase['window_class'] if phrase['window_class'] is not None
				else '')
			self.filter_title.set_text(
				phrase['window_title'] if phrase['window_title'] is not None
				else '')
			self.right_grid.set_sensitive(True)
		else:
			self.right_grid.set_sensitive(False)
			self.plain_text.set_active(True)
			text_buffer.set_text('')
			self.string.set_text('')
			self.send.set_active(-1)
			self.filter_class.set_text('')
			self.filter_title.set_text('')

	def treeview_clicked(self, widget, event):

		path = widget.get_path_at_pos(event.x, event.y)
		if path is None:
			self.selection.unselect_all()
		return False

	def new_phrase(self, menu_item):

		model, tree_iter = self.selection.get_selected()
		if tree_iter is not None:
			if model[tree_iter][0] != 'folder':
				tree_iter = model.iter_parent(tree_iter)
			path = model[tree_iter][1]
		else:
			path = '.'
		name = 'New_phrase'
		name_count = 0
		while not self.name_unique(model, name):
			name_count += 1
			name = 'New_phrase' + str(name_count)
		shared.pmanager.new_phrase(name, '', '', False, 0, None, None, path)
		self.treestore.append(
			tree_iter, ['document', name, '', self.color_disabled])
		self.sort_treeview()

	def new_folder(self, menu_item):

		model, tree_iter = self.selection.get_selected()
		tree_iter = None
		name = 'New folder'
		name_count = 0
		while not self.name_unique(model, name):
			name_count += 1
			name = 'New folder' + ' ' + str(name_count)
		self.treestore.append(tree_iter, ['folder', name, '', self.color_normal])
		self.sort_treeview()

	def remove_item(self, widget):

		model, tree_iter = self.selection.get_selected()
		if tree_iter is None:
			return
		if model[tree_iter][0] != 'folder':
			shared.pmanager.remove_phrase(model[tree_iter][1])
			model.remove(tree_iter)
		else:
			remove_folder = True
			if shared.config['warn_folder_delete']:
				dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.WARNING,
							Gtk.ButtonsType.OK_CANCEL, 'Delete folder')
				dialog.format_secondary_text(
					'This will also delete the phrases in this folder.')
				response = dialog.run()
				if response == Gtk.ResponseType.CANCEL:
					remove_folder = False
				dialog.destroy()
			if remove_folder:
				iter_child = model.iter_children(tree_iter)
				for child in range(model.iter_n_children(tree_iter)):
					shared.pmanager.remove_phrase(model[iter_child][1])
					iter_child = model.iter_next(iter_child)
				model.remove(tree_iter)

	def name_unique(self, model, name, iter_parent=None):

		unique = True
		iter_child = model.iter_children(iter_parent)
		for child in range(model.iter_n_children(iter_parent)):
			if model[iter_child][0] == 'folder':
				unique &= self.name_unique(model, name, iter_parent=iter_child)
			if model[iter_child][1] == name:
				unique &= False
			iter_child = model.iter_next(iter_child)
		return unique

	def string_handle_keypress(self, widget, event):

		if event.keyval == Gdk.KEY_space:
			return True
		else:
			return False

	def wrap_text(self, widget):

		if widget.get_active():
			self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
		else:
			self.textview.set_wrap_mode(Gtk.WrapMode.NONE)

	def set_window_class(self, widget):

		if widget.get_active():
			window_class = shared.interface.active_window_class
			get_class_thread = threading.Thread(
				target=self.get_window_class,
				args=(widget, window_class),
				daemon=True)
			get_class_thread.start()

	def get_window_class(self, widget, window_class):

		while widget.get_active():
			if window_class == shared.interface.active_window_class:
				time.sleep(0.5)
			else:
				window_class = shared.interface.active_window_class
				GLib.idle_add(self.filter_class.set_text, window_class)
				GLib.idle_add(widget.set_active, False)

	def set_window_title(self, widget):

		if widget.get_active():
			window_title = shared.interface.active_window_title
			get_title_thread = threading.Thread(
				target=self.get_window_title,
				args=(widget, window_title),
				daemon=True)
			get_title_thread.start()

	def get_window_title(self, widget, window_title):

		while widget.get_active():
			if window_title == shared.interface.active_window_title:
				time.sleep(0.5)
			else:
				window_title = shared.interface.active_window_title
				GLib.idle_add(self.filter_title.set_text, window_title)
				GLib.idle_add(widget.set_active, False)

	def save_phrase(self, widget):

		model, tree_iter = self.selection.get_selected()
		if tree_iter is not None and model[tree_iter][0] != 'folder':
			name = model[tree_iter][1]
			command = self.command.get_active()
			text_buffer = self.textview.get_buffer()
			body_start, body_end = text_buffer.get_bounds()
			body = text_buffer.get_text(body_start, body_end, False)
			string = self.string.get_text()
			method = self.send.get_active()
			window_class = self.filter_class.get_text()
			window_title = self.filter_title.get_text()
			shared.pmanager.edit_phrase(
				name, string=string, body=body, command=command, method=method,
				window_class=window_class, window_title=window_title)
			model[tree_iter][2] = string

	def get_key(self, key):

		keysym = shared.interface.char_to_keysym(key)
		keycode, state = shared.interface.keysym_to_keycode(keysym)
		keysym = shared.interface.local_display.keycode_to_keysym(keycode, 0)
		key = shared.interface.keysym_to_char(keysym)
		return key

	def set_phrase_dir(self, widget):

		shared.cmanager.edit('phrases_dir', widget.get_filename())
		shared.cmanager.write_config()
		dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.WARNING,
			Gtk.ButtonsType.OK, 'Restart app')
		dialog.format_secondary_text('Phrase editing and creation will not'
						' function corectly until application is restarted.')
		dialog.run()
		dialog.destroy()

	def set_indicator_theme(self, widget, pspec):

		shared.cmanager.edit('indicator_theme_light', widget.get_active())
		shared.cmanager.write_config()

	def folder_warning_toggle(self, widget, pspec):

		shared.cmanager.edit('warn_folder_delete', widget.get_active())
		shared.cmanager.write_config()

	def capture_hotkey(self, widget, event, callback):

		keysym = shared.interface.local_display.keycode_to_keysym(
			event.hardware_keycode, 0)
		key = shared.interface.keysym_to_char(keysym)
		modifiers = []
		for mod in shared.interface.MODIFIER_MASK:
			if event.state & shared.interface.MODIFIER_MASK[mod]:
				modifiers.append(mod)
		if key and modifiers:
			hotkey = (key, modifiers)
			string = ''.join(modifiers) + key
			callback(string, hotkey)
			self.disconnect(self.event_hid)
		elif keysym == CONSTANTS.XK.XK_Escape:
			self.disconnect(self.event_hid)
		elif keysym == CONSTANTS.XK.XK_BackSpace:
			callback('', ('', ('', '')))
			self.disconnect(self.event_hid)

	def get_pause_expansion(self, widget):

		self.event_hid = self.connect(
			'key-press-event', self.capture_hotkey, self.set_pause_expansion)

	def set_pause_expansion(self, string, hotkey):

		shared.cmanager.edit('key_pause', hotkey)
		shared.cmanager.write_config()
		shared.service.ungrab_hotkeys()
		shared.service.grab_hotkeys()
		self.pause_expansion.set_text(string)

	def get_show_manager(self, widget):

		self.event_hid = self.connect(
			'key-press-event', self.capture_hotkey, self.set_show_manager)

	def set_show_manager(self, string, hotkey):

		shared.cmanager.edit('key_show_manager', hotkey)
		shared.cmanager.write_config()
		shared.service.ungrab_hotkeys()
		shared.service.grab_hotkeys()
		self.pause_expansion.set_text(string)

	def close_window(self, widget, event):

		self.hide()
		shared.manager_shown = False
		return True
