def get_schema():
    return {
        "id": "demo_threshold",
        "name": "Demo Threshold",
        "version": "1.0.0",
        "author": "Buff Team",
        "category": "trend",
        "warmup_bars": 5,
        "inputs": {"series": ["close"], "indicators": ["demo_sma"]},
        "params": [
            {
                "name": "threshold",
                "type": "float",
                "default": 0.0,
                "min": 0.0,
                "max": 10.0,
                "description": "Offset applied around SMA before entering/exiting.",
            }
        ],
        "outputs": {"intents": ["HOLD", "ENTER_LONG", "EXIT_LONG"], "provides_confidence": False},
    }


def _last(values):
    if not values:
        return None
    return values[-1]


def _slice_series(values, bar_index):
    if values is None:
        return ()
    if bar_index is None:
        return values
    try:
        return values[: bar_index + 1]
    except Exception:
        return tuple(values)[: bar_index + 1]


def on_bar(ctx):
    warmup_bars = ctx.warmup_bars or 0
    if ctx.bar_index is not None and ctx.bar_index < warmup_bars:
        return {"intent": "HOLD", "tags": ["warmup"]}

    bar_index = ctx.bar_index
    close_values = _slice_series(ctx.series.get("close") or (), bar_index)
    close_price = _last(close_values)
    indicator_values = ctx.indicators.get("demo_sma") or {}
    sma_values = _slice_series(indicator_values.get("sma") or (), bar_index)
    sma_value = _last(sma_values)

    if close_price is None or sma_value is None:
        return {"intent": "HOLD", "tags": ["no_data"]}

    try:
        threshold = float(ctx.params.get("threshold", 0.0))
    except (TypeError, ValueError):
        threshold = 0.0

    if close_price > sma_value + threshold:
        return {"intent": "ENTER_LONG", "tags": ["sma_breakout"]}
    if close_price < sma_value - threshold:
        return {"intent": "EXIT_LONG", "tags": ["sma_reversal"]}
    return {"intent": "HOLD", "tags": ["sma_hold"]}
