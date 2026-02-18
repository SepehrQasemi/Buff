# PRODUCT_SPEC — Buff (TradingView-like Strategy Lab)

## Normative Authority
Current stage is defined exclusively by:
docs/PROJECT_STATE.md

Runtime behavior is normatively defined by:
- [02_ARCHITECTURE_BOUNDARIES.md](./02_ARCHITECTURE_BOUNDARIES.md)
- [03_CONTRACTS_AND_SCHEMAS.md](./03_CONTRACTS_AND_SCHEMAS.md)

If this document conflicts with either normative document, the normative document takes precedence.
This file is descriptive and is not authoritative for canonical error codes or HTTP status mapping.

## Product Identity
Buff is a TradingView-like **strategy analysis lab**: a chart-first UI for visualizing signals, trades, and outcomes of strategies on historical data and paper runs.
Buff is **read-only** in the UI: it does not provide Buy/Sell buttons, broker connections, or live execution controls.

## Roadmap Alignment

The official roadmap and locked product decisions live in:
- `docs/PRODUCT_ROADMAP.md`
- `docs/USER_JOURNEY.md`
- `docs/ARCHITECTURE_BOUNDARIES.md`

If any document conflicts with these boundaries, the boundaries win.

## Target User
- Users who want to **test, compare, and iterate** on strategies and indicators visually.
- Users can be technical or semi-technical, but the product must guide them step-by-step when adding strategies/indicators.

## Core Value Proposition
- On-chart truth: show **exactly where** a strategy would enter/exit and **what happened** (PnL, win/loss, drawdown).
- Fast iteration: select strategy, tune parameters, rerun, compare.
- Extensible: users can add strategies/indicators safely through a defined contract and guided chatbot.

## Scope (Product v1)
### UI-first (TradingView-like)
- Candlestick chart + overlays + trade markers + outcome visualization.
- Strategy selection + parameter editing.
- Indicator selection + configuration and overlay.
- Run/result explorer: compare runs, inspect trades, metrics, and decision timeline.
#### Metrics Artifacts (UI)
- Metrics artifacts may include metrics.time_breakdown: an array of period buckets (e.g., monthly/weekly).
- UI behavior: when present, render a time breakdown table; when absent, show \"Time breakdown not available.\"
- No UI recomputation; values are displayed as-is from artifacts.

### Strategy Catalog
- Built-in pack of **20 well-known strategies** (rule-based) with documented rules and parameters.
- Strategies are customizable via parameter schema and UI forms.

### User Extensibility
- Users can add:
  - Custom indicators (pure computations)
  - Custom strategies (signals generation using indicators)
- Additions must follow contracts and pass validation. The system must not allow unsafe behavior.

### Risk Model
- Default risk configuration exists.
- Users can customize risk behavior within safe boundaries.
- Risk has **5 levels** (1..5) with increasing aggressiveness but still bounded by hard safety caps.

### AI Chatbot
- Built-in chatbot helps users:
  - Define and generate indicator/strategy templates
  - Understand required files and steps
  - Validate and troubleshoot errors
  - Review common issues (lookahead, leakage, NaNs, warmup, overfitting smells)

## Explicit Non-goals
- No buy/sell buttons or trading execution from UI.
- No broker connections or live trading controls in UI.
- No “AI that guarantees profits” or “signals marketplace”.
- No multi-tenant SaaS or hosted user accounts (v1).

## Product Principles (Non-negotiable)
- **UI shows truth derived from artifacts**; no hidden calculations that diverge from engine results.
- Deterministic, explainable outputs; every plotted trade/outcome has traceable provenance.
- Extensibility must be safe: user code cannot bypass core contracts, risk safety caps, or artifacts integrity.

## Definition of “Usable”
A user can:
1) Open the UI and load data / runs.
2) Select a built-in strategy, tune parameters, run, and see:
   - entries/exits on chart
   - each trade outcome
   - summary metrics and timeline events
3) Add a new indicator or strategy using guided chatbot steps, validate it, and see it appear in UI.
