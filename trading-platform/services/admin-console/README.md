# admin-console

Operator control panel on http://127.0.0.1:8004 (this computer only). Python (FastAPI) plus one static page.

What it does: shows whether each service is up, shows and flips the kill switch, lists registered
users (id, email, 2FA on/off, locked, never hashes or keys), and shows a log of admin actions.

Who may use it: you must log in AND your email must be in `ADMIN_EMAILS`. Empty means nobody.
It holds the risk manager's token (for the kill switch) and `AUTH_ADMIN_TOKEN` (to list users).
It never holds the signing key or the execution token.

Safety details: requests with an unexpected Host header are refused; the page uses a strict
Content-Security-Policy with no inline scripts; user-supplied text is shown as plain text only;
the login token lives in the browser tab's memory only; admin actions are appended to
`admin_audit.log` (private file, ignored by git).

Run tests: `python -m pytest -q`. Run: `bash scripts/run_admin.sh`, then open http://127.0.0.1:8004
Not built yet: 2FA enforcement for admins, a deliberate extra confirmation for releasing the kill switch on the server side.
