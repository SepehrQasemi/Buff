# EXECUTION_SAFETY

## Hard Safety Constraints
- No live trading before paper trading passes stability checks
- All orders require SL/TP (or bracket orders) and position sizing
- API errors, network issues → fail-safe to 'no new orders'
- Full logging required for every decision and order action

## Secrets Handling
- API keys are read from environment variables only
- Never commit keys or `.env` to git
