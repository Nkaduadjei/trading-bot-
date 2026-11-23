# Decisions

1. **Monorepo.** Services change together while contracts are young; one repo keeps versions in step.
2. **Python for the strategy engine and execution.** Quant libraries live in Python.
3. **Signals are positions, not orders.** A strategy says what it wants to hold. The risk manager decides what may actually be traded.
4. **Daily bars, long/flat only, to start.** Low turnover keeps costs small and results easy to verify.
5. **No lookahead.** A signal computed at close of day t earns the return of day t+1.
6. **Costs are always on.** Commission and slippage are charged on every position change.
7. **Walk-forward validation.** Parameters are chosen on past data only and judged on the data after it.
8. **Platform layer in Python (FastAPI), not Spring Boot.** One language and one toolchain for the whole project, and the code can be run and tested without a JVM. The ideas (auth, gateway, admin) are the same and can be re-built in Spring Boot later if wanted.
9. **Auth service choices.** scrypt for passwords (standard library, no compiled dependency); Fernet for encrypting stored keys; short-lived login tokens (15 minutes); 2FA codes (RFC 6238) written with the standard library; lockout after 5 failed logins; a used 2FA code cannot be reused.
10. **Broker keys are write-only over HTTP.** They can be stored and deleted but never read back. A user must confirm each key is trade-only. The service cannot verify this itself.
11. **Services talk over HTTP on local-only ports, each guarded by an internal token.** A bug or attack on one service cannot reach into another's code or memory.
12. **Signed approvals make the risk gate unskippable.** The risk manager signs every approved order. Execution accepts only signed, fresh orders (30 seconds). Only these two share the signing key; the gateway does not have it, so even a compromised gateway cannot place an order the risk manager did not approve.
13. **The risk manager never trusts the caller's numbers.** It reads equity, positions and the price from execution itself. The request has no price field at all.
14. **A stop closer than 0.5% to the price is refused,** so the per-trade risk limit cannot be gamed with a tiny stop distance.
15. **If anything is unreadable, the answer is no.** Execution unreachable, bad account data, or a corrupt state file all mean no approval.
16. **The gateway is a whitelist, not a blind proxy.** Only listed routes exist. The kill switch, the paper price endpoint and the upstream docs pages cannot be reached from outside.
17. **The auth service stays the only holder of the login secret.** The gateway checks each login by asking it, so the gateway cannot mint tokens.
18. **The gateway has no signing key.** It forwards the risk manager's signed approval untouched. A bug or break-in at the gateway still cannot place an order the risk manager did not approve.
19. **Trading is allowed only for emails in TRADER_EMAILS; empty means nobody.** There is one shared paper account for now, so being logged in is not enough.
20. **Rate limits, a body-size cap and generic errors.** Login and register are limited to 10 per minute per address; errors never reveal internal addresses or tokens. One retry to execution is safe because orders are idempotent.
21. **The admin console listens on this computer only and checks the Host header.** Another web page you visit cannot trick your browser into talking to it.
22. **Admin means logged in AND on ADMIN_EMAILS; empty means nobody.** Being a registered user gives no admin power.
23. **Least privilege.** The console gets the risk manager token and a separate auth admin token. It never gets the signing key or the execution token, so even a compromised console cannot place orders.
24. **The users endpoint lives on the auth service behind its own token and does not exist unless that token is set.** The gateway does not forward it. Only whitelisted fields are ever returned.
25. **Every admin action is audited, and a failed kill-switch action says the state is UNKNOWN** instead of pretending it worked.

