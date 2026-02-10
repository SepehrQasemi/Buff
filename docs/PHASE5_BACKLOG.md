# PHASE5_BACKLOG — Phase-3/4 Readiness + Phase-5 Execution Backlog
Date: 2026-02-10

**Gate / Preconditions**
Note: Run `python scripts/verify_phase1.py --with-services` without output piping in PowerShell; pipelines can mask the true exit code.

**Acceptance Criteria Checklists**

**UI_SPEC**
- [ ] UI is read-only for execution (no buy/sell, no broker actions).
- [ ] Dashboard shows recent runs with timestamp, dataset, strategy, risk level, summary PnL.
- [ ] Dashboard quick actions include Open Chart, Run Explorer, Strategy Library, Add Strategy/Indicator (chatbot flow).
- [ ] Chart Workspace shows candlestick chart with symbol/timeframe/date selectors and right sidebar tabs.
- [ ] Strategy tab lists built-in + validated user strategies.
- [ ] Strategy tab auto-generates parameter form from schema.
- [ ] Strategy tab shows risk level selector (1..5).
- [ ] Strategy tab supports Run (paper/backtest only) and Save preset.
- [ ] Strategy tab shows validation status and warnings (warmup/NaN/missing data).
- [ ] Indicators tab supports search/add, per-indicator parameter form, overlay toggles, and pane placement.
- [ ] Indicators tab shows validated user indicators.
- [ ] Trades tab lists entry/exit time/price, side, size, PnL, MFE/MAE where available.
- [ ] Trade click highlights markers and opens Trade Detail panel.
- [ ] Trade Detail shows entry/exit timestamps/prices, side, quantity/size, PnL (abs/%), duration.
- [ ] Trade Detail shows reason tags (entry/exit/risk intervention) and provenance (run_id, strategy version, data manifest hash).
- [ ] Metrics tab shows total PnL, win rate, avg win/loss, profit factor.
- [ ] Metrics tab shows max drawdown and exposure metrics; trades count; avg duration.
- [ ] Metrics time breakdown by month/week supported when available.
- [ ] Metrics derived strictly from artifacts (no hidden recomputation).
- [ ] Timeline tab shows data validation warnings, warmup start/end, risk blocks/changes, run start/end, artifact integrity checks.
- [ ] AI Chat tab includes Add Indicator, Add Strategy, Review Strategy, Explain Trade flows.
- [ ] Run Explorer supports filtering by symbol/timeframe/strategy/date.
- [ ] Run Explorer supports comparing two runs with trade/metric overlays.
- [ ] Run Explorer opens a run in Chart Workspace (artifact-driven).
- [ ] Strategy Library lists 20 built-in strategies and user strategies with description, rules, params schema, examples, limitations.
- [ ] Indicator Library lists built-in catalog + user indicators with definition, warmup/NaN policy, params schema.
- [ ] UI reads market data snapshot/manifest + run artifacts (decisions, trades, metrics) as truth.
- [ ] Chart supports zoom/pan, multi-pane indicators, trade markers (entry/exit + win/loss/breakeven).
- [ ] Chart hover tooltips show details.
- [ ] UX is fast, deterministic, and errors are actionable (no stack traces).

**PRODUCT_SPEC**
- [ ] UI is read-only; no broker/live execution controls.
- [ ] Chart-first visualization of signals, trades, outcomes.
- [ ] Strategy selection + parameter tuning + rerun + compare supported.
- [ ] Indicator selection + configuration + overlay supported.
- [ ] Run explorer with trade/metric/timeline inspection.
- [ ] Built-in pack of 20 deterministic strategies with docs.
- [ ] User can add indicators and strategies via contract + validation gate.
- [ ] Risk model exists with 5 levels and hard caps.
- [ ] Chatbot guides creation/validation/review without executing trades.
- [ ] UI outputs are deterministic and traceable to artifacts.
- [ ] Extensibility cannot bypass contracts, safety caps, or artifact integrity.
- [ ] Usable: user can load runs, run a built-in strategy, see trades/metrics/timeline, add strategy/indicator and see it in UI.

