ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Strategy Library

This catalog contains 20 deterministic, rule-based strategies for visualization and inspection.
All strategies operate on OHLCV history and output intents only.

## sma_crossover (v1.0.0) ï¿½ Trend
Entry rule: ENTER_LONG when SMA_fast crosses above SMA_slow (prev_fast <= prev_slow and curr_fast > curr_slow). ENTER_SHORT when SMA_fast crosses below SMA_slow (prev_fast >= prev_slow and curr_fast < curr_slow).
Exit rule: No explicit exits; engine handles exits or strategy switches.
Indicators:
- SMA(period): mean(close[t-period+1..t]) with min_periods=period.
Parameters:
- fast_period (int, default 10, range 2-50, step 1)
- slow_period (int, default 30, range 5-200, step 1)
Warmup rationale: requires slow_period bars to compute SMA_slow.
Intended behavior: Trend-following in directional markets.

## ema_crossover (v1.0.0) ï¿½ Trend
Entry rule: ENTER_LONG when EMA_fast crosses above EMA_slow (prev_fast <= prev_slow and curr_fast > curr_slow). ENTER_SHORT when EMA_fast crosses below EMA_slow (prev_fast >= prev_slow and curr_fast < curr_slow).
Exit rule: No explicit exits; engine handles exits or strategy switches.
Indicators:
- EMA(period): EMA_t = EMA_{t-1} + alpha*(close_t - EMA_{t-1}), alpha = 2/(period+1), initialized by pandas ewm with min_periods=period and adjust=False.
Parameters:
- fast_period (int, default 12, range 2-50, step 1)
- slow_period (int, default 26, range 5-200, step 1)
Warmup rationale: requires slow_period bars to stabilize EMA_slow.
Intended behavior: Trend-following with responsive averages.

## donchian_breakout (v1.0.0) ï¿½ Trend
Entry rule: ENTER_LONG if close_t > max(high[t-lookback..t-1]). ENTER_SHORT if close_t < min(low[t-lookback..t-1]).
Exit rule: EXIT_LONG if close_t < min(low[t-exit_lookback..t-1]). EXIT_SHORT if close_t > max(high[t-exit_lookback..t-1]).
Indicators:
- Donchian upper: max(high[t-lookback..t-1]) (current bar excluded).
- Donchian lower: min(low[t-lookback..t-1]) (current bar excluded).
Parameters:
- lookback (int, default 20, range 5-100, step 1)
- exit_lookback (int, default 10, range 2-50, step 1)
Warmup rationale: requires max(lookback, exit_lookback) + 1 bars to exclude current bar.
Intended behavior: Trend breakouts with volatility expansion.

## bollinger_breakout (v1.0.0) ï¿½ Trend
Entry rule: ENTER_LONG if close_t > upper_t. ENTER_SHORT if close_t < lower_t.
Exit rule: EXIT_LONG if close_t < mid_t. EXIT_SHORT if close_t > mid_t.
Indicators:
- Bollinger mid: SMA(period).
- Bollinger std: rolling std(close, period, ddof=0).
- upper = mid + k*std, lower = mid - k*std.
Parameters:
- period (int, default 20, range 5-100, step 1)
- k (float, default 2.0, range 1.0-3.5, step 0.1)
Warmup rationale: requires period bars for SMA and std.
Intended behavior: Breakouts after volatility expansion.

