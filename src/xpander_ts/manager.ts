import * as path from "path";
import * as fs from "fs";
import * as os from "os";
import { ipcRenderer, remote } from "electron";
import * as ini from "ini";
import Xdg from "xdg-app-paths";
import * as readdirp from "readdirp";
import rimraf from "rimraf";
import $ from "jquery";
import M from "materialize-css";
import "jqtree";
import "simple-module";
import "simple-hotkeys";
import "simple-uploader";
import Simditor from "simditor";
import * as PKG from "../../package.json";
import * as KeyMap from "../xpander_ts/keymap.json";


Simditor.locale = "en-US";


interface IPhrase {
	body: string,
	type: "plaintext" | "richtext",
	hotstring: string | null,
	hotkey: Array<any> | null,
	triggers: Array<string>,
	method: "paste" | "type" | "altpaste",
	wm_class: Array<string>,
	wm_title: string,
}


const newPhrase: IPhrase = {
	"body": "",
	"type": "plaintext",
	"hotstring": null,
	"hotkey": null,
	"triggers": [],
	"method": "paste",
	"wm_class": [],
	"wm_title": "",
}
const xdg = Xdg({ name: PKG.name, suffix: "", isolated: true });
const config = process.platform === 'linux' ? xdg.config() : path.join(os.homedir(), "AppData/Local/", PKG.name);
const Settings = ini.parse(fs.readFileSync(path.join(config, 'settings.ini'), 'utf-8'));


class TextEditor {
	simditor: Simditor | null;
	textarea: HTMLTextAreaElement;
	richtext: JQuery;

	constructor() {
		this.simditor = null;
		this.textarea = <HTMLTextAreaElement>document.getElementById("phraseBody");
		this.richtext = $(`#phraseType input[type="checkbox"]`);

		this.richtext.on("change", () => {
			if (this.richtext.prop("checked") && !this.simditor) {
				this.simditor = new Simditor({
					textarea: $(this.textarea),
					toolbar: [
						"title",
						"bold",
						"italic",
						"underline",
						"strikethrough",
						"|",
						"fontScale",
						"color",
						"|",
						"ol",
						"ul",
						"|",
						"blockquote",
						"code",
						"|",
						"table",
						"link",
						"image",
						"hr",
						"|",
						"indent",
						"outdent",
						"alignment",
					],
				});
			} else {
				if (this.simditor) {
					let html = this.simditor.sync();
					let div = document.createElement("div");
					div.innerHTML = html;
					let text = div.textContent || div.innerText || "";
					div.remove();
					this.simditor.destroy();
					this.simditor = null;
					$(this.textarea).css({ display: "block" });
					$(this.textarea).val(text);
				}
			}
		});
	}

	getText(): string {
		if (this.simditor) {
			return this.simditor.getValue();
		}
		return <string>$(this.textarea).val();
	}

	setText(text: string): void {
		if (this.simditor) {
			try {
				this.simditor.setValue(text);
			} catch(err) {
				this.setType("plaintext");
				$(this.textarea).val(text);
				this.setType("richtext");
			}

		} else {
			$(this.textarea).val(text);
		}
	}

	getType(): "plaintext" | "richtext" {
		if (this.simditor && this.richtext.prop("checked")) {
			return "richtext";
		}
		return "plaintext";
	}

	setType(type: string): void {
		if (type === "richtext") {
			this.richtext.prop("checked", true).trigger("change");
		} else {
			this.richtext.prop("checked", false).trigger("change");
		}
	}
}


function expandUser(filePath: string): string {
	if (filePath.startsWith("~")) {
		return path.join(os.homedir(), filePath.slice(1));
	}
	return filePath;
}


function parseHotkey(hotkey) {
	let [key, mods] = hotkey;
	let ret = "";
	mods.forEach((mod, index) => {
		mods[index] = mod.slice(4);
	});
	key = key.slice(4);
	if (mods.includes("SHIFT")) ret += "SHIFT + ";
	if (mods.includes("CTRL")) ret += "CTRL + ";
	if (mods.includes("ALT")) ret += "ALT + ";
	if (mods.includes("META")) ret += "META + ";
	return ret + key;
}


