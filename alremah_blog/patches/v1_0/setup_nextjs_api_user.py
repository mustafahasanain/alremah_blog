import frappe

ROLE_NAME = "Alremah Blog API"

USER_EMAIL = "nextjs@remah.local"
USER_FULL_NAME = "Alremah Next.js API"

# Roles that would indicate this account is a human/admin account rather
# than the dedicated integration user this patch expects to own. If an
# existing 'nextjs@remah.local' account carries any of these, it is treated
# as an unrelated/conflicting account and the patch fails loudly instead of
# silently repurposing it.
DISQUALIFYING_ROLES = {"System Manager", "Website Manager", "Blogger", "Administrator"}


def execute():
	"""Ensure the dedicated Alremah Next.js integration user exists, carries
	the 'Alremah Blog API' role, and has API Key/API Secret credentials.

	Safe to run multiple times:
	- reuses the user if it already exists and is clearly the intended
	  integration account (no unrelated/admin roles on it);
	- adds the 'Alremah Blog API' role only if it is missing, and never
	  strips other roles from a pre-existing account automatically;
	- generates API Key/Secret only if they are not already set, so a
	  re-run never rotates a valid, already-issued secret.
	"""
	user = get_or_create_user()
	ensure_integration_role(user)
	ensure_api_credentials(user)


def get_or_create_user():
	if frappe.db.exists("User", USER_EMAIL):
		user = frappe.get_doc("User", USER_EMAIL)
		guard_against_conflicting_account(user)

		if not user.enabled:
			user.enabled = 1
			user.save(ignore_permissions=True)

		return user

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": USER_EMAIL,
			"first_name": USER_FULL_NAME,
			"enabled": 1,
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	)
	# Belt-and-braces: also skip the welcome mail flow even if
	# send_welcome_email is later flipped on for some reason.
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)
	return user


def guard_against_conflicting_account(user):
	"""Refuse to touch an existing 'nextjs@remah.local' account that does
	not look like a dedicated, low-privilege integration user."""
	existing_roles = {d.role for d in user.roles}
	conflicting_roles = existing_roles & DISQUALIFYING_ROLES

	if user.user_type == "System User" or conflicting_roles:
		frappe.throw(
			f"A user '{USER_EMAIL}' already exists but does not look like the "
			"dedicated Alremah Next.js API integration account expected by this "
			f"patch (user_type={user.user_type!r}, roles={sorted(existing_roles)!r}). "
			"Refusing to modify it automatically - please review this account manually."
		)


def ensure_integration_role(user):
	existing_roles = {d.role for d in user.roles}
	if ROLE_NAME not in existing_roles:
		user.append("roles", {"role": ROLE_NAME})
		user.save(ignore_permissions=True)


def ensure_api_credentials(user):
	"""Generate API Key/Secret using Frappe's own whitelisted mechanism
	(frappe.core.doctype.user.user.generate_keys), but only when a complete,
	valid credential pair is not already present.

	generate_keys() unconditionally rotates api_secret on every call (and
	only issues a new api_key if one is missing), so it is invoked here
	strictly when needed:
	- no api_key at all (first run): issues both api_key and api_secret.
	- api_key present but api_secret missing/undecryptable (a corrupted or
	  partially-provisioned account): reuses the existing api_key and only
	  (re)issues api_secret, since there is no valid secret to preserve.

	A complete, valid pair is never touched, so a re-run never rotates an
	already-issued, working secret."""
	from frappe.core.doctype.user.user import generate_keys
	from frappe.utils.password import get_decrypted_password

	user.reload()

	if user.api_key:
		existing_secret = get_decrypted_password(
			"User", user.name, fieldname="api_secret", raise_exception=False
		)
		if existing_secret:
			# Complete, valid credential pair already exists; leave it untouched.
			return
		frappe.msgprint(
			f"User {user.name} has an api_key but no valid api_secret; "
			"issuing a new api_secret via Frappe's generate_keys().",
			alert=True,
		)

	generate_keys(user.name)
