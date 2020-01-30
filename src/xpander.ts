import * as fs from "fs";
import * as path from "path";
import { app, ipcMain, BrowserWindow, Menu, MenuItemConstructorOptions, Tray } from "electron";
import { PythonShell } from "python-shell";
import * as ini from "ini";
import Xdg from "xdg-app-paths";
import * as PKG from "../package.json";


const SHELL = new PythonShell("src/xpander.py", {
	mode: "json",
	pythonOptions: ["-u"],
	stderrParser: (line) => JSON.stringify(line),
});
const xdg = Xdg({ name: PKG.name, suffix: "", isolated: true });
let TRAY_MENU: Menu | null;
let TRAY: Tray | null;
let MANAGER_WINDOW: BrowserWindow | null;
let ABOUT_WINDOW: BrowserWindow | null;
let PAUSE: boolean = false;
let Settings = loadSettings();


function loadSettings() {
	return ini.parse(fs.readFileSync(path.join(xdg.config(), 'settings.ini'), 'utf-8'));
}


function createTray() {
	let template: MenuItemConstructorOptions[] = [
		{ id: "pause", label: "Pause expansion", type: "checkbox", checked: false, click: () => {
			SHELL.send({ "type": "main", "action": "pause", "state": null })
		} },
		{ id: "manager", label: "Manager", click: () => {
			managerWindow();
		} },
		{ id: "about", label: "About", click: () => {
			aboutWindow();
		} },
		{ id: "quit", label: "Quit", click: () => {
			SHELL.send({ "type": "main", "action": "exit" });
			SHELL.end((err, code, signal) => { console.log(err, code, signal); });
			setTimeout(() => {
				SHELL.terminate();
				app.quit();
			}, 750);
		} },
	];
	let theme = Settings.DEFAULT.light_theme === "True" ? "light" : "dark";
	let icon = `src/static/icons/xpander-gui-${PAUSE ? "inactive" : "active"}-${theme}.png`;
	TRAY_MENU = Menu.buildFromTemplate(template);

	TRAY = new Tray(icon);
	TRAY.setContextMenu(TRAY_MENU);
}


function fillinWindow() {
	const window = new BrowserWindow({
		width: 550,
		height: 400,
		webPreferences: {
			nodeIntegration: true,
		},
		resizable: false,
		alwaysOnTop: true,
		fullscreenable: false,
		skipTaskbar: true,
		icon: "src/static/icons/xpander-gui.png",
	});
	// window.removeMenu();
	return window;
}


function managerWindow() {
	if (!MANAGER_WINDOW) {
		MANAGER_WINDOW = new BrowserWindow({
			width: 1000,
			height: 600,
			webPreferences: {
				nodeIntegration: true,
			},
			icon: "src/static/icons/xpander-gui.png",
		});
		MANAGER_WINDOW.removeMenu();
		MANAGER_WINDOW.loadFile("src/static/manager.html");
		MANAGER_WINDOW.once("closed", () => MANAGER_WINDOW = null);
	}
	return MANAGER_WINDOW;
}


function aboutWindow() {
	if (!ABOUT_WINDOW) {
		ABOUT_WINDOW = new BrowserWindow({
			width: 500,
			height: 350,
			webPreferences: {
				nodeIntegration: true,
			},
			resizable: false,
			fullscreenable: false,
			skipTaskbar: true,
			icon: "src/static/icons/xpander-gui.png",
		});
		ABOUT_WINDOW.removeMenu();
		ABOUT_WINDOW.loadFile("src/static/about.html");
		ABOUT_WINDOW.once("closed", () => ABOUT_WINDOW = null);
	}
	return ABOUT_WINDOW;
}


app.on("window-all-closed", ev => ev.preventDefault());
app.on("ready", createTray);


SHELL.on("message", (msg) => {
	if (msg.type === "phrase") {
		if (msg.action === "fillin") {
			let window = fillinWindow();
			window.loadFile("src/static/fillin.html").then(() => {
				window.webContents.send("phrase", msg);
			});
		}
	} else if (msg.type === "main") {
		if (msg.action === "pause") {
			if (TRAY_MENU) {
				TRAY_MENU.getMenuItemById('pause').checked = msg.state;
				if (msg.state) {
					PAUSE = true;
				} else {
					PAUSE = false;
				}
				let theme = Settings.DEFAULT.light_theme === "True" ? "light" : "dark";
				let icon = `src/static/icons/xpander-gui-${PAUSE ? "inactive" : "active"}-${theme}.png`;
				TRAY?.setImage(icon);
			}
		}
	} else if (msg.type === "manager") {
		if (msg.action === "show") {
			MANAGER_WINDOW = managerWindow();
		} else if (msg.action === 'listWindows') {
			MANAGER_WINDOW?.webContents.send("manager", msg);
		}
	}
});
SHELL.on("stderr", (err) => console.log(err));


ipcMain.on("phrase", (event, msg) => {
	SHELL.send(msg);
});
ipcMain.on("manager", (event, msg) => {
	SHELL.send(msg);
});
ipcMain.on("settings", (event, msg) => {
	SHELL.send(msg);
	if (msg.action === "reload") {
		Settings = loadSettings();
		let theme = Settings.DEFAULT.light_theme === "True" ? "light" : "dark";
		let icon = `src/static/icons/xpander-gui-${PAUSE ? "inactive" : "active"}-${theme}.png`;
		TRAY?.setImage(icon);
	}
});