function toHotkey(str): Array<any> | null {
	let keys = str.split("+");
	if (keys.length > 1) {
		let ret: Array<any> = [];
		keys.forEach((key, index) => {
			keys[index] = `KEY_${key.trim()}`;
		});
		ret.push(keys.pop());
		ret.push(keys);
		return ret;
	}
	return null;
}


function sortFiles(arr: []) {
	arr.sort((a: any, b: any) => {
		if (a.type === b.type) {
			if (a.name < b.name) {
				return -1;
			} else if (a.name > b.name) {
				return 1;
			} else {
				return 0;
			}
		} else {
			if (a.type === "folder") {
				return -1;
			} else {
				return 1;
			}
		}
	});
	for (let entry of arr) {
		if (Object.keys(entry).includes("children")) sortFiles((<any>entry).children);
	}
}


function buildTree(rootPath: string, rootElem: JQuery): Promise<JQuery> {
	rootElem.off("tree.move");
	rootElem.off("tree.dblclick");
	// rootElem.off("tree.select");
	rootElem.off("click", ".renameBtn");
	rootElem.off("click", ".deleteBtn");
	rootElem.tree("destroy");
	return readdirp.promise(rootPath, {
		fileFilter: "*.json",
		depth: 5,
		type: "files_directories",
	}).then((fileList) => {
		let data: any = [];
		fileList.forEach((file) => {
			let parts = file.path.split(path.sep);
			let children = data;
			let name = parts.pop();
			for (let part of parts) {
				let parent = children.find((child) => child.name === part);
				if (parent) children = parent.children;
			}
			if (file.dirent?.isDirectory()) {
				children.push({
					name: path.parse(file.fullPath).name,
					children: [],
					path: file.fullPath,
					type: "folder",
				});
			} else {
				children.push({
					name: path.parse(file.fullPath).name,
					path: file.fullPath,
					type: "file",
				});
			}
		});
		sortFiles(data);
		rootElem.tree({
			data: data,
			dragAndDrop: true,
			autoOpen: 0,
			buttonLeft: false,
			showEmptyFolder: true,
			closedIcon: "\ue315",
			openedIcon: "\ue313",
			onCanSelectNode: (node) => {
				if (node.type === "file") return true;
				return false;
			},
			onCreateLi: function(node, $li, is_selected) {
				if (node.type === "folder") {
					$li.find(".jqtree-title").before(
						`<i class="material-icons folder-icon">folder</i>`
					);
					$li.find(".jqtree-toggler-right").after(
						`<a href="#" title="Rename" class="renameBtn">
							<i class="material-icons rename-icon">edit</i>
						</a>
						<a href="#" title="Delete" class="deleteBtn">
							<i class="material-icons delete-icon">delete</i>
						</a>`
					);
				} else {
					$li.find(".jqtree-title").before(
						`<i class="material-icons file-icon">note</i>`
					);
					$li.find(".jqtree-title").after(
						`<a href="#" title="Rename" class="renameBtn">
							<i class="material-icons rename-icon">edit</i>
						</a>
						<a href="#" title="Delete" class="deleteBtn">
							<i class="material-icons delete-icon">delete</i>
						</a>`
					);
				}
			},
		});
		return Promise.resolve(rootElem);
	});
}


