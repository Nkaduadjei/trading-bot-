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
