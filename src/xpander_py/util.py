from macpy import Window
from .server import Server


def listWindows():
	windowList = []
	for window in Window.list_windows():
		windowList.append({'class': window.wm_class, 'title': window.title})
	Server.send({'type': 'manager', 'action': 'listWindows', 'list': windowList})
