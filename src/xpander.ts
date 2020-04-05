import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { app, ipcMain, BrowserWindow, Menu, MenuItemConstructorOptions, Tray, dialog } from "electron";
import { PythonShell } from "python-shell";
import * as ini from "ini";
import mkdirp from "mkdirp";
import Xdg from "xdg-app-paths";
import * as PKG from "../package.json";


const xdg = Xdg({ name: PKG.name, suffix: "", isolated: true });
let Settings = loadSettings();
const SHELL = new PythonShell(
	app.isPackaged ? path.resolve(process.resourcesPath, "xpander.pyz") : "src/xpander.py",
	{
		mode: "json",
		pythonPath: process.platform === 'linux' ? "python3" : "python",
		pythonOptions: ["-u"],
		stderrParser: (line) => JSON.stringify(line),
		env: { SHIV_ROOT: xdg.cache(), PYTHONUTF8: "1", ...process.env },
	});
const iconExt = process.platform === "linux" ? "png" : "ico";
const icon16 = process.platform === "linux" ? ".16x16" : "";
const icon48 = process.platform === "linux" ? ".48x48" : "";
let TRAY_MENU: Menu | null;
let TRAY: Tray | null;
let FILLIN_WINDOW: BrowserWindow | null;
let MANAGER_WINDOW: BrowserWindow | null;
let ABOUT_WINDOW: BrowserWindow | null;
let PAUSE: boolean = false;


function loadSettings() {
	const config = process.platform === 'linux' ? xdg.config() : path.join(os.homedir(), "AppData/Local/", PKG.name);
	let settings;
	try {
		settings = ini.parse(fs.readFileSync(path.join(config, 'settings.ini'), 'utf-8'));
	} catch(err) {
		settings = ini.parse(fs.readFileSync(path.resolve(__dirname, "./xpander_data/settings.ini"), "utf-8"));
		mkdirp.sync(config);
		fs.writeFileSync(path.join(config, "settings.ini"), ini.stringify(settings), "utf-8");
	}
	return settings;
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
	let icon = path.resolve(__dirname, `./static/icons/xpander-${PAUSE ? "inactive" : "active"}-${theme}${icon16}.${iconExt}`);
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
		// skipTaskbar: true,
		icon: path.resolve(__dirname, `./static/icons/xpander${icon48}.${iconExt}`),
	});
	window.removeMenu();
	window.once("show", () => {
		SHELL.send({ "type": "main", "action": "focus", "hwnd": window.getNativeWindowHandle() });
	});
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
			icon: path.resolve(__dirname, `./static/icons/xpander${icon48}.${iconExt}`),
		});
		// (<any> MANAGER_WINDOW).openDevTools();
		MANAGER_WINDOW.removeMenu();
		MANAGER_WINDOW.loadFile(path.resolve(__dirname, "./static/manager.html"));
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
			icon: path.resolve(__dirname, `./static/icons/xpander${icon48}.${iconExt}`),
		});
		ABOUT_WINDOW.removeMenu();
		ABOUT_WINDOW.loadFile(path.resolve(__dirname, "./static/about.html"));
		ABOUT_WINDOW.once("closed", () => ABOUT_WINDOW = null);
	}
	return ABOUT_WINDOW;
}


app.on("window-all-closed", ev => ev.preventDefault());
app.on("ready", createTray);


SHELL.on("message", (msg) => {
	if (msg.type === "phrase") {
		if (msg.action === "fillin") {
			FILLIN_WINDOW= fillinWindow();
			FILLIN_WINDOW.loadFile(path.resolve(__dirname,"./static/fillin.html")).then(() => {
				FILLIN_WINDOW?.webContents.send("phrase", msg);
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
				let icon = path.resolve(__dirname, `./static/icons/xpander-${PAUSE ? "inactive" : "active"}-${theme}${icon16}.${iconExt}`);
				TRAY?.setImage(icon);
			}
		} else if (msg.action === "focus") {
			if (FILLIN_WINDOW) {
				setTimeout(() => {
					FILLIN_WINDOW?.focus();
				}, 250);
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
		let icon = path.resolve(__dirname, `./static/icons/xpander-${PAUSE ? "inactive" : "active"}-${theme}${icon16}.${iconExt}`);
		TRAY?.setImage(icon);
	}
});
