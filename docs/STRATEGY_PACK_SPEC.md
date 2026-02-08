# STRATEGY_PACK_SPEC — Built-in Strategy Catalog (20)

## Goal
Provide 20 well-known, rule-based strategies as first-class built-ins:
- Parameterized
- Documented
- Testable
- Visualizable (entries/exits and outcomes)

## Rules for Inclusion
Each built-in strategy must have:
- Stable name and semantic version
- Clear entry/exit rules (no vague “intuition”)
- Parameter schema (types, ranges, defaults)
- Warmup requirement stated
- Basic tests:
  - deterministic signal behavior on synthetic series
  - smoke backtest run produces artifacts
- UI-friendly tags (category, recommended markets/timeframes)

## Categories and Initial List (20)
Trend / Breakout
1) SMA Crossover
2) EMA Crossover
3) Donchian Breakout
4) Bollinger Breakout
5) Supertrend Trend-Follow
6) ADX Filtered Breakout

Mean Reversion
7) RSI Mean Reversion
8) Bollinger Reversion
9) Z-score Reversion (price)
10) Keltner Reversion

Momentum
11) MACD Momentum
12) ROC Momentum
13) Stochastic Momentum

Volatility / Squeeze
14) ATR Volatility Breakout
15) BB-Keltner Squeeze Release

Market Structure (Rule-based)
16) Pivot Breakout
17) Support/Resistance Retest (rule-based)

Exits / Risk Wrappers (still “strategies” for users)
18) Time-based Exit Wrapper
19) Trailing Stop Wrapper
20) Fixed RR Stop/Target Wrapper

## Standard Outputs (must be consistent)
All strategies output normalized intents:
- HOLD
- ENTER_LONG / ENTER_SHORT
- EXIT_LONG / EXIT_SHORT
Optionally:
- confidence score (0..1)
- tags (reasons)

## Parameter Schema Conventions
- integer/float/bool/string/enum
- min/max/step where applicable
- defaults must be safe and reasonable
- changing params must not change contract behavior (only logic thresholds)

## Testing Minimum
- Each strategy has:
  - unit tests for entry/exit conditions
  - at least one smoke backtest generating:
    - trade list
    - metrics summary
    - timeline events