**STRATEGY_GOVERNANCE**
- [ ] Strategies are versioned, registered, and tested; selector only chooses from registered set.
- [ ] Strategy changes require version bump and changelog entry.
- [ ] Strategy outputs intents only (LONG/SHORT/FLAT), deterministic, explicit I/O.
- [ ] Approval workflow: sandbox authoring -> review -> approved registry.
- [ ] Load & activation gate is fail-closed.
- [ ] Required files exist for strategy and indicator plugins.
- [ ] Schema validation passes.
- [ ] Static safety checks pass (forbidden imports/ops).
- [ ] Determinism checks pass (no randomness/time/I/O).
- [ ] Warmup and NaN policies declared and validated.
- [ ] Validation artifact/status record written and stored.

**STRATEGY_CONTRACT**
- [ ] Required files: `user_strategies/<id>/strategy.yaml` + `strategy.py` (README/tests recommended).
- [ ] `strategy.yaml` includes id/name/version/author/category/warmup_bars/inputs/params/outputs.
- [ ] Inputs declare required series + indicator IDs.
- [ ] Outputs declare intents list + provides_confidence.
- [ ] `strategy.py` implements `get_schema()` and `on_bar(ctx)`; `on_finish(ctx)` optional.
- [ ] `on_bar` returns valid intent + optional confidence + tags.
- [ ] Determinism: no randomness/time/I/O/subprocess/network/unsafe imports.
- [ ] No lookahead usage of future data.
- [ ] Performance limits: bounded time/memory; exceptions handled as ERROR events.
- [ ] Validation checks schema, inputs, intents, warmup, and static safety.
- [ ] UI shows strategies only after validation; schema drives parameter forms; errors link to chatbot flow.

**INDICATOR_CONTRACT**
- [ ] Required files: `user_indicators/<id>/indicator.yaml` + `indicator.py` (tests recommended).
- [ ] `indicator.yaml` includes id/name/version/category/inputs/outputs/params/warmup_bars/nan_policy.
- [ ] `indicator.py` implements `get_schema()` + `compute(ctx)` returning output series keys.
- [ ] Causal: no future access in computations.
- [ ] Deterministic and side-effect free (no I/O).
- [ ] Validation checks schema, output keys, warmup, nan_policy, static safety.
- [ ] Built-in indicator coverage includes MA/Momentum/Volatility/Trend/Volume/Statistics/Structure set.

**CHATBOT_SPEC**
- [ ] Draft Mode outputs templates + step-by-step instructions + validation commands.
- [ ] Review Mode checks contract compliance, lookahead/leakage, NaN/warmup, overfitting smells, inconsistencies.
- [ ] Explain Mode references trade markers/run artifacts and explains why trades happened.
- [ ] Flow: Add Indicator with required inputs/outputs/params/warmup/nan_policy.
- [ ] Flow: Add Strategy with rules/indicators/params/warmup/confidence.
- [ ] Flow: Review Strategy/Indicator with structured report (issues/warnings/suggestions/tests).
- [ ] Flow: Troubleshoot errors with root cause + edits + rerun commands.
- [ ] Safety: never disable hard risk caps, never claim profits, never suggest live deployment.
- [ ] Exact Steps: returns exact files, fields, commands, and success signals in UI.

**RISK_MODEL_SPEC**
- [ ] Two-layer model: hard safety caps + user risk policy.
- [ ] Risk levels 1..5 with increasing aggressiveness bounded by hard caps.
- [ ] UI shows risk level selector and risk block reasons.
- [ ] Custom risk definition supports `user_risk/<id>/risk.yaml` + `risk.py` with validation/sandboxing.
- [ ] Hard caps always enforced regardless of user policy.
- [ ] Artifacts record risk blocks with timestamp, intent, verdict, rule id, reason, and level.

