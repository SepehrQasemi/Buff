# 08_RESEARCH_LOOP

## Purpose
Define the required research progression from offline evaluation to paper-live validation.

## Required Progression
Promotion flow is strictly ordered:
1. Backtest
2. Walk-forward
3. Paper-live futures simulation

Skipping stages is not allowed.

## Regime Split Requirement
Evaluation must include regime-aware segmentation.

Minimum regime partitions:
- Trending
- Mean-reverting/range
- High-volatility stress
- Low-liquidity stress proxy (if available)

Requirements:
- Metrics must be reported per regime segment and aggregate.
- Promotion cannot rely on aggregate-only performance.

## Cost Sensitivity Tests
Every candidate must pass cost stress evaluation.

Required tests:
- Baseline cost assumptions
- Elevated fee scenario
- Elevated slippage scenario
- Combined fee+slippage stress
- Funding stress perturbation

Fail criteria:
- Strategy edge collapses under mild realistic cost stress.

## Promotion Rules
A candidate is promotable only when all gates pass:
- Deterministic replay stability for the tested configuration
- Regime robustness (no critical blind regime)
- Cost sensitivity resilience within defined thresholds
- Risk event profile within allowed envelope
- Paper-live behavior consistent with expected decision logic

Promotion outputs must include:
- Promotion verdict artifact
- Evidence bundle references
- Versioned configuration fingerprints

## Stop Conditions
Research progression must halt immediately when any stop condition is met:
- Determinism break (digest mismatch on replay)
- Risk kill-switch event frequency above threshold
- Liquidation event rate above threshold
- Cost-stress failure
- Data integrity contract failure

When stopped:
- Candidate state becomes `STOPPED`
- Further promotion is blocked until a new candidate revision is produced
- Stop reason must be artifact-recorded with stable reason code
