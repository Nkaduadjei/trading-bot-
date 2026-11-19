# Decisions

1. **Monorepo.** Services change together while contracts are young; one repo keeps versions in step.
2. **Python for strategy and execution, Spring Boot for platform.** Quant libraries live in Python; auth and gateway fit your existing Spring Boot stack.
3. **Signals are positions, not orders.** A strategy says what it wants to hold. The risk manager decides what may actually be traded.
4. **Daily bars, long/flat only, to start.** Low turnover keeps costs small and results easy to verify.
5. **No lookahead.** A signal computed at close of day t earns the return of day t+1.
6. **Costs are always on.** Commission and slippage are charged on every position change.
7. **Walk-forward validation.** Parameters are chosen on past data only and judged on the data after it.