**PHASE2_CLOSURE**
- [ ] Built-in Strategy Pack v1 (20 deterministic strategies) shipped and documented.
- [ ] Registry adapter exposure shipped.
- [ ] Strategy determinism/registry/smoke tests shipped.
- [ ] Docs published at `docs/STRATEGY_LIBRARY.md`.
- [ ] Final tests: `python -m ruff format .`, `python -m ruff check .`, `pytest -q`.

**Codebase Findings (Evidence)**
- UI artifact loading: `apps/web/lib/api.js` and `apps/web/lib/useWorkspace.js` call `/runs`, `/runs/{id}/summary`, `/runs/{id}/decisions`, `/runs/{id}/trades`, `/runs/{id}/trades/markers`, `/runs/{id}/metrics`, `/runs/{id}/timeline`, `/runs/{id}/ohlcv`.
- API artifact loading: `apps/api/main.py` routes map to loaders in `apps/api/artifacts.py` (e.g., `load_ohlcv`, `load_trades`, `load_metrics`, `build_timeline_from_decisions`).
- Metrics UI: `apps/web/pages/runs/[id].js` renders `metrics` from `useWorkspace`.
- Timeline UI: `apps/web/pages/runs/[id].js` renders `timeline` from `useWorkspace`.
- Run Explorer UI: `apps/web/pages/runs/index.js` lists runs and links to `/runs/[id]`.
- Compare UI/API: no compare page under `apps/web/pages` and no compare endpoints in `apps/api`.
- Plugin validation gate: `src/plugins/validate.py` + `src/plugins/validation.py` write `artifacts/plugins/<type>/<id>/validation.json` and fail-closed on errors; `apps/api/plugins.py` exposes active/failed lists from validation artifacts.
- UI uses validated plugins only: `apps/web/pages/runs/[id].js` renders strategies/indicators from `activePlugins` and shows failed diagnostics.
- Chatbot flows exist in API: `apps/api/chat.py` modes `add_indicator`, `add_strategy`, `review_plugin`, `explain_trade`; UI wiring in `apps/web/pages/runs/[id].js` using `getChatModes`/`postChat` in `apps/web/lib/api.js`.

**Phase-3 (User Extensibility) Status: PASS**
Evidence:
- Validation + fail-closed artifacts: `src/plugins/validation.py` (`validate_candidate`, `_SafetyScanner`) and `src/plugins/validate.py` (`write_validation_artifact`).
- API exposes validated plugins only: `apps/api/plugins.py` and `/api/v1/plugins/active` + `/api/v1/plugins/failed` in `apps/api/main.py`.
- UI surfaces validated plugins and hides invalid: `apps/web/lib/useWorkspace.js`, `apps/web/pages/runs/[id].js`.
- Tests: `tests/plugins/test_plugin_validation.py`, `tests/integration/test_plugins_api.py`.

**Phase-4 (AI Chatbot) Status: FAIL**
Evidence:
- Existing modes: `apps/api/chat.py` `_MODE_INDEX` and handlers; UI wired in `apps/web/pages/runs/[id].js`.
- Tests cover only current modes: `tests/integration/test_chatbot_api_phase4.py`.

Minimum blocking tasks:
- Add Troubleshoot Errors flow (spec Flow 4) with exact steps, edits, rerun commands. Suggested files: `apps/api/chat.py` (new mode + handler), `apps/web/pages/runs/[id].js` (new form inputs), `tests/integration/test_chatbot_api_phase4.py` (new tests).
- Expand Review Mode checks to include explicit warmup/NaN handling and basic overfitting-smell heuristics per spec. Suggested files: `apps/api/chat.py` (`_review_plugin` helpers), `tests/integration/test_chatbot_api_phase4.py`.

**Release Gate**
Phase-4 must PASS before any release or go/no-go milestone.
Phase-5 PRs may proceed in parallel as long as UI stays read-only and artifact-driven.

