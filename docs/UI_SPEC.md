# UI_SPEC — Buff TradingView-like UI (Read-only)

## Runtime Contract Alignment
- UI MUST render the API error envelope exactly as returned.
- UI MUST NOT transform error codes.
- UI MUST NOT infer execution state.
- UI is artifact-driven and read-only.
- Canonical contract reference: [03_CONTRACTS_AND_SCHEMAS.md#canonical-error-schema](./03_CONTRACTS_AND_SCHEMAS.md#canonical-error-schema)

## North Star
A chart-first experience like TradingView, focused on:
- Visualizing strategy signals and trades
- Showing outcomes clearly
- Helping users iterate quickly

UI must remain **read-only for execution** (no buy/sell, no broker actions).

## Run Creation UX (File-based)

Run creation in the UI is file-based:
- The user selects a CSV file using a file picker.
- The UI submits the creation request and displays progress.
- On success, the UI redirects to the workspace page for the created run id.

Implementation detail:
The backend may store the uploaded file to a controlled location and reference it as an internal path, so path-based request contracts remain compatible.

**Current status**
If the current implementation is path-based, it must be documented as temporary and scheduled for migration to file-based selection.
See `docs/DECISIONS.md` (D-001).

## Pages / Screens

### 1) Dashboard / Home
Purpose: quick access to data sources, runs, strategies, and recent activity.
Components:
- Recent runs list (timestamp, dataset, strategy, risk level, summary PnL)
- Quick actions:
  - Open Chart
  - Run Explorer
  - Strategy Library
  - Add Strategy/Indicator (opens chatbot flow)

### 2) Chart Workspace (Primary screen)
Core layout:
- Main candlestick chart with timeframe selector
- Left/Top toolbar:
  - Symbol selector
  - Timeframe selector
  - Date range selector
- Right sidebar (tabs):
  - Strategy
  - Indicators
  - Trades
  - Metrics
  - Timeline
  - AI Chat

#### 2.1 Strategy tab
- Strategy dropdown (built-in + user strategies)
- Parameter form auto-generated from strategy parameter schema
- Risk Level selector (1..5)
- Buttons:
  - Run (paper/backtest mode only; if UI triggers runs, it triggers local compute and stores artifacts; still no live)
  - Save preset (strategy+params)
- Output:
  - Strategy status (valid/invalid)
  - Warnings (warmup, NaN, missing data, etc.)

#### 2.2 Indicators tab
- Indicator search + add overlay
- Each indicator shows parameter form
- Overlay toggles:
  - show/hide
  - pane placement (main chart vs separate pane where applicable)
- User indicators appear here once validated/loaded.

#### 2.3 Trades tab
- Trade list table:
  - entry time/price
  - exit time/price
  - side
  - size (if available)
  - PnL
  - MFE/MAE (if computed)
- Clicking a trade:
  - highlights entry/exit markers on chart
  - opens Trade Detail panel

#### 2.4 Trade Detail panel
Must show (minimum):
- Entry/Exit timestamps and prices
- Side, quantity/size
- PnL (absolute and %)
- Trade duration
- Reason tags:
  - entry reason (rule/indicator conditions)
  - exit reason
  - risk intervention (if applicable)
- Provenance:
  - run_id
  - strategy version
  - data manifest hash reference

#### 2.5 Metrics tab
At minimum:
- Total PnL, win rate, avg win/loss, profit factor
- Max drawdown, Sharpe-like (optional), exposure metrics
- Trades count, avg duration
- Per-month (or per-week) breakdown (optional)
All metrics must be derived from artifacts (no hidden recomputation that can disagree).

#### 2.6 Timeline tab
Event timeline:
- Data validation warnings/errors
- Strategy warmup start/end
- Risk blocks / risk level changes
- Run start/end and status
- Artifact integrity checks

#### 2.7 AI Chat tab
Chatbot embedded:
- “Add Indicator” flow
- “Add Strategy” flow
- “Review Strategy” flow
- “Explain Trade” flow

### 3) Run Explorer
Purpose: browse and compare previous runs.
Features:
- Filter by symbol, timeframe, strategy, date
- Compare 2 runs:
  - overlay trades and outcomes
  - compare key metrics
- Open run in Chart Workspace (loads its artifacts)

### 3.1 Compare Runs
Access:
- From /runs by selecting exactly two runs and clicking Compare.
- Direct link: /runs/compare?runA=<id>&runB=<id>.

Behavior (read-only, artifact-driven):
- Compares summaries + metrics + trade marker overlays for Run A vs Run B.
- Baseline OHLCV uses Run A; Run B markers overlay on the Run A baseline chart.
- Legend shows both run_ids. Toggles can hide/show Run A or Run B markers.
- Marker tooltips include the originating run_id and marker type.
- No recomputation: values render as provided by artifacts only.

Error handling:
- Missing run ids -> show actionable error message.
- Same run id for runA/runB -> show actionable error message.
- Symbol/timeframe mismatch -> show warning:
  \"Runs differ in symbol/timeframe; marker alignment may be inaccurate.\"

### 4) Strategy Library
- Built-in strategies list (20)
- User strategies list
- Each strategy has:
  - description
  - rules summary
  - parameters schema
  - examples
  - known limitations

### 5) Indicator Library
- Built-in indicators catalog (categorized)
- User indicators list
- Each indicator has:
  - definition
  - warmup/NaN policy
  - parameters schema

## Data Sources for UI (Truth Sources)
Canonical contract reference:
- [03_CONTRACTS_AND_SCHEMAS.md#artifact-contract-matrix](./03_CONTRACTS_AND_SCHEMAS.md#artifact-contract-matrix)
- [03_CONTRACTS_AND_SCHEMAS.md#error-code-registry](./03_CONTRACTS_AND_SCHEMAS.md#error-code-registry)

UI reads:
- Market data snapshot/manifest (or configured data source)
- Run artifacts:
  - decision records (for decisions/timeline)
  - trades (for markers and trade list)
  - metrics summary
UI must not invent trades; it must plot from artifacts.

## Chart Requirements
- Candlestick rendering with zoom/pan
- Multi-pane indicator support
- Trade markers:
  - Entry marker (direction)
  - Exit marker
  - Color/shape indicates win/loss/breakeven
- Hover tooltips with details

## Minimal UX Requirements
- Fast: avoid blocking UI on heavy computation; show progress
- Deterministic: if run_id loaded, UI must render same view every time
- Error clarity: show actionable messages, not stack traces