function attachTreeEvents(rootElem: JQuery, textEditor: TextEditor): void {
	rootElem.on("tree.select", function(event: any) {
		if (event.node === null) {
			resetEditor(textEditor);
			$("#editor").find(":input").prop("disabled", true);
		} else {
			console.log("Node selected!");
			$("#editor").find(":input").prop("disabled", false);
			loadPhrase(event.node.path, textEditor);
		}
	});
	rootElem.on("tree.move", (event) => {
		const { moved_node, target_node, position } = (<any>event).move_info;
		if (position === "inside") {
			if (target_node.type === "folder") {
				fs.rename(
					moved_node.path,
					path.join(target_node.path, path.basename(moved_node.path)),
					() => buildTree(expandUser(Settings.DEFAULT.phrase_dir), rootElem).then(() => attachTreeEvents(rootElem, textEditor))
				);
			} else {
				event.preventDefault();
			}
		} else {
			let dest = target_node.parent.path;
			if (!dest || target_node.parent.name === "") {
				dest = expandUser(Settings.DEFAULT.phrase_dir);
			}
			fs.rename(
				moved_node.path,
				path.join(dest, path.basename(moved_node.path)),
				() => buildTree(expandUser(Settings.DEFAULT.phrase_dir), rootElem).then(() => attachTreeEvents(rootElem, textEditor))
			);
		}
		ipcRenderer.send("phrase", { "type": "phrase", "action": "reload" });
	});
	rootElem.on("tree.dblclick", (event) => {
		rootElem.tree("toggle", (<any>event).node);
	});
	$(".renameBtn").on("click", function(event) {
		let node = <INode>rootElem.tree("getNodeByHtmlElement", this);
		$("#renameInput").val(node.name);
		$("#renameDialog").modal("open");
		M.updateTextFields();
		$("#renameSubmit").one("click", () => {
			let newName = <string>$("#renameInput").val();
			let newPath: string;
			if (node.type === "file") {
				newPath = path.join(path.dirname(node.path), newName + ".json");
			} else {
				newPath = path.join(path.dirname(node.path), newName);
			}
			fs.rename(node.path, newPath, () => {
				buildTree(expandUser(Settings.DEFAULT.phrase_dir), rootElem).then(() => attachTreeEvents(rootElem, textEditor));
				if (node.type === "file") {
					ipcRenderer.send("phrase", {
						"type": "phrase",
						"action": "delete",
						"path": node.path,
					});
					ipcRenderer.send("phrase", {
						"type": "phrase",
						"action": "edit",
						"path": newPath,
					});
				} else {
					ipcRenderer.send("phrase", { "type": "phrase", "action": "reload" });
				}
			});
		});
	});
	$(".deleteBtn").on("click", function(event) {
		let node = <INode>rootElem.tree("getNodeByHtmlElement", this);
		if (node.type === "folder") {
			$("#deleteWarning").modal("open");
			$("#deleteSubmit").one("click", () => {
				rootElem.tree("removeNode", node);
				rimraf(node.path, () => {
					buildTree(expandUser(Settings.DEFAULT.phrase_dir), rootElem).then(() => attachTreeEvents(rootElem, textEditor));
					ipcRenderer.send("phrase", { "type": "phrase", "action": "reload" });
				});
			});
		} else {
			rootElem.tree("removeNode", node);
			fs.unlink(node.path, () => {
				buildTree(expandUser(Settings.DEFAULT.phrase_dir), rootElem).then(() => attachTreeEvents(rootElem, textEditor));
				ipcRenderer.send("phrase", {
					"type": "phrase",
					"action": "delete",
					"path": node.path,
				});
			});
		}
		resetEditor(textEditor);
		$("#editor").find(":input").prop("disabled", true);
	});
}


function resetEditor(textEditor: TextEditor) {
	textEditor.setType("plaintext");
	textEditor.setText("");
	$("#hotstring").val("");
	$("#hotkey").val("");
	$("#triggers").val("");
	$("#pasteMethod option[selected]").prop("selected", false);
	$("#pasteMethod").formSelect({ dropdownOptions: { coverTrigger: false }});
	$("#wmClass").val("");
	$("#wmTitle").val("");
	M.updateTextFields();
}