## supertrend_trend_follow (v1.0.0) ï¿½ Trend
Entry rule: ENTER_LONG when trend flips from -1 to +1. ENTER_SHORT when trend flips from +1 to -1.
Exit rule: No explicit exits; engine handles exits or strategy switches.
Indicators:
- ATR (Wilder): see ATR definition in atr_volatility_breakout section.
- hl2_t = (high_t + low_t)/2.
- basic_upper = hl2 + multiplier*ATR, basic_lower = hl2 - multiplier*ATR.
- final_upper: if basic_upper < final_upper_{t-1} or close_{t-1} > final_upper_{t-1}, use basic_upper else final_upper_{t-1}.
- final_lower: if basic_lower > final_lower_{t-1} or close_{t-1} < final_lower_{t-1}, use basic_lower else final_lower_{t-1}.
- trend flips: if trend_{t-1} == -1 and close_t > final_upper_{t-1} => trend_t = +1; if trend_{t-1} == +1 and close_t < final_lower_{t-1} => trend_t = -1; otherwise trend_t = trend_{t-1}.
Parameters:
- atr_period (int, default 10, range 3-50, step 1)
- multiplier (float, default 3.0, range 1.0-5.0, step 0.1)
Warmup rationale: requires atr_period bars plus one bar for trend comparison.
Intended behavior: Trend-following with ATR-based trailing bands.

## adx_filtered_breakout (v1.0.0) ï¿½ Trend
Entry rule: ENTER_LONG if ADX_t >= adx_threshold and close_t > max(high[t-lookback..t-1]). ENTER_SHORT if ADX_t >= adx_threshold and close_t < min(low[t-lookback..t-1]).
Exit rule: EXIT_LONG if close_t < min(low[t-exit_lookback..t-1]). EXIT_SHORT if close_t > max(high[t-exit_lookback..t-1]).
Indicators:
- TR_t = max(high_t - low_t, abs(high_t - close_{t-1}), abs(low_t - close_{t-1})).
- +DM_t = max(high_t - high_{t-1}, 0) if (high_t - high_{t-1}) > (low_{t-1} - low_t); else 0.
- -DM_t = max(low_{t-1} - low_t, 0) if (low_{t-1} - low_t) > (high_t - high_{t-1}); else 0.
- Wilder smoothing over period: smoothed_TR, smoothed_+DM, smoothed_-DM.
- +DI = 100 * smoothed_+DM / smoothed_TR, -DI = 100 * smoothed_-DM / smoothed_TR.
- DX = 100 * abs(+DI - -DI) / (+DI + -DI).
- ADX = Wilder smoothing of DX over period; first valid ADX after 2*period bars.
Parameters:
- lookback (int, default 20, range 5-100, step 1)
- exit_lookback (int, default 10, range 2-50, step 1)
- adx_period (int, default 14, range 5-50, step 1)
- adx_threshold (float, default 20.0, range 5.0-50.0, step 0.5)
Warmup rationale: requires max(lookback, exit_lookback, 2*adx_period) bars for ADX readiness.
Intended behavior: Trend breakouts gated by trend-strength filter.

## rsi_mean_reversion (v1.0.0) ï¿½ Mean Reversion
Entry rule: ENTER_LONG if RSI_t <= lower. ENTER_SHORT if RSI_t >= upper.
Exit rule: EXIT_LONG if RSI_t >= exit. EXIT_SHORT if RSI_t <= exit.
Indicators:
- RSI (Wilder): delta = close_t - close_{t-1}; gain = max(delta, 0), loss = max(-delta, 0).
- avg_gain, avg_loss are Wilder smoothed (alpha=1/period).
- RS = avg_gain/avg_loss; RSI = 100 - 100/(1+RS); RSI = 100 when avg_loss == 0.
Parameters:
- period (int, default 14, range 5-50, step 1)
- lower (float, default 30.0, range 5.0-45.0, step 0.5)
- upper (float, default 70.0, range 55.0-95.0, step 0.5)
- exit (float, default 50.0, range 40.0-60.0, step 0.5)
Warmup rationale: requires period bars for Wilder smoothing.
Intended behavior: Range-bound mean reversion.

## bollinger_reversion (v1.0.0) ï¿½ Mean Reversion
Entry rule: ENTER_LONG if close_t < lower_t. ENTER_SHORT if close_t > upper_t.
Exit rule: EXIT_LONG if close_t >= mid_t. EXIT_SHORT if close_t <= mid_t.
Indicators:
- Bollinger mid: SMA(period).
- Bollinger std: rolling std(close, period, ddof=0).
- upper = mid + k*std, lower = mid - k*std.
Parameters:
- period (int, default 20, range 5-100, step 1)
- k (float, default 2.0, range 1.0-3.5, step 0.1)
Warmup rationale: requires period bars for SMA and std.
Intended behavior: Reversion in stable ranges.