**Phase-4 PASS Criteria (Required for Release)**
- [ ] Troubleshoot Errors flow implemented and exposed in UI. Suggested files: `apps/api/chat.py`, `apps/web/pages/runs/[id].js`, `tests/integration/test_chatbot_api_phase4.py`. Verify: `pytest -q tests/integration/test_chatbot_api_phase4.py`.
- [ ] Review Mode expanded checks (warmup/NaN + basic overfitting smells). Suggested files: `apps/api/chat.py`, `tests/integration/test_chatbot_api_phase4.py`. Verify: `pytest -q tests/integration/test_chatbot_api_phase4.py`.
- [ ] Explain Trade references artifacts (markers/decisions/trades) and has an integration test. Suggested files: `apps/api/chat.py`, `tests/integration/test_chatbot_api_phase4.py`. Verify: `pytest -q tests/integration/test_chatbot_api_phase4.py`.
- [ ] Integration tests for all Phase-4 modes exist and pass. Suggested files: `tests/integration/test_chatbot_api_phase4.py`. Verify: `pytest -q tests/integration/test_chatbot_api_phase4.py`.
- [ ] UI shows all modes in AI Chat tab and each mode returns structured output. Suggested files: `apps/web/pages/runs/[id].js`, `apps/api/chat.py`. Verify: `python scripts/verify_phase1.py --with-services` (open `/runs/phase1_demo` and confirm all modes render and return structured sections).

**Verification Scripts / Tests (Phase-1/Phase-2 relevant)**
Recommended:
- `python scripts/verify_phase1.py --with-services`
- `node apps/web/scripts/ui-smoke.mjs`
- `node apps/web/scripts/smoke.mjs`
- `python scripts/verify_m1.py`
- `python -m ruff check .`
- `python -m ruff format --check .`
- `pytest -q`

Latest run (2026-02-10):
- `python scripts/verify_phase1.py --with-services` -> PASS
- `python -m ruff check .` -> PASS
- `python -m ruff format --check .` -> PASS
- `pytest -q` -> PASS (509 passed)

**Phase-5 Backlog (Summary)**
- Performance / Smooth UX: request cancellation + cache for artifact fetches; trades pagination for large trade sets.
- Run Comparison: select two runs; side-by-side metrics; trade marker overlays.
- Metrics time breakdown: render per-period metrics when artifacts include breakdowns.
- Timeline readability: group by date and filter by severity.
- Docs / Quickstart: user extensibility quickstart; compare and metrics breakdown docs.

**Phase-5 PR Execution Plan**
PR order rationale: stabilize data fetching and paging (PR-01/PR-02) before adding compare flows to reduce UI regression risk and ensure baseline performance. Compare features build on reliable artifact loading, while docs follow feature shape to avoid churn.
Order: PR-01 -> PR-02 -> PR-03 -> PR-04 -> PR-05 -> PR-06 -> PR-07 -> PR-08.

**Performance / Smooth UX**
**PR-01: Add request cache and abort for workspace artifacts**
Depends on: none.
Scope: Add AbortController support and a small in-memory cache keyed by run_id, timeframe, and range for OHLCV, markers, trades, metrics, and timeline requests.
Does NOT change:
- API contracts or endpoints.
- Artifact truth, server-side computations, or UI write controls.
Acceptance criteria:
- [ ] Switching run, symbol, or timeframe cancels in-flight requests and prevents stale updates.
- [ ] Re-loading the same run/timeframe/range reuses cached payloads unless Refresh is clicked.
- [ ] Errors and empty states remain unchanged from current behavior.
Target files:
- `apps/web/lib/api.js`
- `apps/web/lib/useWorkspace.js`
Test plan:
- `python -m ruff check .`
- `python -m ruff format --check .`
- `pytest -q`
- `node apps/web/scripts/ui-smoke.mjs`
Risk notes:
- Cached data could appear stale if Refresh does not invalidate cache; detect by changing timeframe and verifying new timestamps.
Rollback plan:
- Revert PR-01 to remove cache and abort logic.

