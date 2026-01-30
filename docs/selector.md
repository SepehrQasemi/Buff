# Selector (Menu-Based)

The selector is a deterministic rule engine that maps market signals and a risk state to a **strategy_id** from a fixed menu or **NO_TRADE**. It does **not** produce buy/sell signals or price predictions. It only chooses a menu entry.

## Inputs

- `signals` (`MarketSignals`)
  - `trend_state`: `"up" | "down" | "flat" | "unknown"`
  - `volatility_regime`: `"low" | "mid" | "high" | "unknown"`
  - `momentum_state`: `"bull" | "bear" | "neutral" | "unknown"`
  - `structure_state`: `"breakout" | "meanrevert" | "none" | "unknown"`
- `risk_state` (`RiskState`): `GREEN | YELLOW | RED`

## Output

`SelectionResult` includes:

- `strategy_id`: a menu ID or `None` (meaning **NO_TRADE**)
- `reason`: deterministic human-readable reason
- `rule_id`: stable rule identifier (e.g. `R2`)
- `inputs`: snapshot of only the fields used by the rule plus `risk_state`

## Risk precedence

Risk state has absolute precedence over all market-derived rules:

- `RED` always yields **NO_TRADE**, regardless of signals.
- `YELLOW` always yields **DEFENSIVE**, regardless of signals.

This is intentional to keep the selector deterministic and auditable.

## DEFENSIVE semantics

`DEFENSIVE` is a menu strategy_id used as a **meta/defensive profile**. It is intended to map to stricter execution constraints in later milestones (e.g., risk limits, position sizing constraints), while remaining a valid strategy choice in M5.

## Rule ordering (first match wins)

1. **R0**: `risk_state == RED` -> `NO_TRADE` (`reason="risk=RED"`)
2. **R1**: `risk_state == YELLOW` -> `DEFENSIVE` (`reason="risk=YELLOW"`)
3. **R2**: `trend_state in {up,down}` and `volatility_regime in {low,mid}` and `structure_state == breakout`
   -> `TREND_FOLLOW` (`reason="trend+breakout & vol not high"`)
4. **R3**: `trend_state == flat` and `volatility_regime in {low,mid}` and `structure_state == meanrevert`
   -> `MEAN_REVERT` (`reason="range+meanrevert & vol not high"`)
5. **R9**: default -> `NO_TRADE` (`reason="no_rule_matched"`)

## Example

Input:

```
signals = {
  "trend_state": "up",
  "volatility_regime": "low",
  "momentum_state": "neutral",
  "structure_state": "breakout",
}
risk_state = RiskState.GREEN
```

Output:

```
SelectionResult(
  strategy_id="TREND_FOLLOW",
  reason="trend+breakout & vol not high",
  rule_id="R2",
  inputs={
    "risk_state": RiskState.GREEN,
    "trend_state": "up",
    "volatility_regime": "low",
    "structure_state": "breakout",
  },
)
```
