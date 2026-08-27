import frappe
from frappe.permissions import setup_custom_perms

ROLE_NAME = "Alremah Blog API"

# DocTypes that the Alremah Next.js website is allowed to read through this role.
BLOG_DOCTYPES = ["Blog Post", "Blogger", "Blog Category"]

# Desired permission state at permlevel 0 for the role: read-only + select,
# every write/admin capability explicitly disabled.
PERMISSION_FLAGS = {
	"if_owner": 0,
	"read": 1,
	"select": 1,
	"write": 0,
	"create": 0,
	"delete": 0,
	"submit": 0,
	"cancel": 0,
	"amend": 0,
	"report": 0,
	"import": 0,
	"export": 0,
	"share": 0,
	"print": 0,
	"email": 0,
}


def execute():
	"""Ensure the 'Alremah Blog API' role exists and has read-only access
	to the Blog Post, Blogger and Blog Category doctypes.

	Safe to run multiple times: reuses the role and Custom DocPerm rows if
	they already exist instead of creating duplicates.
	"""
	create_role()

	for doctype in BLOG_DOCTYPES:
		ensure_read_only_permission(doctype)


def create_role():
	if frappe.db.exists("Role", ROLE_NAME):
		return

	role = frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": ROLE_NAME,
			# API/integration role: no Desk UI access, not a system-wide admin role.
			"desk_access": 0,
			"is_custom": 1,
		}
	)
	role.insert(ignore_permissions=True)


def ensure_read_only_permission(doctype):
	# Materializes standard DocType permissions into Custom DocPerm rows the
	# first time this doctype is customized. This is the same mechanism the
	# Role Permission Manager uses and does not change any existing role's
	# effective permissions.
	setup_custom_perms(doctype)

	existing_name = frappe.db.get_value(
		"Custom DocPerm",
		{"parent": doctype, "role": ROLE_NAME, "permlevel": 0},
		"name",
	)

	if existing_name:
		docperm = frappe.get_doc("Custom DocPerm", existing_name)
		changed = False
		for fieldname, value in PERMISSION_FLAGS.items():
			if docperm.get(fieldname) != value:
				docperm.set(fieldname, value)
				changed = True
		if changed:
			docperm.save(ignore_permissions=True)
	else:
		docperm = frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"permlevel": 0,
				"role": ROLE_NAME,
				**PERMISSION_FLAGS,
			}
		)
		docperm.insert(ignore_permissions=True)

	frappe.clear_cache(doctype=doctype)