**PR-02: Add trades pagination controls in workspace**
Depends on: none. (Optional: pairs with PR-01 for request cancellation.)
Scope: Add page/page_size controls for trades in `runs/[id]` and wire through `useWorkspace` to `/runs/{id}/trades`. API already supports `page` and `page_size` in `apps/api/main.py` `trades()` and `apps/api/artifacts.py` `load_trades()`.
Does NOT change:
- API pagination parameters or backend ordering semantics.
- Artifact formats, trade computation, or decision records.
Acceptance criteria:
- [ ] Trades table supports paging in fixed increments (default 250).
- [ ] Requests include `page` and `page_size`; `total`, `page`, and `page_size` from the response drive UI controls.
- [ ] Selection and trade detail operate on the currently displayed page only.
- [ ] No client-side recomputation of trades.
Target files:
- `apps/web/pages/runs/[id].js`
- `apps/web/lib/useWorkspace.js`
Test plan:
- `python -m ruff check .`
- `python -m ruff format --check .`
- `pytest -q`
- `node apps/web/scripts/ui-smoke.mjs`
Risk notes:
- Backend ordering is implicit to artifacts; detect mismatched expectations by paging through and confirming `total` is stable.
Rollback plan:
- Revert PR-02 to restore single-page trade list.

**Run Comparison**
**PR-03: Add compare selection and baseline compare page**
Depends on: none.
Scope: Add two-run selection on `/runs` and create a compare page that loads both run summaries and shows metadata side-by-side.
Does NOT change:
- API contracts, artifact formats, or metric computation.
- Existing run workspace behavior.
Acceptance criteria:
- [ ] User can select exactly two runs and navigate to compare view.
- [ ] Compare view loads both run summaries from artifacts and shows run_id, strategy, symbols, timeframe, and created_at.
- [ ] Invalid or missing run ids show actionable errors.
Target files:
- `apps/web/pages/runs/index.js`
- `apps/web/pages/runs/compare.js`
- `apps/web/lib/api.js`
Test plan:
- `python -m ruff check .`
- `python -m ruff format --check .`
- `pytest -q`
- `node apps/web/scripts/ui-smoke.mjs`
- Manual: open compare view for two runs and verify metadata fields render for both run_ids.
Risk notes:
- Query parameter handling could break deep links; detect by reloading the compare page.
Rollback plan:
- Revert PR-03 to remove compare selection and page.

**PR-04: Add compare metrics and trade marker overlays**
Depends on: PR-03.
Scope: Extend compare view to load metrics and trade markers for both runs and render side-by-side metrics plus overlay markers with run identification.
Does NOT change:
- Artifact formats, metrics computation, or trade generation.
- Existing single-run workspace behavior.
Acceptance criteria:
- [ ] Compare view shows metrics for both runs using `metrics.json` only.
- [ ] Legend maps Run A and Run B to marker styles and displays each run_id.
- [ ] Toggles allow showing/hiding markers for each run independently.
- [ ] Marker tooltips or labels include the originating run_id.
- [ ] Links allow opening each run in the standard workspace.
Target files:
- `apps/web/pages/runs/compare.js`
- `apps/web/components/workspace/CandlestickChart.js`
- `apps/web/lib/api.js`
Test plan:
- `python -m ruff check .`
- `python -m ruff format --check .`
- `pytest -q`
- `node apps/web/scripts/ui-smoke.mjs`
- Manual: open compare view, verify legend/run_id labels, and toggle Run A/Run B markers.
Risk notes:
- Overlay markers could confuse directions if styling is ambiguous; detect by comparing legend and marker colors.
Rollback plan:
- Revert PR-04 to restore baseline compare view only.