## zscore_reversion (v1.0.0) ï¿½ Mean Reversion
Entry rule: ENTER_LONG if z_t <= -entry_z. ENTER_SHORT if z_t >= entry_z.
Exit rule: EXIT_LONG if z_t >= -exit_z. EXIT_SHORT if z_t <= exit_z.
Indicators:
- z_t = (close_t - mean_t) / std_t.
- mean_t = rolling mean(close, lookback), std_t = rolling std(close, lookback, ddof=0).
Parameters:
- lookback (int, default 20, range 10-100, step 1)
- entry_z (float, default 2.0, range 1.0-4.0, step 0.1)
- exit_z (float, default 0.5, range 0.1-2.0, step 0.1)
Warmup rationale: requires lookback bars for mean/std.
Intended behavior: Statistical mean reversion.

## keltner_reversion (v1.0.0) ï¿½ Mean Reversion
Entry rule: ENTER_LONG if close_t < lower_t. ENTER_SHORT if close_t > upper_t.
Exit rule: EXIT_LONG if close_t >= mid_t. EXIT_SHORT if close_t <= mid_t.
Indicators:
- EMA mid: EMA(ema_period).
- ATR (Wilder): see ATR definition in atr_volatility_breakout section.
- upper = mid + atr_mult*ATR, lower = mid - atr_mult*ATR.
Parameters:
- ema_period (int, default 20, range 5-100, step 1)
- atr_period (int, default 20, range 5-100, step 1)
- atr_mult (float, default 1.5, range 0.5-3.0, step 0.1)
Warmup rationale: requires max(ema_period, atr_period) bars.
Intended behavior: Mean reversion around EMA with ATR scaling.

## macd_momentum (v1.0.0) ï¿½ Momentum
Entry rule: ENTER_LONG when MACD crosses above signal and hist_t > hist_threshold. ENTER_SHORT when MACD crosses below signal and hist_t < -hist_threshold.
Exit rule: EXIT_LONG if MACD_t < signal_t. EXIT_SHORT if MACD_t > signal_t.
Indicators:
- MACD_t = EMA_fast(close) - EMA_slow(close).
- signal_t = EMA_signal(MACD).
- hist_t = MACD_t - signal_t.
Parameters:
- fast (int, default 12, range 5-20, step 1)
- slow (int, default 26, range 10-50, step 1)
- signal (int, default 9, range 3-20, step 1)
- hist_threshold (float, default 0.0, range 0.0-1.0, step 0.01)
Warmup rationale: requires slow + signal - 1 bars to fill MACD and signal.
Intended behavior: Momentum continuation in trending markets.

## roc_momentum (v1.0.0) ï¿½ Momentum
Entry rule: ENTER_LONG if ROC_t >= entry_threshold. ENTER_SHORT if ROC_t <= -entry_threshold.
Exit rule: EXIT_LONG if ROC_t <= exit_threshold. EXIT_SHORT if ROC_t >= -exit_threshold.
Indicators:
- ROC_t = 100 * (close_t / close_{t-period} - 1).
Parameters:
- period (int, default 12, range 5-50, step 1)
- entry_threshold (float, default 1.0, range 0.2-5.0, step 0.1)
- exit_threshold (float, default 0.0, range -1.0-1.0, step 0.1)
Warmup rationale: requires period bars for ROC.
Intended behavior: Short-term momentum bursts.

