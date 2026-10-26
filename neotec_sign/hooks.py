app_name = "neotec_sign"
app_title = "Neotec Sign"
app_publisher = "Neotec Integrated Solutions"
app_description = "Simple PFX/P12 digital signatures for any ERPNext document, with audit log and QR verification"
app_email = ""
app_license = "Proprietary"
required_apps = ["frappe", "erpnext"]

app_include_js = "/assets/neotec_sign/js/neotec_sign.js"

after_install = "neotec_sign.install.after_install"
after_migrate = "neotec_sign.install.after_migrate"

boot_session = "neotec_sign.boot.boot_session"

doc_events = {
	"*": {
		"on_submit": "neotec_sign.events.on_submit",
	}
}
