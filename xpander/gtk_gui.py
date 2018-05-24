#!/usr/bin/env python3

import sys
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
from gi.repository import Gtk, GtkSource, Gdk, GdkPixbuf, GLib, Pango
from markdown2 import Markdown
import klembord as Clipboard
from macpy import Window, Key
from macpy.platform import PLATFORM, Platform
from .gtk_dialogs import FolderWarning, InsertLink, InsertImage, InsertDateMath
from .gtk_dialogs import InsertEntry, InsertMulti, InsertChoice, InsertOption
from .gtk_dialogs import InsertKey, InsertPhrase
from .html import HTMLSerializer, PlainText
from .phrase import PhraseType, PasteMethod, Phrase
from .control import MSG, MsgType


CSS = """
.text_link {
	border-style: none;
	box-shadow: none;
	padding: 0px;
	color: blue;
}
.text_link:hover label {
	text-decoration-line: underline;
}
.filterbox {
	border-radius: 50px;
}
""".encode()


RESERVEDCHARS = r'<>:"/\|?*'
TITLE = 'Phrase Editor'


Clipboard.init()


class Editor(Gtk.Window):

	def __init__(self, settings, manager, client, execpath):

		Gtk.Window.__init__(self, title=TITLE)
		self.set_border_width(6)
		self.gui_hotkeys = Gtk.AccelGroup()
		self.add_accel_group(self.gui_hotkeys)
		style_provider = Gtk.CssProvider()
		style_provider.load_from_data(CSS)
		Gtk.StyleContext.add_provider_for_screen(
			Gdk.Screen.get_default(),
			style_provider,
			Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
		self.connect('delete-event', self.close)
		GLib.set_prgname('xpander-gui')
		self.execpath = execpath
		icon_path = execpath / 'data/xpander.svg'
		if getattr(sys, 'frozen', False) or icon_path.exists():
			self.set_icon_from_file(str(icon_path))
		else:
			self.set_icon_name('xpander')

		self.settings = settings
		self.manager = manager
		self.client = client
		if self.client.offline:
			self.set_title(TITLE + ' : Offline')

		self.types = {}

		mainbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		self.add(mainbox)
		mainstack = Gtk.Stack(
			transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
		self.editorpane = Gtk.Paned()
		mainstack.add_titled(self.editorpane, 'editor', 'Edit')
		self.hotkeybox = Gtk.Box(
			orientation=Gtk.Orientation.VERTICAL, spacing=10)
		mainstack.add_titled(self.hotkeybox, 'hotkeys', 'Hotkeys')
		self.settingsgrid = Gtk.Grid(halign=Gtk.Align.CENTER)
		mainstack.add_titled(self.settingsgrid, 'settings', 'Settings')
		stackswitcher = Gtk.StackSwitcher(halign=Gtk.Align.CENTER)
		stackswitcher.set_stack(mainstack)
		for button in stackswitcher.get_children():
			label = button.get_child().get_label()
			if label == 'Hotkeys':
				button.connect('toggled', self.stack_switched)
			elif label == 'Settings':
				button.connect('toggled', self.stack_switched)
		mainbox.pack_start(stackswitcher, False, True, 0)
		mainbox.pack_start(mainstack, True, True, 0)
		self.build_editor()
		self.build_hotkeys()
		self.build_settings()

		self.connect('button-press-event', self.button_pressed)
		self.pointer_grab_class = False
		self.pointer_grab_title = False

		self.opentags = set()
		self.body_insert = False

		self.serializer = HTMLSerializer(self.sourceview)
		self.extractor = PlainText()
		self.md_converter = Markdown()
		self.load_phrases()

		self.show_all()
		self.mainloop = GLib.MainLoop()
		# ~ self.mainloop.run()

	def close(self, window, event):

		self.client.close()
		self.mainloop.quit()

	def start(self):

		self.mainloop.run()

	def build_editor(self):

		self.managerbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		self.managerframe = Gtk.Frame(shadow_type=Gtk.ShadowType.IN)
		self.managerframe.add(self.managerbox)
		self.editorpane.add1(self.managerframe)
		self.scrolledmanager = Gtk.ScrolledWindow(width_request=250)
		self.scrolledmanager.set_vexpand(True)
		self.build_manager()
		self.scrolledmanager.add(self.phraseview)
		self.managerbox.pack_start(self.scrolledmanager, True, True, 0)
		self.build_manager_toolbar()

		self.propsframe = Gtk.Frame(shadow_type=Gtk.ShadowType.IN)
		self.propsgrid = Gtk.Grid(column_spacing=6, row_spacing=6, margin=6)
		self.propsframe.add(self.propsgrid)
		self.editorpane.add2(self.propsframe)
		self.build_properties()

	def build_manager(self):

		self.phrasestore = Gtk.TreeStore(str, str, str, Gdk.RGBA, str)
		self.phraseview = Gtk.TreeView.new_with_model(self.phrasestore)
		self.add_mnemonic(Gdk.KEY_m, self.phraseview)
		self.phraseview.set_headers_visible(False)
		self.phraseview.set_search_column(1)
		icon_renderer = Gtk.CellRendererPixbuf()
		icon_column = Gtk.TreeViewColumn('', icon_renderer, icon_name=0)
		self.phraseview.append_column(icon_column)
		label_renderer = Gtk.CellRendererText()
		label_renderer.set_property('editable', True)
		label_renderer.connect('edited', self.label_edited)
		label_column = Gtk.TreeViewColumn('Label', label_renderer, text=1)
		label_column.set_expand(True)
		self.phraseview.append_column(label_column)
		abbr_renderer = Gtk.CellRendererText()
		context = self.phraseview.get_style_context()
		self.color_normal = context.get_background_color(Gtk.StateFlags.NORMAL)
		self.color_disabled = context.get_background_color(
			Gtk.StateFlags.INSENSITIVE)
		self.color_conflict = Gdk.RGBA(red=0.8, green=0.0, blue=0.0, alpha=1.0)
		abbr_renderer.set_property('editable', False)
		abbr_renderer.set_property('xalign', 0.9)
		abbr_column = Gtk.TreeViewColumn(
			'Abbreviation', abbr_renderer, text=2, background_rgba=3)
		self.phraseview.append_column(abbr_column)
		self.phraseselection = self.phraseview.get_selection()
		self.phraseselection.connect('changed', self.phrase_selected)
		self.phraseview.connect('button-press-event', self.phrase_select_none)
		self.phraseview.connect('key-press-event', self.rename_phrase)
		target = Gtk.TargetEntry.new('row', Gtk.TargetFlags.SAME_WIDGET, 0)
		self.phraseview.enable_model_drag_source(
			Gdk.ModifierType.BUTTON1_MASK,
			[target],
			Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
		self.phraseview.enable_model_drag_dest(
			[target], Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
		self.phraseview.connect('drag-data-get', self.phrase_drag_data_get)
		self.phraseview.connect(
			'drag-data-received', self.phrase_drag_data_received)

	def build_manager_toolbar(self):

		toolbar = Gtk.ButtonBox(
			orientation=Gtk.Orientation.HORIZONTAL,
			layout_style=Gtk.ButtonBoxStyle.EXPAND)
		new_phrase = Gtk.Button()
		new_phrase_icon = Gtk.Image.new_from_icon_name('document-new', 0)
		new_phrase.add(new_phrase_icon)
		new_phrase.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_n,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		new_phrase.connect('clicked', self.new_phrase)
		toolbar.pack_start(new_phrase, True, True, 0)
		new_folder = Gtk.Button()
		new_folder_icon = Gtk.Image.new_from_icon_name('folder-new', 0)
		new_folder.add(new_folder_icon)
		new_folder.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_n,
			Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK,
			Gtk.AccelFlags.VISIBLE)
		new_folder.connect('clicked', self.new_folder)
		toolbar.pack_start(new_folder, True, True, 0)
		delete = Gtk.Button()
		delete_icon = Gtk.Image.new_from_icon_name('edit-delete', 0)
		delete.add(delete_icon)
		delete.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_Delete,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		delete.connect('clicked', self.delete)
		toolbar.pack_start(delete, True, True, 0)
		self.managerbox.pack_start(toolbar, False, True, 0)

	def build_properties(self):

		self.build_typetoolbar()
		self.build_insert()
		self.build_richtoolbar()
		self.build_sourceview()
		self.build_tags()
		self.build_fields()

	def build_typetoolbar(self):

		self.propsgrid.set_sensitive(False)
		self.typetoolbar = Gtk.ButtonBox(
			orientation=Gtk.Orientation.HORIZONTAL,
			layout_style=Gtk.ButtonBoxStyle.EXPAND)
		self.typetoolbar.set_homogeneous(False)
		self.plaintext = Gtk.RadioButton.new_with_mnemonic(None, '_Plain Text')
		self.plaintext.set_tooltip_text('Plain text without any formatting')
		self.plaintext.connect('toggled', self.type_changed, 'plaintext')
		self.types[self.plaintext] = PhraseType.PLAINTEXT
		self.typetoolbar.pack_start(self.plaintext, True, True, 0)
		self.richtext = Gtk.RadioButton.new_with_label_from_widget(
			self.plaintext, 'Rich Text')
		self.richtext.set_tooltip_text(
			'Formatted rich text with links and images')
		self.richtext.connect('toggled', self.type_changed, 'richtext')
		self.types[self.richtext] = PhraseType.RICHTEXT
		self.typetoolbar.pack_start(self.richtext, True, True, 0)
		self.markdown = Gtk.RadioButton.new_with_label_from_widget(
			self.plaintext, 'Markdown')
		self.markdown.set_tooltip_text(
			'Rich text formatted with Markdown markup language')
		self.markdown.connect('toggled', self.type_changed, 'markdown')
		self.types[self.markdown] = PhraseType.MARKDOWN
		self.typetoolbar.pack_start(self.markdown, True, True, 0)
		self.command = Gtk.RadioButton.new_with_label_from_widget(
			self.plaintext, 'Shell Command')
		self.command.set_tooltip_text('Shell command to be executed')
		self.command.connect('toggled', self.type_changed, 'command')
		self.types[self.command] = PhraseType.COMMAND
		self.typetoolbar.pack_start(self.command, True, True, 0)
		self.html = Gtk.RadioButton.new_with_label_from_widget(
			self.plaintext, 'HTML')
		self.html.set_tooltip_text('Raw HTML markup')
		self.html.connect('toggled', self.type_changed, 'html')
		self.types[self.html] = PhraseType.HTML
		self.typetoolbar.pack_start(self.html, True, True, 0)
		sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
		self.typetoolbar.pack_start(sep1, True, True, 10)
		self.undo = Gtk.Button.new_from_icon_name('edit-undo', 2)
		self.undo.set_tooltip_text('Undo last edit')
		self.undo.set_sensitive(False)
		self.undo.connect('clicked', self.sourceview_undo)
		self.typetoolbar.pack_start(self.undo, True, True, 0)
		self.redo = Gtk.Button.new_from_icon_name('edit-redo', 2)
		self.redo.set_tooltip_text('Redo last edit')
		self.redo.set_sensitive(False)
		self.redo.connect('clicked', self.sourceview_redo)
		self.typetoolbar.pack_start(self.redo, True, True, 0)
		sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
		self.typetoolbar.pack_start(sep2, True, True, 10)
		self.insert = Gtk.MenuButton('_Insert')
		self.insert.set_use_underline(True)
		self.insert.set_tooltip_text('Insert a keyboard, date or other macro')
		self.typetoolbar.pack_start(self.insert, True, True, 0)
		self.wrap = Gtk.CheckButton.new_with_mnemonic('_Wrap Text')
		self.wrap.connect('toggled', self.wrap_text)
		self.typetoolbar.pack_start(self.wrap, True, True, 0)
		self.propsgrid.attach(self.typetoolbar, 0, 0, 16, 1)

	def build_insert(self):

		mainmenu = Gtk.Menu()
		date_menu = Gtk.Menu()
		datemath_menu = Gtk.Menu()
		add_menu = Gtk.Menu()
		sub_menu = Gtk.Menu()
		fillin_menu = Gtk.Menu()
		trigover_menu = Gtk.Menu()

		add_year = Gtk.MenuItem.new_with_label('Year')
		add_year.connect('activate', self.insert_macro, 'math', 'add_year')
		add_menu.append(add_year)
		add_month = Gtk.MenuItem.new_with_label('Month')
		add_month.connect('activate', self.insert_macro, 'math', 'add_month')
		add_menu.append(add_month)
		add_week = Gtk.MenuItem.new_with_label('Week')
		add_week.connect('activate', self.insert_macro, 'math', 'add_week')
		add_menu.append(add_week)
		add_day = Gtk.MenuItem.new_with_label('Day')
		add_day.connect('activate', self.insert_macro, 'math', 'add_day')
		add_menu.append(add_day)
		add_hour = Gtk.MenuItem.new_with_label('Hour')
		add_hour.connect('activate', self.insert_macro, 'math', 'add_hour')
		add_menu.append(add_hour)
		add_minute = Gtk.MenuItem.new_with_label('Minute')
		add_minute.connect('activate', self.insert_macro, 'math', 'add_minute')
		add_menu.append(add_minute)
		add_second = Gtk.MenuItem.new_with_label('Second')
		add_second.connect('activate', self.insert_macro, 'math', 'add_second')
		add_menu.append(add_second)
		sub_year = Gtk.MenuItem.new_with_label('Year')
		sub_year.connect('activate', self.insert_macro, 'math', 'sub_year')
		sub_menu.append(sub_year)
		sub_month = Gtk.MenuItem.new_with_label('Month')
		sub_month.connect('activate', self.insert_macro, 'math', 'sub_month')
		sub_menu.append(sub_month)
		sub_week = Gtk.MenuItem.new_with_label('Week')
		sub_week.connect('activate', self.insert_macro, 'math', 'sub_week')
		sub_menu.append(sub_week)
		sub_day = Gtk.MenuItem.new_with_label('Day')
		sub_day.connect('activate', self.insert_macro, 'math', 'sub_day')
		sub_menu.append(sub_day)
		sub_hour = Gtk.MenuItem.new_with_label('Hour')
		sub_hour.connect('activate', self.insert_macro, 'math', 'sub_hour')
		sub_menu.append(sub_hour)
		sub_minute = Gtk.MenuItem.new_with_label('Minute')
		sub_minute.connect('activate', self.insert_macro, 'math', 'sub_minute')
		sub_menu.append(sub_minute)
		sub_second = Gtk.MenuItem.new_with_label('Second')
		sub_second.connect('activate', self.insert_macro, 'math', 'sub_second')
		sub_menu.append(sub_second)
		add_item = Gtk.MenuItem.new_with_label('Add')
		add_item.set_submenu(add_menu)
		datemath_menu.append(add_item)
		sub_item = Gtk.MenuItem.new_with_label('Subtract')
		sub_item.set_submenu(sub_menu)
		datemath_menu.append(sub_item)
		math_item = Gtk.MenuItem.new_with_label('Math')
		math_item.set_submenu(datemath_menu)
		date_menu.append(math_item)

		year_full = Gtk.MenuItem.new_with_label('Year (4-digits)')
		year_full.connect('activate', self.insert_macro, 'date', '%Y')
		date_menu.append(year_full)
		year_abbr = Gtk.MenuItem.new_with_label('Year (2-digits)')
		year_abbr.connect('activate', self.insert_macro, 'date', '%y')
		date_menu.append(year_abbr)
		month_name = Gtk.MenuItem.new_with_label("Month's name")
		month_name.connect('activate', self.insert_macro, 'date', '%B')
		date_menu.append(month_name)
		month_abbr = Gtk.MenuItem.new_with_label("Month's name abbr.")
		month_abbr.connect('activate', self.insert_macro, 'date', '%b')
		date_menu.append(month_abbr)
		month_num = Gtk.MenuItem.new_with_label('Month numeric')
		month_num.connect('activate', self.insert_macro, 'date', '%m')
		date_menu.append(month_num)
		day_month = Gtk.MenuItem.new_with_label('Day of the month')
		day_month.connect('activate', self.insert_macro, 'date', '%d')
		date_menu.append(day_month)
		day_week = Gtk.MenuItem.new_with_label('Day of the week')
		day_week.connect('activate', self.insert_macro, 'date', '%A')
		date_menu.append(day_week)
		day_abbr = Gtk.MenuItem.new_with_label('Day of the week abbr.')
		day_abbr.connect('activate', self.insert_macro, 'date', '%a')
		date_menu.append(day_abbr)
		day_year = Gtk.MenuItem.new_with_label('Day of the year')
		day_year.connect('activate', self.insert_macro, 'date', '%j')
		date_menu.append(day_year)
		hour_24 = Gtk.MenuItem.new_with_label('Hour (24-hour)')
		hour_24.connect('activate', self.insert_macro, 'date', '%H')
		date_menu.append(hour_24)
		hour_12 = Gtk.MenuItem.new_with_label('Hour (12-hour)')
		hour_12.connect('activate', self.insert_macro, 'date', '%I')
		date_menu.append(hour_12)
		am_pm = Gtk.MenuItem.new_with_label('AM/PM')
		am_pm.connect('activate', self.insert_macro, 'date', '%p')
		date_menu.append(am_pm)
		minute = Gtk.MenuItem.new_with_label('Minute')
		minute.connect('activate', self.insert_macro, 'date', '%M')
		date_menu.append(minute)
		second = Gtk.MenuItem.new_with_label('Second')
		second.connect('activate', self.insert_macro, 'date', '%S')
		date_menu.append(second)

		fill_entry = Gtk.MenuItem.new_with_label('Entry')
		fill_entry.connect('activate', self.insert_macro, 'fillin', 'entry')
		fillin_menu.append(fill_entry)
		fill_multi = Gtk.MenuItem.new_with_label('Multiline')
		fill_multi.connect('activate', self.insert_macro, 'fillin', 'multi')
		fillin_menu.append(fill_multi)
		fill_choice = Gtk.MenuItem.new_with_label('Choice')
		fill_choice.connect('activate', self.insert_macro, 'fillin', 'choice')
		fillin_menu.append(fill_choice)
		fill_option = Gtk.MenuItem.new_with_label('Option')
		fill_option.connect('activate', self.insert_macro, 'fillin', 'option')
		fillin_menu.append(fill_option)

		trig_keep = Gtk.MenuItem.new_with_label('Keep trigger')
		trig_keep.connect('activate', self.insert_macro, 'trigger', '$+')
		trigover_menu.append(trig_keep)
		trig_rem = Gtk.MenuItem.new_with_label('Remove trigger')
		trig_rem.connect('activate', self.insert_macro, 'trigger', '$-')
		trigover_menu.append(trig_rem)

		date_item = Gtk.MenuItem.new_with_label('Date/Time')
		date_item.set_submenu(date_menu)
		mainmenu.append(date_item)
		fillin_item = Gtk.MenuItem.new_with_label('Fill-In')
		fillin_item.set_submenu(fillin_menu)
		mainmenu.append(fillin_item)
		trigover_item = Gtk.MenuItem.new_with_label('Trigger overrides')
		trigover_item.set_submenu(trigover_menu)
		mainmenu.append(trigover_item)
		cursor_item = Gtk.MenuItem.new_with_label('Cursor')
		cursor_item.connect('activate', self.insert_macro, 'cursor', '$|')
		mainmenu.append(cursor_item)
		clipboard_item = Gtk.MenuItem.new_with_label('Clipboard')
		clipboard_item.connect('activate', self.insert_macro, 'clipboard', '$C')
		mainmenu.append(clipboard_item)
		key_item = Gtk.MenuItem.new_with_label('Key')
		key_item.connect('activate', self.insert_macro, 'key', None)
		mainmenu.append(key_item)
		phrase_item = Gtk.MenuItem.new_with_label('Phrase')
		phrase_item.connect('activate', self.insert_macro, 'phrase', None)
		mainmenu.append(phrase_item)
		mainmenu.show_all()
		self.insert.set_popup(mainmenu)

	def insert_macro(self, menu_item, action, subaction):

		macro = None
		if action == 'math':
			dialog = InsertDateMath(self, *subaction.split('_'))
			response = dialog.run()
			if response == Gtk.ResponseType.OK:
				macro = dialog.get_macro()
			dialog.destroy()
		elif action == 'date':
			macro = subaction
		elif action == 'fillin':
			if subaction == 'entry':
				dialog = InsertEntry(self)
			elif subaction == 'multi':
				dialog = InsertMulti(self)
			elif subaction == 'choice':
				dialog = InsertChoice(self)
			elif subaction == 'option':
				dialog = InsertOption(self)
			response = dialog.run()
			if response == Gtk.ResponseType.OK:
				macro = dialog.get_macro()
			dialog.destroy()
		elif action == 'trigger':
			macro = subaction
			end = self.sourcebuffer.get_end_iter()
			self.sourcebuffer.place_cursor(end)
		elif action == 'cursor':
			macro = subaction
		elif action == 'clipboard':
			macro = subaction
		elif action == 'key':
			dialog = InsertKey(self)
			response = dialog.run()
			if response == Gtk.ResponseType.OK:
				macro = dialog.get_macro()
			dialog.destroy()
		elif action == 'phrase':
			dialog = InsertPhrase(self)
			response = dialog.run()
			if response == Gtk.ResponseType.OK:
				macro = dialog.get_macro()
			dialog.destroy()
		if macro:
			self.sourcebuffer.insert_at_cursor(macro, -1)
		self.sourceview.grab_focus()

	def build_richtoolbar(self):


		self.richrevealer = Gtk.Revealer(
			transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
		self.propsgrid.attach_next_to(
			self.richrevealer, self.typetoolbar, Gtk.PositionType.BOTTOM, 16, 1)
		self.richtoolbar = Gtk.ButtonBox(
			orientation=Gtk.Orientation.HORIZONTAL,
			layout_style=Gtk.ButtonBoxStyle.EXPAND)
		self.richtoolbar.set_homogeneous(False)
		self.richrevealer.add(self.richtoolbar)
		self.simpletags = {}

		self.bold = Gtk.ToggleButton()
		bold_icon = Gtk.Image.new_from_icon_name('format-text-bold', 2)
		self.bold.set_image(bold_icon)
		self.bold.set_tooltip_text('Bold (Ctrl+B)')
		self.bold.connect('toggled', self.richtoolbutton, 'bold', None)
		self.bold.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_b,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.simpletags['bold'] = self.bold
		self.richtoolbar.pack_start(self.bold, True, True, 0)

		self.italic = Gtk.ToggleButton()
		italic_icon = Gtk.Image.new_from_icon_name('format-text-italic', 2)
		self.italic.set_image(italic_icon)
		self.italic.set_tooltip_text('Italic (Ctrl+I)')
		self.italic.connect('toggled', self.richtoolbutton, 'italic', None)
		self.italic.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_i,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.simpletags['italic'] = self.italic
		self.richtoolbar.pack_start(self.italic, True, True, 0)

		self.underline = Gtk.ToggleButton()
		underline_icon = Gtk.Image.new_from_icon_name(
			'format-text-underline', 2)
		self.underline.set_image(underline_icon)
		self.underline.set_tooltip_text('Underline (Ctrl+U)')
		self.underline.connect(
			'toggled', self.richtoolbutton, 'underline', None)
		self.underline.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_u,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.simpletags['underline'] = self.underline
		self.richtoolbar.pack_start(self.underline, True, True, 0)

		self.strikethrough = Gtk.ToggleButton()
		strikethrough_icon = Gtk.Image.new_from_icon_name(
			'format-text-strikethrough', 2)
		self.strikethrough.set_image(strikethrough_icon)
		self.strikethrough.set_tooltip_text('Strikethrough (Ctrl+T)')
		self.strikethrough.connect(
			'toggled', self.richtoolbutton, 'strikethrough', None)
		self.strikethrough.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_t,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.simpletags['strikethrough'] = self.strikethrough
		self.richtoolbar.pack_start(self.strikethrough, True, True, 0)

		self.subscript = Gtk.ToggleButton()
		subscript_icon = Gtk.Image.new_from_icon_name(
			'format-text-subscript', 2)
		self.subscript.set_image(subscript_icon)
		self.subscript.set_tooltip_text('Subscript (Ctrl+Arrow Down)')
		self.subscript.connect(
			'toggled', self.richtoolbutton, 'subscript', None)
		self.subscript.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_Down,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.simpletags['subscript'] = self.subscript
		self.richtoolbar.pack_start(self.subscript, True, True, 0)

		self.superscript = Gtk.ToggleButton()
		superscript_icon = Gtk.Image.new_from_icon_name(
			'format-text-superscript', 2)
		self.superscript.set_image(superscript_icon)
		self.superscript.set_tooltip_text('Superscript (Ctrl+Arrow Up)')
		self.superscript.connect(
			'toggled', self.richtoolbutton, 'superscript', None)
		self.superscript.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_Up,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.simpletags['superscript'] = self.superscript
		self.richtoolbar.pack_start(self.superscript, True, True, 0)

		self.font = Gtk.FontButton.new_with_font('')
		self.font.set_filter_func(self.filter_fonts, None)
		self.font.set_tooltip_text('Choose Font')
		self.font.connect('font-set', self.richtoolbutton, 'font', None)
		self.richtoolbar.pack_start(self.font, True, True, 0)

		self.color_black = Gdk.RGBA()
		self.color_black.parse('rgb(0, 0, 0)')
		self.foreground_color = Gtk.ColorButton.new_with_rgba(self.color_black)
		self.foreground_color.set_tooltip_text('Text Color')
		self.foreground_color.connect(
			'color-set', self.richtoolbutton, 'foreground', None)
		self.richtoolbar.pack_start(self.foreground_color, True, True, 0)

		self.color_white = Gdk.RGBA()
		self.color_white.parse('rgb(255, 255, 255)')
		self.background_color = Gtk.ColorButton.new_with_rgba(self.color_white)
		self.background_color.set_tooltip_text('Highlight Color')
		self.background_color.connect(
			'color-set', self.richtoolbutton, 'background', None)
		self.richtoolbar.pack_start(self.background_color, True, True, 0)

		self.align_left = Gtk.RadioButton()
		left_icon = Gtk.Image.new_from_icon_name('format-justify-left', 2)
		self.align_left.set_image(left_icon)
		self.align_left.props.draw_indicator = False
		self.align_left.set_tooltip_text('Align Left (Ctrl+L)')
		self.align_left.connect(
			'toggled', self.richtoolbutton, 'text-align', 'left')
		self.align_left.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_l,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.richtoolbar.pack_start(self.align_left, True, True, 0)

		self.align_center = Gtk.RadioButton.new_from_widget(self.align_left)
		center_icon = Gtk.Image.new_from_icon_name('format-justify-center', 2)
		self.align_center.set_image(center_icon)
		self.align_center.props.draw_indicator = False
		self.align_center.set_tooltip_text('Center Horizontally (Ctrl+E)')
		self.align_center.connect(
			'toggled', self.richtoolbutton, 'text-align', 'center')
		self.align_center.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_e,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.richtoolbar.pack_start(self.align_center, True, True, 0)

		self.align_right = Gtk.RadioButton.new_from_widget(self.align_left)
		right_icon = Gtk.Image.new_from_icon_name('format-justify-right', 2)
		self.align_right.set_image(right_icon)
		self.align_right.props.draw_indicator = False
		self.align_right.set_tooltip_text('Align Right (Ctrl+R)')
		self.align_right.connect(
			'toggled', self.richtoolbutton, 'text-align', 'right')
		self.align_right.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_r,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.richtoolbar.pack_start(self.align_right, True, True, 0)

		self.align_justify = Gtk.RadioButton.new_from_widget(self.align_left)
		justify_icon = Gtk.Image.new_from_icon_name('format-justify-fill', 2)
		self.align_justify.set_image(justify_icon)
		self.align_justify.props.draw_indicator = False
		self.align_justify.set_tooltip_text('Justify (Ctrl+J)')
		self.align_justify.connect(
			'toggled', self.richtoolbutton, 'text-align', 'justify')
		self.align_justify.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_j,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.richtoolbar.pack_start(self.align_justify, True, True, 0)

		self.format_clear = Gtk.Button.new_from_icon_name('format-text-none', 2)
		self.format_clear.set_tooltip_text('Clear formatting (Ctrl+M)')
		self.format_clear.connect('clicked', self.richtoolbutton, 'clear', None)
		self.format_clear.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_m,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.richtoolbar.pack_start(self.format_clear, True, True, 0)

		self.insert_link = Gtk.Button.new_from_icon_name('insert-link', 2)
		self.insert_link.set_tooltip_text('Insert hyperlink (Ctrl+K)')
		self.insert_link.connect('clicked', self.richtoolbutton, 'link', None)
		self.insert_link.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_k,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.richtoolbar.pack_start(self.insert_link, True, True, 0)

		self.insert_image = Gtk.Button.new_from_icon_name('insert-image', 2)
		self.insert_image.set_tooltip_text('Insert image (Ctrl+I)')
		self.insert_image.connect('clicked', self.richtoolbutton, 'image', None)
		self.insert_image.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_i,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.richtoolbar.pack_start(self.insert_image, True, True, 0)

	def build_sourceview(self):

		self.scrolledsourceview = Gtk.ScrolledWindow(
			hexpand=True, vexpand=True, min_content_height=200)
		self.propsgrid.attach_next_to(
			self.scrolledsourceview, self.richrevealer,
			Gtk.PositionType.BOTTOM, 16, 10)
		self.sourceview = GtkSource.View()
		self.sourcebuffer = self.sourceview.get_buffer()
		self.sourceview.set_top_margin(6)
		self.sourceview.set_right_margin(6)
		self.sourceview.set_bottom_margin(6)
		self.sourceview.set_left_margin(6)
		self.sourceview.set_indent_on_tab(True)
		self.sourceview.set_insert_spaces_instead_of_tabs(False)
		self.sourceview.set_smart_backspace(False)
		self.sourceview.set_tab_width(4)
		self.sourceview.add_accelerator(
			'redo', self.gui_hotkeys, Gdk.KEY_y,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		self.sourcebuffer.set_implicit_trailing_newline(False)
		self.sourcebuffer.set_max_undo_levels(40)
		self.sourcebuffer.connect('notify::can-undo', self.can_undo_redo)
		self.sourcebuffer.connect('notify::can-redo', self.can_undo_redo)
		self.sourcebuffer.connect_after('undo', self.can_undo_redo, None)
		self.sourcebuffer.connect_after('redo', self.can_undo_redo, None)
		self.sourcebuffer.connect('notify::cursor-position', self.cursor_moved)
		self.sourcebuffer.connect('changed', self.text_inserted)
		self.sourceview.connect('key-press-event', self.insert_with_tags)
		self.sourceview.connect('key-press-event', self.copy_paste_keyboard)
		self.sourceview.connect('populate-popup', self.right_menu)
		self.scrolledsourceview.add(self.sourceview)
		self.add_mnemonic(Gdk.KEY_b, self.sourceview)
		self.language_manager = GtkSource.LanguageManager.get_default()

	def build_tags(self):

		self.sourcebuffer.create_tag('bold', weight=Pango.Weight.BOLD)
		self.sourcebuffer.create_tag('italic', style=Pango.Style.ITALIC)
		self.sourcebuffer.create_tag(
			'underline', underline=Pango.Underline.SINGLE)
		self.sourcebuffer.create_tag('strikethrough', strikethrough=True)
		self.sourcebuffer.create_tag('subscript', rise=-4 * 1024, scale=0.6)
		self.sourcebuffer.create_tag('superscript', rise=4 * 1024, scale=0.6)
		self.sourcebuffer.create_tag(
			'text-align: left', justification=Gtk.Justification.LEFT)
		self.sourcebuffer.create_tag(
			'text-align: center', justification=Gtk.Justification.CENTER)
		self.sourcebuffer.create_tag(
			'text-align: right', justification=Gtk.Justification.RIGHT)
		self.sourcebuffer.create_tag(
			'text-align: justify', justification=Gtk.Justification.FILL)
		self.sourcebuffer.create_tag('private', editable=False, invisible=True)
		self.tagtable = self.sourcebuffer.get_tag_table()

	def build_fields(self):

		hotstring_label = Gtk.Label.new_with_mnemonic('_Abbreviation:')
		hotstring_label.set_xalign(0)
		self.propsgrid.attach_next_to(
			hotstring_label, self.scrolledsourceview,
			Gtk.PositionType.BOTTOM, 8, 1)
		self.hotstring = Gtk.Entry()
		hotstring_label.set_mnemonic_widget(self.hotstring)
		self.propsgrid.attach_next_to(
			self.hotstring, hotstring_label, Gtk.PositionType.BOTTOM, 8, 1)
		trigger_label = Gtk.Label.new_with_mnemonic('_Triggers:')
		trigger_label.set_xalign(0)
		self.propsgrid.attach_next_to(
			trigger_label, self.hotstring, Gtk.PositionType.BOTTOM, 8, 1)
		self.triggers = Gtk.ComboBoxText.new_with_entry()
		self.triggers.append_text('No trigger')
		self.triggers.append_text('Whitespace')
		self.triggers.append_text('Punctuation')
		self.triggers.append_text('Whitespace and Punctuation')
		self.triggers.connect('format-entry-text', self.fill_triggers)
		trigger_label.set_mnemonic_widget(self.triggers)
		self.propsgrid.attach_next_to(
			self.triggers, trigger_label, Gtk.PositionType.BOTTOM, 8, 1)
		method_label = Gtk.Label.new_with_mnemonic('_Send via:')
		method_label.set_xalign(0)
		self.propsgrid.attach_next_to(
			method_label, hotstring_label, Gtk.PositionType.RIGHT, 8, 1)
		self.method = Gtk.ComboBoxText()
		self.method.append_text('Type')
		self.method.append_text('Paste')
		self.method.append_text('Alt. Paste')
		self.method.set_active(1)
		method_label.set_mnemonic_widget(self.method)
		self.propsgrid.attach_next_to(
			self.method, method_label, Gtk.PositionType.BOTTOM, 8, 1)
		class_label = Gtk.Label.new_with_mnemonic('Filter by Window _Class:')
		class_label.set_xalign(0)
		self.propsgrid.attach_next_to(
			class_label, self.triggers, Gtk.PositionType.BOTTOM, 8, 1)
		self.wm_class = Gtk.Entry()
		class_label.set_mnemonic_widget(self.wm_class)
		self.propsgrid.attach_next_to(
			self.wm_class, class_label, Gtk.PositionType.BOTTOM, 7, 1)
		self.class_button = Gtk.ToggleButton()
		if PLATFORM is Platform.WAYLAND:
			self.class_button.set_sensitive(False)
		add2 = Gtk.Image.new_from_icon_name('add', 2)
		self.class_button.set_image(add2)
		self.class_button.connect('toggled', self.pick_class)
		self.propsgrid.attach_next_to(
			self.class_button, self.wm_class, Gtk.PositionType.RIGHT, 1, 1)
		window_label = Gtk.Label.new_with_mnemonic('Filter by Window _Title')
		window_label.set_xalign(0)
		self.propsgrid.attach_next_to(
			window_label, class_label, Gtk.PositionType.RIGHT, 8, 1)
		self.wm_title = Gtk.Entry()
		window_label.set_mnemonic_widget(self.wm_title)
		self.propsgrid.attach_next_to(
			self.wm_title, window_label, Gtk.PositionType.BOTTOM, 7, 1)
		self.window_button = Gtk.ToggleButton()
		if PLATFORM is Platform.WAYLAND:
			self.window_button.set_sensitive(False)
		add1 = Gtk.Image.new_from_icon_name('add', 2)
		self.window_button.set_image(add1)
		self.window_button.connect('toggled', self.pick_window)
		self.propsgrid.attach_next_to(
			self.window_button, self.wm_title, Gtk.PositionType.RIGHT, 1, 1)
		save = Gtk.Button('Save')
		save.add_accelerator(
			'clicked', self.gui_hotkeys, Gdk.KEY_s,
			Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
		save.connect('clicked', self.save_phrase)
		self.propsgrid.attach_next_to(
			save, self.window_button, Gtk.PositionType.BOTTOM, 1, 1)
		cancel = Gtk.Button.new_with_mnemonic('Canc_el')
		cancel.connect('clicked', self.cancel_phrase)
		self.propsgrid.attach_next_to(
			cancel, save, Gtk.PositionType.LEFT, 1, 1)

	def build_hotkeys(self):

		filterbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		filterbox.props.halign = Gtk.Align.CENTER
		self.hotkeybox.pack_start(filterbox, False, False, 0)
		filter_label = Gtk.Label('Filter:')
		filterbox.pack_start(filter_label, False, False, 6)
		self.hotkey_filter = Gtk.Entry()
		self.hotkey_filter.get_style_context().add_class('filterbox')
		self.hotkey_filter.connect(
			'changed', lambda entry: self.filter_hotkeys.refilter())
		filterbox.pack_start(self.hotkey_filter, False, False, 6)
		#                           priority, filepath, name, hotkey string
		self.hotkeystore = Gtk.ListStore(int, str, str, str)
		self.filter_hotkeys = self.hotkeystore.filter_new()
		self.filter_hotkeys.set_visible_func(self.filter_hotkey)
		self.hotkeyview = Gtk.TreeView.new_with_model(self.filter_hotkeys)
		self.hotkeyview.props.halign = Gtk.Align.CENTER
		self.hotkeyview.set_size_request(600, -1)
		self.hotkeyview.set_headers_visible(False)
		self.hotkeyview.set_search_column(2)
		label_renderer = Gtk.CellRendererText()
		label_column = Gtk.TreeViewColumn('Label', label_renderer, text=2)
		label_column.set_expand(True)
		self.hotkeyview.append_column(label_column)
		hotkey_renderer = Gtk.CellRendererAccel()
		hotkey_renderer.set_property('editable', True)
		hotkey_renderer.connect('accel-edited', self.hotkey_edited)
		hotkey_renderer.connect('accel-cleared', self.hotkey_cleared)
		hotkey_column = Gtk.TreeViewColumn('Hotkey', hotkey_renderer, text=3)
		self.hotkeyview.append_column(hotkey_column)
		self.hotkeybox.pack_start(self.hotkeyview, True, True, 0)
		self.keymap = Gdk.Keymap.get_default()
		self.modmap = {
			Key.KEY_SHIFT: Gdk.ModifierType.SHIFT_MASK,
			Key.KEY_CTRL: Gdk.ModifierType.CONTROL_MASK,
			Key.KEY_ALT: Gdk.ModifierType.MOD1_MASK,
			Key.KEY_META: Gdk.ModifierType.SUPER_MASK}

	def build_settings(self):

		settingsbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
		self.settingsgrid.attach(settingsbox, 0, 0, 6, 10)
		phrase_dirbox = Gtk.Box(
			orientation=Gtk.Orientation.HORIZONTAL, spacing=100)
		settingsbox.add(phrase_dirbox)
		phrase_dir_label = Gtk.Label("Phrases' directory")
		phrase_dir_label.set_xalign(0)
		phrase_dirbox.pack_start(phrase_dir_label, True, False, 0)
		phrase_dir_spacer = Gtk.Label('')
		phrase_dirbox.pack_start(phrase_dir_spacer, True, True, 0)
		self.phrase_dir = Gtk.FileChooserButton(
			title="Phrases' Directory",
			action=Gtk.FileChooserAction.SELECT_FOLDER)
		self.phrase_dir.set_create_folders(True)
		phrase_dir_filter = Gtk.FileFilter()
		phrase_dir_filter.add_mime_type('inode/directory')
		self.phrase_dir.add_filter(phrase_dir_filter)
		phrase_dirbox.pack_start(self.phrase_dir, False, False, 0)
		keep_trigbox = Gtk.Box(
			orientation=Gtk.Orientation.HORIZONTAL, spacing=100)
		settingsbox.add(keep_trigbox)
		keep_trig_label = Gtk.Label('Keep trigger after expansion')
		keep_trig_label.set_xalign(0)
		keep_trigbox.pack_start(keep_trig_label, False, False, 0)
		keep_trig_spacer = Gtk.Label('')
		keep_trigbox.pack_start(keep_trig_spacer, True, True, 0)
		self.keep_trig = Gtk.Switch()
		keep_trigbox.pack_start(self.keep_trig, False, False, 0)
		use_tabbox = Gtk.Box(
			orientation=Gtk.Orientation.HORIZONTAL, spacing=100)
		settingsbox.add(use_tabbox)
		use_tab_label = Gtk.Label('Use tab*')
		use_tab_label.set_xalign(0)
		use_tabbox.pack_start(use_tab_label, False, False, 0)
		use_tab_spacer = Gtk.Label('')
		use_tabbox.pack_start(use_tab_spacer, True, True, 0)
		self.use_tab = Gtk.Switch()
		use_tabbox.pack_start(self.use_tab, False, False, 0)
		warn_folderbox = Gtk.Box(
			orientation=Gtk.Orientation.HORIZONTAL, spacing=100)
		settingsbox.add(warn_folderbox)
		warn_folder_label = Gtk.Label('Warn when deleting a folder')
		warn_folder_label.set_xalign(0)
		warn_folderbox.pack_start(warn_folder_label, False, False, 0)
		warn_folder_spacer = Gtk.Label('')
		warn_folderbox.pack_start(warn_folder_spacer, True, True, 0)
		self.warn_folder = Gtk.Switch()
		warn_folderbox.pack_start(self.warn_folder, False, False, 0)
		themebox = Gtk.Box(
			orientation=Gtk.Orientation.HORIZONTAL, spacing=100)
		settingsbox.add(themebox)
		theme_label = Gtk.Label('Use light panel theme')
		theme_label.set_xalign(0)
		themebox.pack_start(theme_label, False, False, 0)
		theme_spacer = Gtk.Label('')
		themebox.pack_start(theme_spacer, True, True, 0)
		self.theme = Gtk.Switch()
		themebox.pack_start(self.theme, False, False, 0)
		experimental_label = Gtk.Label('*Experimental')
		experimental_label.set_xalign(1)
		self.settingsgrid.attach(experimental_label, 4, 10, 2, 1)
		# ~ restart_label = Gtk.Label('**Requires Restart')
		# ~ restart_label.set_xalign(1)
		# ~ self.settingsgrid.attach(restart_label, 4, 11, 2, 1)
		save = Gtk.Button.new_with_label('Save')
		save.connect('clicked', self.save_settings)
		self.settingsgrid.attach(save, 5, 12, 1, 1)
		cancel = Gtk.Button.new_with_label('Cancel')
		cancel.connect('clicked', self.cancel_settings)
		self.settingsgrid.attach(cancel, 4, 12, 1, 1)

	def load_phrases(self):

		seen_paths = {Path('.'): None}
		for fullpath, phrase in self.manager.phrases.items():
			path = Path(phrase.path).parent
			if path in seen_paths:
				self.phrasestore.append(
					seen_paths[path],
					('document', phrase.name, phrase.hotstring,
						self.color_disabled, fullpath))
			else:
				for folder in reversed(path.parents):
					if folder not in seen_paths:
						if folder.parent in seen_paths:
							folder_iter = self.phrasestore.append(
								seen_paths[folder.parent],
								('folder', folder.name, '', self.color_normal,
									''))
							seen_paths[folder] = folder_iter
				tree_iter = self.phrasestore.append(
					seen_paths[path.parent],
					('folder', path.name, '', self.color_normal, ''))
				seen_paths[path] = tree_iter
				self.phrasestore.append(
					tree_iter,
					('document', phrase.name, phrase.hotstring,
						self.color_disabled, fullpath))
		self.sort_phraseview()
		self.check_abbr_conflicts()

	def phrase_selected(self, selection):

		model, tree_iter = selection.get_selected()
		self.propsgrid.set_sensitive(False)
		self.plaintext.set_active(True)
		self.sourcebuffer.begin_not_undoable_action()
		self.sourcebuffer.set_text('')
		self.hotstring.set_text('')
		self.triggers.get_child().set_text('')
		self.method.set_active(1)
		self.wm_class.set_text('')
		self.wm_title.set_text('')
		if tree_iter and model[tree_iter][0] != 'folder':
			self.propsgrid.set_sensitive(True)
			phrase = self.manager.phrases[model[tree_iter][4]]
			if phrase.type is PhraseType.PLAINTEXT:
				self.plaintext.set_active(True)
			elif phrase.type is PhraseType.RICHTEXT:
				self.richtext.set_active(True)
			elif phrase.type is PhraseType.MARKDOWN:
				self.markdown.set_active(True)
			elif phrase.type is PhraseType.COMMAND:
				self.command.set_active(True)
			elif phrase.type is PhraseType.HTML:
				self.html.set_active(True)
			if phrase.type is PhraseType.RICHTEXT:
				self.serializer.deserialize(phrase.body, True)
			else:
				self.sourcebuffer.set_text(phrase.body)
			self.hotstring.set_text(phrase.hotstring)
			self.triggers.get_child().set_text(''.join(
				phrase.triggers).replace('\t', '\\t').replace('\n', '\\n'))
			self.method.set_active(phrase.method.value - 1)
			self.wm_class.set_text(', '.join(phrase.wm_class))
			self.wm_title.set_text(phrase.wm_title)
		self.sourcebuffer.end_not_undoable_action()

	def sort_phraseview(self):

		self.phrasestore.set_sort_column_id(1, Gtk.SortType.ASCENDING)
		self.phrasestore.set_sort_column_id(0, Gtk.SortType.DESCENDING)

	def iter_tree(self, treestore):

		def iter_rows(tree_iter):

			while tree_iter is not None:
				yield tree_iter
				if treestore.iter_has_child(tree_iter):
					child_iter = treestore.iter_children(tree_iter)
					yield from iter_rows(child_iter)
				tree_iter = treestore.iter_next(tree_iter)

		root_iter = treestore.get_iter_first()
		yield from iter_rows(root_iter)

	def check_abbr_conflicts(self):

		seen_abbr = {}
		for tree_iter in self.iter_tree(self.phrasestore):
			abbr = self.phrasestore[tree_iter][2]
			if abbr:
				if abbr in seen_abbr:
					self.phrasestore[seen_abbr[abbr]][3] = self.color_conflict
					self.phrasestore[tree_iter][3] = self.color_conflict
				else:
					seen_abbr[abbr] = tree_iter

	def label_edited(self, renderer, path, text):

		def get_child_phrases(tree_iter):

			child = self.phrasestore.iter_children(tree_iter)
			for i in range(self.phrasestore.iter_n_children(tree_iter)):
				if self.phrasestore[child][0] != 'folder':
					phrases.append((self.phrasestore[child][4], child))
				else:
					get_child_phrases(child)
				child = self.phrasestore.iter_next(child)

		def remove_empty_dirs(parent_dir):

			for filepath in parent_dir.iterdir():
				if filepath.is_dir():
					if remove_empty_dirs(filepath):
						filepath.rmdir()
					else:
						return False
				else:
					return False
			return True

		if text and not text.isspace():
			for char in text:
				if char in RESERVEDCHARS:
					text = text.replace(char, '')
		tree_iter = self.phrasestore.get_iter(path)
		if not self.is_unique(tree_iter, text):
			return
		if text and not text.isspace():
			if self.phrasestore[path][0] != 'folder':
				old_path = self.phrasestore[path][4]
				new_path = str(Path(old_path).with_name(text + '.json'))
				phrase = self.manager.move(str(old_path), str(new_path))
				if not self.client.offline:
					self.client.send(MSG(
						MsgType.MOVE, (str(old_path), str(new_path), phrase)))
			else:
				phrases = []
				child = self.phrasestore.iter_children(tree_iter)
				for i in range(self.phrasestore.iter_n_children(tree_iter)):
					if self.phrasestore[child][0] == 'folder':
						get_child_phrases(child)
					else:
						phrases.append((self.phrasestore[child][4], child))
					child = self.phrasestore.iter_next(child)
				parent = self.phrasestore.iter_parent(tree_iter)
				if parent:
					new_root = Path(self.phrasestore[parent][1])
					for i in range(self.phrasestore.iter_depth(parent)):
						parent = self.phrasestore.iter_parent(parent)
						new_root = self.phrasestore[parent][1] / new_root
					new_root = self.manager.root / new_root
				else:
					new_root = self.manager.root
				old_path = new_root / self.phrasestore[path][1]
				new_root /= text
				for phrasepath, phrase_iter in phrases:
					rel_path = Path(phrasepath).relative_to(old_path)
					new_path = new_root / rel_path
					phrase = self.manager.move(phrasepath, str(new_path))
					if not self.client.offline:
						self.client.send(MSG(
							MsgType.MOVE, (phrasepath, str(new_path), phrase)))
					self.phrasestore[phrase_iter][4] = str(new_path)
				if old_path.exists():
					if not self.manager.root.samefile(old_path):
						empty = True
						for filepath in old_path.iterdir():
							if filepath.is_dir():
								if remove_empty_dirs(filepath):
									filepath.rmdir()
								else:
									empty = False
							else:
								empty = False
						if empty:
							old_path.rmdir()
			self.phrasestore[path][1] = text
			self.sort_phraseview()

	def rename_phrase(self, treeview, event):

		if event.keyval == Gdk.KEY_F2:
			model, tree_iter = self.phraseselection.get_selected()
			if tree_iter:
				tree_path = model.get_path(tree_iter)
				treeview.set_cursor(tree_path, treeview.get_column(1), True)
		return False

	def phrase_select_none(self, treeview, event):

		path = treeview.get_path_at_pos(event.x, event.y)
		if path is None:
			self.phraseselection.unselect_all()
		return False

	def phrase_drag_data_get(self, widget, context, data, info, timestamp):

		model, tree_iter = self.phraseselection.get_selected()
		path = model.get_path(tree_iter)
		string = path.to_string()
		data.set(data.get_target(), 0, string.encode())

	def phrase_drag_data_received(
			self, widget, context, x, y, data, info, timestamp):

		def move_tree(src_iter, dst_iter, new_path, root=True):

			if root:
				root_content = model.get(src_iter, 0, 1)
				dst_iter = model.insert(
					dst_iter, -1, root_content + ('', self.color_normal, ''))
			new_path /= model[src_iter][1]
			src_child_iter = model.iter_children(src_iter)
			while src_child_iter:
				if model[src_child_iter][0] == 'folder':
					child_content = model.get(src_child_iter, 0, 1)
					dst_child_iter = model.insert(
						dst_iter, -1,
						child_content + ('', self.color_normal, ''))
					move_tree(src_child_iter, dst_child_iter, new_path, False)
				else:
					child_content = model.get(src_child_iter, 0, 1, 2)
					phrase_path = new_path / (model[src_child_iter][1] + '.json')
					old_path = model[src_child_iter][4]
					phrase = self.manager.move(old_path, str(phrase_path))
					if not self.client.offline:
						self.client.send(MSG(
							MsgType.MOVE, (old_path, str(phrase_path), phrase)))
					model.insert(
						dst_iter, -1,
						child_content + (self.color_normal, str(phrase_path)))
					remove_empty_dirs(old_path)
				src_child_iter = model.iter_next(src_child_iter)
			if root:
				model.remove(src_iter)

		def remove_empty_dirs(phrase_path):

			path = Path(phrase_path).parent
			while path != self.manager.root:
				if path.exists() and not any(path.iterdir()):
					path.rmdir()
					path = path.parent
				else:
					break

		model = widget.get_model()
		src_iter = model.get_iter_from_string(data.get_data().decode())
		src_name = model[src_iter][1]
		content = model.get(src_iter, 0, 1, 2, 3)
		dst_tuple = widget.get_dest_row_at_pos(x, y)
		if dst_tuple:
			dst_path, dst_pos = dst_tuple
			dst_iter = model.get_iter(dst_path)
			if dst_pos in {Gtk.TreeViewDropPosition.BEFORE,
					Gtk.TreeViewDropPosition.AFTER}:
				dst_iter = model.iter_parent(dst_iter)
			elif model[dst_iter][0] != 'folder':
				dst_iter = model.iter_parent(dst_iter)
		else:
			dst_iter = None
		if dst_iter:
			dst_parent = model.iter_parent(dst_iter)
			if not dst_parent:
				new_path = self.manager.root / model[dst_iter][1]
			else:
				new_path = Path(model[dst_iter][1])
				while dst_parent:
					new_path = model[dst_parent][1] / new_path
					dst_parent = model.iter_parent(dst_parent)
				new_path = self.manager.root / new_path
		else:
			new_path = self.manager.root
		if self.is_unique(dst_iter, src_name):
			if model[src_iter][0] == 'folder':
				move_tree(src_iter, dst_iter, new_path)
			else:
				new_path /= (model[src_iter][1] + '.json')
				old_path = model[src_iter][4]
				phrase = self.manager.move(old_path, str(new_path))
				if not self.client.offline:
					self.client.send(MSG(
						MsgType.MOVE, (old_path, str(new_path), phrase)))
				model.remove(src_iter)
				model.insert(dst_iter, -1, content + (str(new_path), ))
			self.sort_phraseview()
			self.check_abbr_conflicts()

	def is_unique(self, tree_iter, name):

		names = set()
		child = self.phrasestore.iter_children(tree_iter)
		while child:
			names.add(self.phrasestore[child][1])
			child = self.phrasestore.iter_next(child)
		if name in names:
			return False
		return True

	def unique_name(self, tree_iter, name):

		iteration = 1
		while not self.is_unique(tree_iter, name):
			iteration += 1
			if iteration > 2:
				name = '{0} {1}'.format(
					name[:-len(str(iteration)) - 1], iteration)
			else:
				name = '{0} {1}'.format(name, iteration)
		return name

	def new_phrase(self, button):

		model, tree_iter = self.phraseselection.get_selected()
		if tree_iter:
			if model[tree_iter][0] != 'folder':
				tree_iter = model.iter_parent(tree_iter)
		if tree_iter:
			filepath = Path(model[tree_iter][1])
			parent = model.iter_parent(tree_iter)
			while parent:
				filepath = model[parent][1] / filepath
				parent = model.iter_parent(parent)
			filepath = self.manager.root / filepath
		else:
			filepath = self.manager.root
		name = self.unique_name(tree_iter, 'New phrase')
		filepath /= (name + '.json')
		self.manager.add(str(filepath))
		if not self.client.offline:
			self.client.send(MSG(MsgType.ADD, str(filepath)))
		self.phrasestore.append(
			tree_iter, ('document', name, '', self.color_normal, str(filepath)))
		self.sort_phraseview()

	def new_folder(self, button):

		model, tree_iter = self.phraseselection.get_selected()
		if tree_iter:
			if model[tree_iter][0] != 'folder':
				tree_iter = model.iter_parent(tree_iter)
		name = self.unique_name(tree_iter, 'New folder')
		self.phrasestore.append(
			tree_iter, ('folder', name, '', self.color_normal, ''))
		self.sort_phraseview()

	def delete(self, button):

		def remove_children(tree_iter):

			child = model.iter_children(tree_iter)
			while child:
				if model[child][0] == 'folder':
					remove_children(child)
				else:
					filepath = Path(model[child][4])
					self.manager.delete(str(filepath))
					if not self.client.offline:
						self.client.send(MSG(MsgType.DEL, str(filepath)))
					if (filepath.parent.exists
							and not any(filepath.parent.iterdir())):
						filepath.parent.rmdir()
				child = model.iter_next(child)

		model, tree_iter = self.phraseselection.get_selected()
		if tree_iter:
			if model[tree_iter][0] != 'folder':
				filepath = Path(model[tree_iter][4])
				self.manager.delete(str(filepath))
				if not self.client.offline:
					self.client.send(MSG(MsgType.DEL, str(filepath)))
				if (filepath.parent.exists()
						and not any(filepath.parent.iterdir())):
					filepath.parent.rmdir()
				model.remove(tree_iter)
			else:
				if self.settings.getbool('warn_folder'):
					dialog = FolderWarning()
					response = dialog.run()
					dialog.destroy()
					if response == Gtk.ResponseType.CANCEL:
						return
				remove_children(tree_iter)
				model.remove(tree_iter)

	def type_changed(self, button, phrase_type):

		if button.get_active():
			start, end = self.sourcebuffer.get_bounds()
			if phrase_type == 'plaintext':
				self.richrevealer.set_reveal_child(False)
				if self.last_type == 'richtext':
					html = self.serializer.serialize(start, end)
					text = self.extractor.extract(html, False)
					self.sourcebuffer.set_text(text)
				elif self.last_type == 'markdown':
					markdown = self.sourcebuffer.get_text(start, end, False)
					html = self.md_converter.convert(markdown)
					plaintext = self.extractor.extract(html, False)
					self.sourcebuffer.set_text(plaintext)
				elif self.last_type == 'html':
					html = self.sourcebuffer.get_text(start, end, False)
					plaintext = self.extractor.extract(html, False)
					self.sourcebuffer.set_text(plaintext)
				self.set_syntax_highlighting(None, False)
			elif phrase_type == 'richtext':
				self.richrevealer.set_reveal_child(True)
				if self.last_type == 'markdown':
					markdown = self.sourcebuffer.get_text(start, end, False)
					html = self.md_converter.convert(markdown)
					self.sourcebuffer.set_text('')
					self.serializer.deserialize(html, True)
				elif self.last_type == 'html':
					html = self.sourcebuffer.get_text(start, end, False)
					self.sourcebuffer.set_text('')
					self.serializer.deserialize(html, True)
				self.set_syntax_highlighting(None, False)
			elif phrase_type == 'markdown':
				self.richrevealer.set_reveal_child(False)
				if self.last_type == 'richtext':
					html = self.serializer.serialize(start, end)
					plaintext = self.extractor.extract(html, False)
					self.sourcebuffer.set_text(plaintext)
				self.set_syntax_highlighting('md', True)
			elif phrase_type == 'command':
				self.richrevealer.set_reveal_child(False)
				if self.last_type == 'richtext':
					html = self.serializer.serialize(start, end)
					plaintext = self.extractor.extract(html, False)
					self.sourcebuffer.set_text(plaintext)
				self.set_syntax_highlighting('sh', True)
			elif phrase_type == 'html':
				self.richrevealer.set_reveal_child(False)
				if self.last_type == 'richtext':
					html = self.serializer.serialize(start, end)
					self.sourcebuffer.set_text(html)
				elif self.last_type == 'markdown':
					markdown = self.sourcebuffer.get_text(start, end, False)
					html = self.md_converter.convert(markdown)
					self.sourcebuffer.set_text(html)
				self.set_syntax_highlighting('html', True)
		else:
			self.last_type = phrase_type

	def set_syntax_highlighting(self, language, highlight):

		if language:
			language = self.language_manager.get_language(language)
		self.sourcebuffer.set_language(language)
		self.sourcebuffer.set_highlight_matching_brackets(highlight)
		self.sourcebuffer.set_highlight_syntax(highlight)
		self.sourceview.set_auto_indent(highlight)
		self.sourceview.set_highlight_current_line(highlight)
		self.sourceview.set_show_line_numbers(highlight)
		self.sourceview.set_smart_home_end(1 if highlight else 0)
		self.sourceview.set_monospace(highlight)

	def can_undo_redo(self, sourcebuffer, pspec):

		if sourcebuffer.can_undo():
			self.undo.set_sensitive(True)
		else:
			self.undo.set_sensitive(False)
		if sourcebuffer.can_redo():
			self.redo.set_sensitive(True)
		else:
			self.redo.set_sensitive(False)

	def sourceview_undo(self, button):

		self.sourcebuffer.undo()

	def sourceview_redo(self, button):

		self.sourcebuffer.redo()

	def wrap_text(self, button):

		if button.get_active():
			self.sourceview.set_wrap_mode(Gtk.WrapMode.WORD)
		else:
			self.sourceview.set_wrap_mode(Gtk.WrapMode.NONE)

	def richtoolbutton(self, button, action, subaction):

		selection = self.sourcebuffer.get_selection_bounds()
		if selection:
			start, end = selection
			if action == 'clear':
				for btn in self.simpletags.values():
					btn.set_active(False)
				self.font.set_font('')
				self.foreground_color.set_rgba(self.color_black)
				self.background_color.set_rgba(self.color_white)
				self.align_left.set_active(True)
				self.sourcebuffer.remove_all_tags(start, end)
				line_no = start.get_line()
				line_start = self.sourcebuffer.get_iter_at_line(line_no)
				if not end.is_end():
					end.forward_to_line_end()
				self.remove_partial_tags('text-align', line_start, end)
				self.opentags = set()
			elif action in self.simpletags:
				text_tag = self.tagtable.lookup(action)
				state = button.get_active()
				if start.has_tag(text_tag) and not state:
					self.sourcebuffer.remove_tag(text_tag, start, end)
				else:
					self.sourcebuffer.apply_tag(text_tag, start, end)
			elif action == 'font':
				font_str = button.get_font_name()
				name = 'font=' + font_str
				text_tag = self.tagtable.lookup(name)
				if not text_tag:
					text_tag = self.sourcebuffer.create_tag(name, font=font_str)
				self.remove_partial_tags('font', start, end)
				self.sourcebuffer.apply_tag(text_tag, start, end)
			elif action == 'foreground':
				rgba = button.get_rgba()
				red = int(rgba.red * 255)
				green = int(rgba.green * 255)
				blue = int(rgba.blue * 255)
				name = 'foreground=rgb({0}, {1}, {2})'.format(red, green, blue)
				text_tag = self.tagtable.lookup(name)
				if (red, green, blue) != (0, 0, 0):
					if not text_tag:
						text_tag = self.sourcebuffer.create_tag(
							name, foreground_rgba=rgba)
					self.remove_partial_tags('foreground', start, end)
					self.sourcebuffer.apply_tag(text_tag, start, end)
				else:
					self.remove_partial_tags('foreground', start, end)
			elif action == 'background':
				rgba = button.get_rgba()
				red = int(rgba.red * 255)
				green = int(rgba.green * 255)
				blue = int(rgba.blue * 255)
				name = 'background=rgb({0}, {1}, {2})'.format(red, green, blue)
				text_tag = self.tagtable.lookup(name)
				if (red, green, blue) != (255, 255, 255):
					if not text_tag:
						text_tag = self.sourcebuffer.create_tag(
							name, background_rgba=rgba)
					self.remove_partial_tags('background', start, end)
					self.sourcebuffer.apply_tag(text_tag, start, end)
				else:
					self.remove_partial_tags('background', start, end)
			elif action == 'text-align':
				if button.get_active():
					text_tag = self.tagtable.lookup('text-align: ' + subaction)
					line_no = start.get_line()
					line_start = self.sourcebuffer.get_iter_at_line(line_no)
					if not end.ends_line():
						end.forward_to_line_end()
					self.remove_partial_tags('text-align', line_start, end)
					self.sourcebuffer.apply_tag(text_tag, line_start, end)
					try:
						align_tag = next(tag for tag in self.opentags
							if tag.props.name.startswith('text-align'))
						self.opentags.remove(align_tag)
					except StopIteration:
						pass
					self.opentags.add(text_tag)
			elif action == 'link':
				title = self.sourcebuffer.get_text(start, end, False)
				self.sourcebuffer.delete_interactive(start, end, True)
				self.link_insert(end, title)
			elif action == 'image':
				self.sourcebuffer.delete_interactive(start, end, True)
				self.image_insert(end)
		else:
			cursor = self.sourcebuffer.get_insert()
			text_iter = self.sourcebuffer.get_iter_at_mark(cursor)
			if action == 'clear':
				for btn in self.simpletags.values():
					btn.set_active(False)
				self.font.set_font('')
				self.foreground_color.set_rgba(self.color_black)
				self.background_color.set_rgba(self.color_white)
				self.align_left.set_active(True)
				line_no = text_iter.get_line()
				line_start = self.sourcebuffer.get_iter_at_line(line_no)
				if not text_iter.is_end():
					text_iter.forward_to_line_end()
				self.remove_partial_tags('text-align', line_start, text_iter)
				self.opentags = set()
			elif action in self.simpletags:
				state = button.get_active()
				text_tag = self.tagtable.lookup(action)
				if text_tag in self.opentags and not state:
					self.opentags.remove(text_tag)
				else:
					self.opentags.add(text_tag)
			elif action == 'font':
				font_str = button.get_font_name()
				name = 'font=' + font_str
				text_tag = self.tagtable.lookup(name)
				if not text_tag:
					text_tag = self.sourcebuffer.create_tag(name, font=font_str)
				try:
					font_tag = next(tag for tag in self.opentags
						if tag.props.name.startswith('font'))
					self.opentags.remove(font_tag)
				except StopIteration:
					pass
				self.opentags.add(text_tag)
			elif action == 'foreground':
				try:
					foreground_tag = next(tag for tag in self.opentags
						if tag.props.name.startswith('foreground'))
					self.opentags.remove(foreground_tag)
				except StopIteration:
					pass
				rgba = button.get_rgba()
				red = int(rgba.red * 255)
				green = int(rgba.green * 255)
				blue = int(rgba.blue * 255)
				name = 'foreground=rgb({0}, {1}, {2})'.format(red, green, blue)
				if (red, green, blue) != (0, 0, 0):
					text_tag = self.tagtable.lookup(name)
					if not text_tag:
						text_tag = self.sourcebuffer.create_tag(
							name, foreground_rgba=rgba)
					self.opentags.add(text_tag)
			elif action == 'background':
				try:
					background_tag = next(tag for tag in self.opentags
						if tag.props.name.startswith('background'))
					self.opentags.remove(background_tag)
				except StopIteration:
					pass
				rgba = button.get_rgba()
				red = int(rgba.red * 255)
				green = int(rgba.green * 255)
				blue = int(rgba.blue * 255)
				name = 'background=rgb({0}, {1}, {2})'.format(red, green, blue)
				if (red, green, blue) != (255, 255, 255):
					text_tag = self.tagtable.lookup(name)
					if not text_tag:
						text_tag = self.sourcebuffer.create_tag(
							name, background_rgba=rgba)
					self.opentags.add(text_tag)
			elif action == 'text-align':
				if button.get_active():
					text_tag = self.tagtable.lookup('text-align: ' + subaction)
					line_no = text_iter.get_line()
					line_start = self.sourcebuffer.get_iter_at_line(line_no)
					if not text_iter.ends_line():
						text_iter.forward_to_line_end()
					self.remove_partial_tags(
						'text-align', line_start, text_iter)
					self.sourcebuffer.apply_tag(text_tag, line_start, text_iter)
					try:
						align_tag = next(tag for tag in self.opentags
							if tag.props.name.startswith('text-align'))
						self.opentags.remove(align_tag)
					except StopIteration:
						pass
					self.opentags.add(text_tag)
			elif action == 'link':
				self.link_insert(text_iter, None)
			elif action == 'image':
				self.image_insert(text_iter)
		self.sourceview.grab_focus()

	def remove_partial_tags(self, partial, start, end):

		tag_iter = start.copy()
		tags = tag_iter.get_tags()
		while tag_iter.compare(end) < 0:
			tag_iter.forward_to_tag_toggle()
			tags += tag_iter.get_toggled_tags(True)
		for tag in (tag for tag in tags if tag.props.name.startswith(partial)):
			self.sourcebuffer.remove_tag(tag, start, end)

	def filter_fonts(self, family, face, udata):

		if face.get_face_name() != 'Regular':
			return False
		else:
			return True

	def link_insert(self, text_iter, title):

		dialog = InsertLink(self, title)
		response = dialog.run()
		if response == Gtk.ResponseType.OK:
			is_text, title, url = dialog.get_link()
			if is_text:
				link = Gtk.LinkButton.new_with_label(url, title)
			else:
				link = Gtk.LinkButton.new(url)
				image = Gtk.Image.new_from_file(title)
				link.set_image(image)
				link.props.always_show_image = True
				link.set_label('')
			link.get_style_context().add_class('text_link')
			link.show()
			anchor = self.sourcebuffer.create_child_anchor(text_iter)
			self.sourceview.add_child_at_anchor(link, anchor)
		dialog.destroy()

	def image_insert(self, text_iter):

		dialog = InsertImage(self)
		response = dialog.run()
		if response == Gtk.ResponseType.OK:
			image = dialog.get_image()
			if image:
				pixbuf = GdkPixbuf.Pixbuf.new_from_file(image)
				pixbuf.path = image
				self.sourcebuffer.insert_pixbuf(text_iter, pixbuf)
		dialog.destroy()

	def cursor_moved(self, sourcebuffer, pspec):

		if self.richtext.get_active():
			simpledct = {name: False for name in self.simpletags}
			font_set = False
			foreground_set = False
			background_set = False
			text_align_set = False
			if (not self.sourcebuffer.props.has_selection
					and not self.body_insert):
				cursor = self.sourcebuffer.get_insert()
				text_iter = self.sourcebuffer.get_iter_at_mark(cursor)
				text_tags = set(text_iter.get_tags())
				end_tags = set(text_iter.get_toggled_tags(False))
				found_tags = text_tags | end_tags
				for tag in found_tags:
					if tag.props.name in self.simpletags:
						self.simpletags[tag.props.name].set_active(True)
						if tag in end_tags:
							self.opentags.add(tag)
						simpledct[tag.props.name] = True
					elif tag.props.name.startswith('font'):
						font = tag.props.name.replace('font=', '')
						self.font.set_font_name(font)
						if tag in end_tags:
							self.opentags.add(tag)
						font_set = True
					elif tag.props.name.startswith('foreground'):
						color = tag.props.name.replace('foreground=', '')
						rgba = Gdk.RGBA()
						rgba.parse(color)
						self.foreground_color.set_rgba(rgba)
						if tag in end_tags:
							self.opentags.add(tag)
						foreground_set = True
					elif tag.props.name.startswith('background'):
						color = tag.props.name.replace('background=', '')
						rgba = Gdk.RGBA()
						rgba.parse(color)
						self.background_color.set_rgba(rgba)
						if tag in end_tags:
							self.opentags.add(tag)
						background_set = True
					elif tag.props.name.startswith('text-align'):
						alignment = tag.props.name.replace('text-align: ', '')
						getattr(
							self, 'align_{}'.format(alignment)).set_active(True)
						if tag in end_tags:
							self.opentags.add(tag)
						text_align_set = True
				for name, value in simpledct.items():
					if not value:
						self.simpletags[name].set_active(False)
						try:
							tag = next(tag for tag in self.opentags
								if tag.props.name == name)
							self.opentags.remove(tag)
						except StopIteration:
							pass
				if not font_set:
					self.font.set_font_name('')
					try:
						tag = next(tag for tag in self.opentags
							if tag.props.name.startswith('font'))
						self.opentags.remove(tag)
					except StopIteration:
						pass
				if not foreground_set:
					self.foreground_color.set_rgba(self.color_black)
					try:
						tag = next(tag for tag in self.opentags
							if tag.props.name.startswith('foreground'))
						self.opentags.remove(tag)
					except StopIteration:
						pass
				if not background_set:
					self.background_color.set_rgba(self.color_white)
					try:
						tag = next(tag for tag in self.opentags
							if tag.props.name.startswith('background'))
						self.opentags.remove(tag)
					except StopIteration:
						pass
				if not text_align_set:
					self.align_left.set_active(True)
					line_no = text_iter.get_line()
					line_start = self.sourcebuffer.get_iter_at_line(line_no)
					if not text_iter.ends_line():
						text_iter.forward_to_line_end()
					tag = self.tagtable.lookup('text-align: left')
					self.sourcebuffer.remove_tag(tag, line_start, text_iter)
					try:
						tag = next(tag for tag in self.opentags
							if tag.props.name.startswith('text-align'))
						self.opentags.remove(tag)
					except StopIteration:
						pass
			elif (self.sourcebuffer.props.has_selection
					and not self.body_insert):
				start, end = self.sourcebuffer.get_selection_bounds()
				found_tags = set(start.get_tags())
				while start.compare(end) < 0:
					start.forward_to_tag_toggle(None)
					found_tags |= set(start.get_tags())
				for tag in found_tags:
					if tag.props.name in self.simpletags:
						self.simpletags[tag.props.name].set_active(True)
						simpledct[tag.props.name] = True
					elif tag.props.name.startswith('font'):
						font = tag.props.name.replace('font=', '')
						self.font.set_font_name(font)
						font_set = True
					elif tag.props.name.startswith('foreground'):
						color = tag.props.name.replace('foreground=', '')
						rgba = Gdk.RGBA()
						rgba.parse(color)
						self.foreground_color.set_rgba(rgba)
						foreground_set = True
					elif tag.props.name.startswith('background'):
						color = tag.props.name.replace('background=', '')
						rgba = Gdk.RGBA()
						rgba.parse(color)
						self.background_color.set_rgba(rgba)
						background_set = True
					elif tag.props.name.startswith('text-align'):
						alignment = tag.props.name.replace('text-align: ', '')
						getattr(self, 'align_{}'.format(
							alignment)).set_active(True)
						text_align_set = True
				for name, value in simpledct.items():
					if not value:
						self.simpletags[name].set_active(False)
				if not font_set:
					self.font.set_font_name('')
				if not foreground_set:
					self.foreground_color.set_rgba(self.color_black)
				if not background_set:
					self.background_color.set_rgba(self.color_white)
				if not text_align_set:
					self.align_left.set_active(True)
		self.body_insert = False

	def text_inserted(self, sourcebuffer):

		self.body_insert = True

	def insert_with_tags(self, sourceview, event):

		string = chr(Gdk.keyval_to_unicode(event.keyval))
		if ((string.isprintable() or string.isspace())
				and self.opentags
				and (event.state & 8) != 8
				and (event.state & 4) != 4
				and (event.state & 67108864) != 67108864):
			cursor = self.sourcebuffer.get_insert()
			if self.sourcebuffer.get_has_selection():
				start, end = self.sourcebuffer.get_selection_bounds()
				self.sourcebuffer.delete_interactive(start, end, True)
				self.sourcebuffer.place_cursor(end)
			text_iter = self.sourcebuffer.get_iter_at_mark(cursor)
			self.sourcebuffer.insert_with_tags(
				text_iter, string, *self.opentags)
			return True
		return False

	def copy_paste_keyboard(self, sourceview, event):

		text, html = Clipboard.get_with_rich_text()
		if html:
			if (event.keyval == Gdk.KEY_v
					and event.state & Gdk.ModifierType.CONTROL_MASK
					and not event.state & Gdk.ModifierType.SHIFT_MASK
					and self.richtext.get_active()):
				bounds = self.sourcebuffer.get_selection_bounds()
				if bounds:
					self.sourcebuffer.delete_interactive(*bounds, True)
				self.serializer.deserialize(html, False)
				return True
		elif (event.keyval == Gdk.KEY_c
				and event.state & Gdk.ModifierType.CONTROL_MASK
				and not event.state & Gdk.ModifierType.SHIFT_MASK
				and self.richtext.get_active()):
			bounds = self.sourcebuffer.get_selection_bounds()
			if bounds:
				html = self.serializer.serialize(*bounds)
				text = self.extractor.extract(html, False)
				Clipboard.set_with_rich_text(text, html)
				return True
		elif (event.keyval == Gdk.KEY_x
				and event.state & Gdk.ModifierType.CONTROL_MASK
				and not event.state & Gdk.ModifierType.SHIFT_MASK
				and self.richtext.get_active()):
			bounds = self.sourcebuffer.get_selection_bounds()
			if bounds:
				html = self.serializer.serialize(*bounds)
				text = self.extractor.extract(html, False)
				self.sourcebuffer.delete_interactive(*bounds, True)
				Clipboard.set_with_rich_text(text, html)
				return True
		return False

	def right_menu(self, sourceview, popup):

		if self.richtext.get_active() and type(popup) is Gtk.Menu:
			children = popup.get_children()
			popup.remove(children[2])     # _Paste
			popup.remove(children[1])     # _Copy
			popup.remove(children[0])     # Cu_t
			paste = Gtk.MenuItem.new_with_mnemonic('_Paste')
			paste.connect('activate', self.paste_menu, children[2])
			paste.show()
			popup.insert(paste, 0)
			paste_wo_format = Gtk.MenuItem.new_with_mnemonic(
				'Paste w/o _Formatting')
			paste_wo_format.connect(
				'activate', lambda mi: children[2].activate())
			paste_wo_format.show()
			popup.insert(paste_wo_format, 1)
			copy = Gtk.MenuItem.new_with_mnemonic('_Copy')
			copy.connect('activate', self.copy_menu, children[1])
			copy.show()
			if not self.sourcebuffer.get_selection_bounds():
				copy.set_sensitive(False)
			popup.insert(copy, 0)
			cut = Gtk.MenuItem.new_with_mnemonic('Cu_t')
			cut.connect('activate', self.cut_menu, children[0])
			cut.show()
			if not self.sourcebuffer.get_selection_bounds():
				cut.set_sensitive(False)
			popup.insert(cut, 0)

	def paste_menu(self, menu_item, default):

		text, html = Clipboard.get_with_rich_text()
		if html and self.richtext.get_active():
			bounds = self.sourcebuffer.get_selection_bounds()
			if bounds:
				self.sourcebuffer.delete_interactive(*bounds, True)
			self.serializer.deserialize(html, False)
			return
		default.activate()

	def copy_menu(self, menu_item, default):

		if self.richtext.get_active():
			bounds = self.sourcebuffer.get_selection_bounds()
			if bounds:
				html = self.serializer.serialize(*bounds)
				text = self.extractor.extract(html, False)
				Clipboard.set_with_rich_text(text, html)
				return
		default.activate()

	def cut_menu(self, menu_item, default):

		if self.richtext.get_active():
			bounds = self.sourcebuffer.get_selection_bounds()
			if bounds:
				html = self.serializer.serialize(*bounds)
				text = self.extractor.extract(html, False)
				self.sourcebuffer.delete_interactive(*bounds, True)
				Clipboard.set_with_rich_text(text, html)
				return
		default.activate()

	def fill_triggers(self, combo, pathstr):

		model = combo.get_model()
		tree_iter = model.get_iter_from_string(pathstr)
		action = model[tree_iter][0]
		if action == 'No trigger':
			return ''
		elif action == 'Whitespace':
			return '\\t \\n'
		elif action == 'Punctuation':
			return '''.,!?;:'"()[]{}<>-_+=/\\*`~'''
		elif action == 'Whitespace and Punctuation':
			return '''\\t \\n.,!?;:'"()[]{}<>-_+=/\\*`~'''

	def pick_class(self, button):

		if button.get_active():
			self.pointer_grab_class = True
			Gdk.pointer_grab(
				self.get_window(), True, Gdk.EventMask.BUTTON_PRESS_MASK,
				None, None, Gdk.CURRENT_TIME)

	def pick_window(self, button):

		if button.get_active():
			self.pointer_grab_title = True
			Gdk.pointer_grab(
				self.get_window(), True, Gdk.EventMask.BUTTON_PRESS_MASK,
				None, None, Gdk.CURRENT_TIME)

	def button_pressed(self, window, event):

		if self.pointer_grab_class:
			window = Window.get_under_pointer()
			if window and window.wm_class not in {'xpander-gui.Xpander-gui'}:
				classes = self.wm_class.get_text()
				if classes:
					self.wm_class.set_text(classes + ', ' + window.wm_class)
				else:
					self.wm_class.set_text(window.wm_class)
			Gdk.pointer_ungrab(Gdk.CURRENT_TIME)
			self.pointer_grab_class = False
			self.class_button.set_active(False)
			return True
		elif self.pointer_grab_title:
			window = Window.get_under_pointer()
			if (window and window.title
					not in {'Phrase Editor', 'Phrase Editor : Offline'}):
				self.wm_title.set_text(window.title)
			Gdk.pointer_ungrab(Gdk.CURRENT_TIME)
			self.pointer_grab_title = False
			self.window_button.set_active(False)
			return True
		return False

	def cancel_phrase(self, button):

		model, tree_iter = self.phraseselection.get_selected()
		phrase = self.manager.phrases[model[tree_iter][4]]
		if phrase.type is PhraseType.PLAINTEXT:
			self.plaintext.set_active(True)
		elif phrase.type is PhraseType.RICHTEXT:
			self.richtext.set_active(True)
		elif phrase.type is PhraseType.MARKDOWN:
			self.markdown.set_active(True)
		elif phrase.type is PhraseType.COMMAND:
			self.command.set_active(True)
		elif phrase.type is PhraseType.HTML:
			self.html.set_active(True)
		if phrase.type is PhraseType.RICHTEXT:
			self.serializer.deserialize(phrase.body, True)
		else:
			self.sourcebuffer.set_text(phrase.body)
		self.hotstring.set_text(phrase.hotstring)
		self.triggers.get_child().set_text(''.join(
			phrase.triggers).replace('\t', '\\t').replace('\n', '\\n'))
		self.method.set_active(phrase.method.value - 1)
		self.wm_class.set_text(', '.join(phrase.wm_class))
		self.wm_title.set_text(phrase.wm_title)

	def save_phrase(self, button):

		model, tree_iter = self.phraseselection.get_selected()
		filepath = model[tree_iter][4]
		phrasetype = None
		for btn, member in self.types.items():
			if btn.get_active():
				phrasetype = member
				break
		bounds = self.sourcebuffer.get_bounds()
		if phrasetype is PhraseType.RICHTEXT:
			body = self.serializer.serialize(*bounds)
		else:
			body = self.sourcebuffer.get_text(*bounds, False)
		hotstring = self.hotstring.get_text()
		triggers = tuple(self.triggers.get_active_text(
			).replace('\\n', '\n').replace('\\t', '\t'))
		method = PasteMethod(self.method.get_active() + 1)
		wm_class = []
		for cls in self.wm_class.get_text().split(','):
			cls = cls.strip()
			if cls:
				wm_class.append(cls)
		wm_title = self.wm_title.get_text()
		old_phrase = self.manager.phrases[filepath]
		new_phrase = Phrase(
			hotstring, triggers, phrasetype, body, method, wm_class, wm_title,
			old_phrase.hotkey)
		self.manager.edit(
			filepath, hotstring, triggers, phrasetype, body, method,
			wm_class, wm_title)
		if not self.client.offline:
			self.client.send(MSG(MsgType.EDIT, (filepath, new_phrase)))
		model[tree_iter][2] = hotstring

	def stack_switched(self, button):

		if button.get_active():
			label = button.get_child().get_label()
			if label == 'Hotkeys':
				self.load_hotkeys()
			elif label == 'Settings':
				self.load_settings()

	def load_hotkeys(self):

		def parse_hotkey(key, mods):

			gdkkey = Gdk.KeymapKey()
			gdkkey.keycode = key.ec.value + 8
			gdkkey.group = 0
			gdkkey.level = 0
			keyval = self.keymap.lookup_key(gdkkey)
			state = Gdk.ModifierType(0)
			for mod in mods:
				state |= self.modmap[mod]
			return keyval, state

		self.hotkeystore.clear()

		pause_key = Gtk.accelerator_name(
			*parse_hotkey(*self.settings.getkey('pause')))
		self.hotkeystore.append((0, 'pause', 'Pause Expansion', pause_key))
		manager_key = Gtk.accelerator_name(
			*parse_hotkey(*self.settings.getkey('manager')))
		self.hotkeystore.append((1, 'manager', 'Show Editor', manager_key))

		for filepath, phrase in self.manager.phrases.items():
			if phrase.hotkey:
				hotkeystr = Gtk.accelerator_name(*parse_hotkey(*phrase.hotkey))
			else:
				hotkeystr = ''
			self.hotkeystore.append((5, filepath, phrase.name, hotkeystr))

		self.hotkeystore.set_sort_column_id(2, Gtk.SortType.ASCENDING)
		self.hotkeystore.set_sort_column_id(0, Gtk.SortType.ASCENDING)

	def hotkey_edited(self, renderer, pathstr, keyval, modmask, xkeycode):

		def parse_hotkey(xkeycode, modmask):

			key = Key.from_ec(xkeycode - 8)
			mods = []
			if modmask & Gdk.ModifierType.SHIFT_MASK:
				mods.append(Key.KEY_SHIFT)
			if modmask & Gdk.ModifierType.CONTROL_MASK:
				mods.append(Key.KEY_CTRL)
			if modmask & Gdk.ModifierType.MOD1_MASK:
				mods.append(Key.KEY_ALT)
			if modmask & Gdk.ModifierType.SUPER_MASK:
				mods.append(Key.KEY_META)
			return key, tuple(mods)

		hotkeystr = Gtk.accelerator_name(keyval, modmask)
		is_unique = True
		for row in self.hotkeystore:
			if row[3] == hotkeystr:
				is_unique = False
		if is_unique:
			priority = self.hotkeystore[pathstr][0]
			hotkey = parse_hotkey(xkeycode, modmask)
			filepath = self.hotkeystore[pathstr][1]
			if priority < 2:
				self.settings.setkey(filepath, hotkey)
				self.settings.save()
				if not self.client.offline:
					self.client.send(MSG(MsgType.SETTINGS, None))
			else:
				self.manager.set_hotkey(filepath, hotkey)
				if not self.client.offline:
					self.client.send(MSG(MsgType.HOTKEY, (filepath, hotkey)))
			self.hotkeystore[pathstr][3] = hotkeystr

	def hotkey_cleared(self, renderer, pathstr):

		priority = self.hotkeystore[pathstr][0]
		filepath = self.hotkeystore[pathstr][1]
		if priority < 2:
			self.settings.setkey(filepath, None)
			self.settings.save()
			if not self.client.offline:
				self.client.send(MSG(MsgType.SETTINGS, None))
		else:
			self.manager.set_hotkey(filepath, None)
			if not self.client.offline:
				self.client.send(MSG(MsgType.HOTKEY, (filepath, None)))
		self.hotkeystore[pathstr][3] = ''

	def filter_hotkey(self, model, tree_iter, data):

		if model[tree_iter][2].startswith(self.hotkey_filter.get_text()):
			return True
		return False

	def load_settings(self):

		phrase_dir = Path(
			self.settings.getstr('phrase_dir')).expanduser().resolve()
		self.phrase_dir.set_filename(str(phrase_dir))
		self.keep_trig.set_active(self.settings.getbool('keep_trig'))
		self.use_tab.set_active(self.settings.getbool('use_tab'))
		self.warn_folder.set_active(self.settings.getbool('warn_folder'))
		self.theme.set_active(self.settings.getbool('light_theme'))

	def save_settings(self, button):

		phrase_dir = Path(self.phrase_dir.get_filename())
		try:
			phrase_dir = '~' / phrase_dir.relative_to(Path.home())
		except ValueError:
			pass
		self.settings.setstr('phrase_dir', str(phrase_dir))
		self.settings.setbool('keep_trig', self.keep_trig.get_active())
		self.settings.setbool('use_tab', self.use_tab.get_active())
		self.settings.setbool('warn_folder', self.warn_folder.get_active())
		self.settings.setbool('light_theme', self.theme.get_active())
		self.settings.save()
		if not self.client.offline:
			self.client.send(MSG(MsgType.SETTINGS, None))
		else:
			self.manager.reload_phrases()
			self.phrasestore.clear()
			self.load_phrases()

	def cancel_settings(self, button):

		self.load_settings()

	def process_msg(self, msg):

		if msg.type is MsgType.EXIT:
			self.client.close()
			self.mainloop.quit()
		elif msg.type is MsgType.SETTINGS:
			self.settings.reload()
			self.manager.reload_phrases()
			self.phrasestore.clear()
			self.load_phrases()