## stochastic_momentum (v1.0.0) ï¿½ Momentum
Entry rule: ENTER_LONG when %K crosses above %D and %K_t >= entry_threshold. ENTER_SHORT when %K crosses below %D and %K_t <= (100 - entry_threshold).
Exit rule: EXIT_LONG if %K_t <= exit_threshold. EXIT_SHORT if %K_t >= (100 - exit_threshold).
Indicators:
- highest_t = max(high[t-k_period+1..t]), lowest_t = min(low[t-k_period+1..t]).
- raw_%K_t = 100 * (close_t - lowest_t) / (highest_t - lowest_t).
- %K_t = SMA(raw_%K, smooth_k) if smooth_k > 1 else raw_%K_t.
- %D_t = SMA(%K, d_period).
Parameters:
- k_period (int, default 14, range 5-50, step 1)
- d_period (int, default 3, range 2-10, step 1)
- smooth_k (int, default 3, range 1-10, step 1)
- entry_threshold (float, default 60.0, range 50.0-90.0, step 1.0)
- exit_threshold (float, default 50.0, range 10.0-60.0, step 1.0)
Warmup rationale: requires k_period + smooth_k + d_period bars for smoothed %K/%D.
Intended behavior: Momentum continuation after oscillator confirmation.

## atr_volatility_breakout (v1.0.0) ï¿½ Volatility
Entry rule: ENTER_LONG if atr_pct_t >= atr_pct_threshold and close_t > max(high[t-lookback..t-1]). ENTER_SHORT if atr_pct_t >= atr_pct_threshold and close_t < min(low[t-lookback..t-1]).
Exit rule: EXIT_LONG if close_t < min(low[t-exit_lookback..t-1]). EXIT_SHORT if close_t > max(high[t-exit_lookback..t-1]).
Indicators:
- TR_t = max(high_t - low_t, abs(high_t - close_{t-1}), abs(low_t - close_{t-1})).
- ATR_t (Wilder): first ATR = mean(TR[0..period-1]); thereafter ATR_t = ((ATR_{t-1}*(period-1)) + TR_t)/period.
- atr_pct_t = ATR_t / close_t.
Parameters:
- lookback (int, default 20, range 5-100, step 1)
- exit_lookback (int, default 10, range 2-50, step 1)
- atr_period (int, default 14, range 5-50, step 1)
- atr_pct_threshold (float, default 0.01, range 0.002-0.05, step 0.001)
Warmup rationale: requires max(lookback, exit_lookback, atr_period) bars.
Intended behavior: Volatility expansion breakouts.

## bb_keltner_squeeze_release (v1.0.0) ï¿½ Volatility
Entry rule: After a squeeze for squeeze_bars consecutive bars and current bar is not a squeeze, ENTER_LONG if close_t > Bollinger upper_t, ENTER_SHORT if close_t < Bollinger lower_t.
Exit rule: EXIT_LONG if close_t < Bollinger mid_t. EXIT_SHORT if close_t > Bollinger mid_t.
Indicators:
- Bollinger bands: mid = SMA(bb_period), std = rolling std(ddof=0), upper = mid + bb_k*std, lower = mid - bb_k*std.
- Keltner channels: mid = EMA(kc_period), ATR = Wilder ATR(kc_period), upper = mid + kc_atr_mult*ATR, lower = mid - kc_atr_mult*ATR.
- Squeeze_t = (BB_upper_t < KC_upper_t) and (BB_lower_t > KC_lower_t).
Parameters:
- bb_period (int, default 20, range 5-100, step 1)
- bb_k (float, default 2.0, range 1.0-3.5, step 0.1)
- kc_period (int, default 20, range 5-100, step 1)
- kc_atr_mult (float, default 1.5, range 0.5-3.0, step 0.1)
- squeeze_bars (int, default 5, range 2-20, step 1)
Warmup rationale: requires max(bb_period, kc_period, squeeze_bars) bars.
Intended behavior: Volatility contraction then expansion.

