import { shell } from "electron";
import $ from "jquery";
import M from "materialize-css";


$(document).ready(() => {
	$("#repo").on("click", function(event) {
		shell.openExternal("https://github.com/OzymandiasTheGreat/xpander");
	});
	$("#mail").on("click", function(event) {
		shell.openExternal("mailto:tomas.rav@gmail.com");
	});
	M.Modal.init(document.querySelectorAll(".modal"));
});
