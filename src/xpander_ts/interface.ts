import { ipcRenderer } from "electron";


const ECHO = document.getElementById("echo");
const OUTPUT = document.getElementById("output");


ipcRenderer.on("async-msg", (event, msg) => {
	if (OUTPUT) {
		OUTPUT.innerText = msg;
	}
});

ECHO?.addEventListener("input", () => {
	ipcRenderer.send("async-msg", (<HTMLInputElement>ECHO).value);
});

ECHO?.dispatchEvent(new Event("input"));