function loadPhrase(filePath: string, textEditor: TextEditor) {
	fs.readFile(filePath, 'utf-8', (err, data) => {
		let phrase = JSON.parse(data);
		textEditor.setType(phrase.type);
		textEditor.setText(phrase.body);
		$("#hotstring").val(phrase.hotstring ? phrase.hotstring : "");
		$("#hotkey").val(phrase.hotkey ? parseHotkey(phrase.hotkey) : "");
		$("#triggers").val(phrase.triggers ? phrase.triggers.join("").replace("\t", "\\t").replace("\n", "\\n") : "");
		$(`#pasteMethod option[value="${phrase.method}"]`).prop("selected", true);
		$("#pasteMethod").formSelect({ dropdownOptions: { coverTrigger: false }});
		$("#wmClass").val(phrase.wm_class ? phrase.wm_class.join() : "");
		$("#wmTitle").val(phrase.wm_title);
		M.updateTextFields();
	});
}


function loadSettings() {
	$("#pathDisplay").val(expandUser(Settings.DEFAULT.phrase_dir));
	$("#keepTrig").prop("checked", Settings.DEFAULT.keep_trig === "True");
	$("#useTab").prop("checked", Settings.DEFAULT.use_tab);
	$(`#theme option[value="${Settings.DEFAULT.light_theme}"]`).prop("selected", true);
	$("#theme").formSelect({ dropdownOptions: { coverTrigger: false }});
	$("#pauseKey").val(Settings.HOTKEY.pause ? parseHotkey(JSON.parse(Settings.HOTKEY.pause)) : "");
	$("#managerKey").val(Settings.HOTKEY.manager ? parseHotkey(JSON.parse(Settings.HOTKEY.manager)) : "");
	M.updateTextFields();
}