## pivot_breakout (v1.0.0) ï¿½ Structure
Entry rule: ENTER_LONG if close_t > pivot_high * (1 + buffer_pct). ENTER_SHORT if close_t < pivot_low * (1 - buffer_pct).
Exit rule: EXIT_LONG if close_t < pivot_high * (1 - buffer_pct). EXIT_SHORT if close_t > pivot_low * (1 + buffer_pct).
Indicators:
- Pivot high at index i if high_i == max(high[i-L..i+L]) where L = pivot_lookback; confirmation requires L bars after i.
- Pivot low at index i if low_i == min(low[i-L..i+L]) where L = pivot_lookback; confirmation requires L bars after i.
- Strategy uses the most recent confirmed pivot high/low in history.
Parameters:
- pivot_lookback (int, default 3, range 2-10, step 1)
- buffer_pct (float, default 0.0, range 0.0-0.02, step 0.001)
Warmup rationale: requires 2*pivot_lookback + 1 bars for pivot confirmation.
Intended behavior: Structural breakouts at swing points.

## sr_retest_rule_based (v1.0.0) ï¿½ Structure
Entry rule: ENTER_LONG if prev_close > resistance*(1+breakout_buffer) and current_low <= resistance*(1+retest_tolerance) and current_close >= resistance. ENTER_SHORT if prev_close < support*(1-breakout_buffer) and current_high >= support*(1-retest_tolerance) and current_close <= support.
Exit rule: EXIT_LONG if current_close < resistance. EXIT_SHORT if current_close > support.
Indicators:
- resistance_t = rolling max(high, lookback) shifted by 1 bar.
- support_t = rolling min(low, lookback) shifted by 1 bar.
Parameters:
- lookback (int, default 20, range 10-60, step 1)
- breakout_buffer (float, default 0.002, range 0.0-0.02, step 0.001)
- retest_tolerance (float, default 0.002, range 0.0-0.02, step 0.001)
Warmup rationale: requires lookback + 1 bars for shifted levels.
Intended behavior: Retest-based entries after level breaks.

## time_based_exit_wrapper (v1.0.0) ï¿½ Wrapper
Entry rule: No entries; wrapper never emits ENTER intents.
Exit rule: If position.bars_in_trade >= max_bars, EXIT_LONG for long positions or EXIT_SHORT for short positions. If position context is missing, HOLD.
Indicators:
- None; relies only on explicit position context (side, entry_index, bars_in_trade).
Parameters:
- max_bars (int, default 10, range 1-200, step 1)
Warmup rationale: warmup=1 ensures at least one bar of history before evaluating exits.
Intended behavior: Time-based exits for any market state.

## trailing_stop_wrapper (v1.0.0) ï¿½ Wrapper
Entry rule: No entries; wrapper never emits ENTER intents.
Exit rule: If position.side == LONG and current_low <= position.max_price*(1 - trail_pct), EXIT_LONG. If position.side == SHORT and current_high >= position.min_price*(1 + trail_pct), EXIT_SHORT. If position context is missing, HOLD.
Indicators:
- None; relies only on explicit position context (side, entry_price, max_price, min_price).
Parameters:
- trail_pct (float, default 0.02, range 0.001-0.2, step 0.001)
Warmup rationale: warmup=1 ensures at least one bar of history before evaluating exits.
Intended behavior: Trend protection and profit locking.

## fixed_rr_stop_target_wrapper (v1.0.0) ï¿½ Wrapper
Entry rule: No entries; wrapper never emits ENTER intents.
Exit rule: If position.side == LONG, stop = entry*(1-stop_pct), target = entry*(1+stop_pct*reward_ratio); exit long if current_low <= stop or current_high >= target. If position.side == SHORT, stop = entry*(1+stop_pct), target = entry*(1-stop_pct*reward_ratio); exit short if current_high >= stop or current_low <= target. If position context is missing, HOLD.
Indicators:
- None; relies only on explicit position context (side, entry_price).
Parameters:
- stop_pct (float, default 0.01, range 0.001-0.1, step 0.001)
- reward_ratio (float, default 2.0, range 0.5-5.0, step 0.1)
Warmup rationale: warmup=1 ensures at least one bar of history before evaluating exits.
Intended behavior: Deterministic risk-reward exits.