**Metrics time breakdown**
**PR-05: Render metrics time breakdown table**
Depends on: none.
Scope: When `metrics.json` includes `time_breakdown` as a list of period objects, render a simple table in the Metrics tab.
Does NOT change:
- Metric calculations, aggregation logic, or artifact formats.
- Any non-metrics tabs or chart behavior.
Acceptance criteria:
- [ ] If `metrics.time_breakdown` exists, render a table with period, total_return, max_drawdown, win_rate, and num_trades when present.
- [ ] If the field is missing, show a clear “not available” message.
- [ ] All values are displayed exactly as provided by artifacts.
Target files:
- `apps/web/pages/runs/[id].js`
- `apps/web/lib/format.js` or `apps/web/lib/metrics.js`
Test plan:
- `python -m ruff check .`
- `python -m ruff format --check .`
- `pytest -q`
- `node apps/web/scripts/ui-smoke.mjs`
Risk notes:
- Inconsistent metric keys could render blanks; detect by adding a fixture with partial fields.
Rollback plan:
- Revert PR-05 to remove breakdown rendering.

**Timeline readability**
**PR-06: Group timeline by date and add severity filters**
Depends on: none.
Scope: Group timeline events by date and provide INFO/WARN/ERROR filter controls.
Does NOT change:
- Timeline event content, ordering within artifacts, or server-side generation.
- Any non-timeline tabs or artifact loading.
Acceptance criteria:
- [ ] Timeline events are grouped under date headers.
- [ ] Filters show only matching severities and default to showing all.
- [ ] Event order remains artifact-true within each date.
Target files:
- `apps/web/pages/runs/[id].js`
- `apps/web/lib/timeline.js`
Test plan:
- `python -m ruff check .`
- `python -m ruff format --check .`
- `pytest -q`
- `node apps/web/scripts/ui-smoke.mjs`
Risk notes:
- Grouping could reorder events if timestamps are missing; detect by verifying stable ordering for a known run.
Rollback plan:
- Revert PR-06 to restore flat timeline list.

**Docs / Quickstart**
**PR-07: Add user extensibility quickstart**
Depends on: none.
Scope: Add a concise quickstart for user strategies/indicators and validation gate steps that mirror chatbot outputs.
Does NOT change:
- Strategy/indicator contracts or validation behavior.
- UI runtime behavior.
Acceptance criteria:
- [ ] Quickstart includes exact file paths, required fields, validation command, and UI success criteria.
- [ ] Mentions fail-closed behavior if validation fails.
Target files:
- `docs/USER_EXTENSIBILITY.md`
- `docs/README.md`
Test plan:
- `python -m ruff check .`
- `python -m ruff format --check .`
- `pytest -q`
Risk notes:
- Doc drift vs chatbot outputs; detect by comparing to `apps/api/chat.py` templates.
Rollback plan:
- Revert PR-07 to restore previous docs.

**PR-08: Document compare view and metrics breakdown fields**
Depends on: PR-03 and PR-05.
Scope: Update specs to document compare view usage and the optional `metrics.time_breakdown` field schema.
Does NOT change:
- Product scope, contracts, or runtime behavior.
- Validation gates or artifact truth rules.
Acceptance criteria:
- [ ] `docs/UI_SPEC.md` includes compare view behavior and artifact truth notes.
- [ ] `docs/PRODUCT_SPEC.md` describes the optional metrics breakdown field and usage.
Target files:
- `docs/UI_SPEC.md`
- `docs/PRODUCT_SPEC.md`
Test plan:
- `python -m ruff check .`
- `python -m ruff format --check .`
- `pytest -q`
Risk notes:
- Spec updates could conflict with contracts; detect by re-reading STRATEGY and INDICATOR contracts.
Rollback plan:
- Revert PR-08 to restore prior specs.

**Operator Checklist**
Before opening a Phase-5 PR:
- [ ] Run `python -m ruff check .`.
- [ ] Run `python -m ruff format --check .`.
- [ ] Run `pytest -q`.
- [ ] Run `python scripts/verify_phase1.py --with-services`.

After merging a Phase-5 PR:
- [ ] Start API/UI and open `/runs/phase1_demo` to confirm artifacts render.
- [ ] Verify metrics, timeline, and trades render with no UI recomputation.
- [ ] Verify compare view or new UI features load without API errors.