$(document).ready(() => {
	const textEditor = new TextEditor();

	$(".tabs").tabs();
	$('.modal').modal();
	$(".fixed-action-btn").floatingActionButton({
		direction: "right",
		hoverEnabled: false,
	});
	$("select").formSelect({ dropdownOptions: { coverTrigger: false }});
	$("#wmClass").autocomplete();
	$("#wmTitle").autocomplete();

	buildTree(expandUser(Settings.DEFAULT.phrase_dir), $("#files")).then(() => attachTreeEvents($("#files"), textEditor));

	$("#newPhrase").on("click", function(event) {
		let node = $("#files").tree("getSelectedNode");
		let dir = expandUser(Settings.DEFAULT.phrase_dir);
		if (node) {
			dir = path.dirname(node.path);
		}
		let filePath = path.join(dir, "New phrase.json");
		let iteration = 1;
		while (fs.existsSync(filePath)) {
			filePath = path.join(dir, `New phrase ${iteration}.json`);
			iteration++;
		}
		fs.writeFile(filePath, JSON.stringify(newPhrase), () => buildTree(expandUser(Settings.DEFAULT.phrase_dir), $("#files")).then(() => attachTreeEvents($("#files"), textEditor)));
	});
	$("#newFolder").on("click", function(event) {
		let node = $("#files").tree("getSelectedNode");
		let dir = expandUser(Settings.DEFAULT.phrase_dir);
		if (node) {
			dir = path.dirname(node.path);
		}
		let folderPath = path.join(dir, "New folder");
		let iteration = 1;
		while (fs.existsSync(folderPath)) {
			folderPath = path.join(dir, `New folder ${iteration}`);
			iteration++;
		}
		fs.mkdir(folderPath, () => buildTree(expandUser(Settings.DEFAULT.phrase_dir), $("#files")).then(() => attachTreeEvents($("#files"), textEditor)));
	});

	resetEditor(textEditor);
	$("#editor").find(":input").prop("disabled", true);

	$("#hotkey, #pauseKey, #managerKey").on("keydown", function(event) {
		let key = <string>event.originalEvent?.code;
		if (key !== "Tab") {
			event.preventDefault();

			let hotkey = "";
			if (key === "Backspace") $(this).val("");
			if (Object.keys(KeyMap).includes(key)) {
				key = KeyMap[key];
			}
			hotkey += event.shiftKey ? "SHIFT + " : "";
			hotkey += event.ctrlKey ? "CTRL + " : "";
			hotkey += event.altKey ? "ALT + " : "";
			hotkey += event.metaKey ? "META + " : "";
			if (key.startsWith("Key")) key = key.slice(3);
			if (!["SHIFT", "CTRL", "ALT", "META"].includes(key)) hotkey += key.toUpperCase();
			if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) $(this).val(hotkey);
		}
	});
	$("#cancelBtn").on("click", function(event) {
		let node = $("#files").tree("getSelectedNode");
		if (node) {
			loadPhrase(node.path, textEditor);
		}
	});
	$("#saveBtn").on("click", function(event) {
		let node = $("#files").tree("getSelectedNode");
		if (node) {
			let phrase: IPhrase = JSON.parse(JSON.stringify(newPhrase));
			phrase.body = textEditor.getText();
			phrase.type = textEditor.getType();
			phrase.hotstring = <string>$("#hotstring").val() || null;
			phrase.hotkey = toHotkey($("#hotkey").val() || "");
			phrase.triggers = (<string>$("#triggers").val())?.replace("\\t", "\t").replace("\\n", "\n").split("");
			$("#pasteMethod").formSelect({ dropdownOptions: { coverTrigger: false }});
			phrase.method = <"paste"|"type"|"altpaste"><unknown>$("#pasteMethod").formSelect("getSelectedValues")[0];
			phrase.wm_class = $("#wmClass").val() ? (<string>$("#wmClass").val()).split(", ") : [];
			phrase.wm_title = (<string>$("#wmTitle").val()) || "";
			let filePath = node.path;
			fs.writeFile(node.path, JSON.stringify(phrase), () => {
				ipcRenderer.send("phrase", {
					"type": "phrase",
					"action": "edit",
					"path": filePath,
				});
			});
		}
	});

	setTimeout(() => {
		ipcRenderer.send("manager", { "type": "manager", "action": "listWindows" });
	}, 1000);
	ipcRenderer.on("manager", (event, msg) => {
		if (msg.action === "listWindows") {
			let classData = {};
			let titleData = {};
			for (let window of msg.list) {
				classData[window.class] = null;
				titleData[window.title] = null;
			}
			$("#wmClass").autocomplete("updateData", classData);
			$("#wmTitle").autocomplete("updateData", titleData);
		}
	});

	loadSettings();
	$("#phraseDir").on("click", function(event) {
		remote.dialog.showOpenDialog(remote.getCurrentWindow(), {
			defaultPath: expandUser(Settings.DEFAULT.phrase_dir),
			properties: ["openDirectory", "showHiddenFiles"],
		}).then(({ canceled, filePaths }) => {
			if (!canceled) {
				$(this).find("input").val(filePaths[0]);
			}
		});
	});
	$("#settingsCancel").on("click", function(event) {
		loadSettings();
	});
	$("#settingsSave").on("click", function(event) {
		Settings.DEFAULT.phrase_dir = $("#pathDisplay").val();
		Settings.DEFAULT.keep_trig = $("#keepTrig").prop("checked") ? "True" : "False";
		Settings.DEFAULT.use_tab = $("#useTab").prop("checked") ? "True" : "False";
		$("#theme").formSelect({ dropdownOptions: { coverTrigger: false }});
		Settings.DEFAULT.light_theme = $("#theme").formSelect("getSelectedValues")[0];
		Settings.HOTKEY.pause = JSON.stringify(toHotkey($("#pauseKey").val() || ""));
		Settings.HOTKEY.manager = JSON.stringify(toHotkey($("#managerKey").val() || ""));
		fs.writeFile(path.join(config, 'settings.ini'), ini.stringify(Settings), () => {
			ipcRenderer.send("settings", { "type": "settings", "action": "reload" });
		});
	});
});
