import { ipcRenderer } from "electron";
import $ from "jquery";
import M from "materialize-css";


const fillinBody = $("#fillin-body");
const okButton = $("#ok");
const cancelButton = $("#cancel");


ipcRenderer.on("phrase", (event, msg) => {
	if (fillinBody) {
		fillinBody.html(msg.body);
	}
	M.FormSelect.init(document.querySelectorAll("select"), { dropdownOptions: { coverTrigger: false }});
	M.updateTextFields();
	$(":input").on("input", function() {
		if (this.tagName === "INPUT" && (<HTMLInputElement>this).type === "checkbox") {
			$(":input").filter(`[name="${(<HTMLFormElement>this).name}"]`).prop("checked", $(this).prop("checked"));
		} else if (this.tagName === "SELECT") {
			$(":input").filter(`[name="${(<HTMLFormElement>this).name}"]`).val($(this).val() || '');
			M.FormSelect.init(document.querySelectorAll("select"), { dropdownOptions: { coverTrigger: false }});
		} else {
			$(":input").filter(`[name="${(<HTMLFormElement>this).name}"]`).val($(this).val() || '');
			M.updateTextFields();
		}
	});
	okButton.on("click", function(event) {
		$(":input").each(function() {
			let $this = $(this);
			if ($this.attr("type") === "checkbox") {
				if ($this.prop("checked")) {
					$this.parents(".xpander-fillin").replaceWith(<string>$this.val() || "");
				} else {
					$this.parents(".xpander-fillin").replaceWith("");
				}
			} else {
				$this.parents(".xpander-fillin").replaceWith(<string>$this.val() || "");
			}
		});
		ipcRenderer.send("phrase", {
			"type": "phrase",
			"action": "fillin",
			"phrase": {
				"body": fillinBody.html(),
				"method": msg.method,
				"trigger": msg.trigger,
				"richText": msg.richText,
			}
		});
		window.close();
	});
	cancelButton.on("click", function(event) {
		window.close();
	});
	$(document).on("keyup", function(event) {
		if (event.key === "Enter") {
			if (this.activeElement?.tagName === "TEXTAREA" && event.ctrlKey) {
				okButton.click();
			} else if (this.activeElement?.tagName !== "TEXTAREA") {
				okButton.click();
			}
		}
		if (event.key === "Esc" || event.key === "Escape") {
			window.close();
		}
	});
});
