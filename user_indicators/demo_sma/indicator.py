def get_schema():
    return {
        "id": "demo_sma",
        "name": "Demo SMA",
        "version": "1.0.0",
        "author": "Buff Team",
        "category": "trend",
        "inputs": ["close"],
        "outputs": ["sma"],
        "params": [
            {
                "name": "period",
                "type": "int",
                "default": 5,
                "min": 1,
                "max": 200,
                "description": "Lookback period for the SMA.",
            }
        ],
        "warmup_bars": 5,
        "nan_policy": "propagate",
    }


def compute(ctx):
    series = ctx.series.get("close") or ()
    bar_index = ctx.bar_index
    if bar_index is not None:
        try:
            series = series[: bar_index + 1]
        except Exception:
            series = tuple(series)[: bar_index + 1]
    try:
        period = int(ctx.params.get("period", 1))
    except (TypeError, ValueError):
        period = 1
    if period < 1:
        period = 1
    if not series:
        return {"sma": 0.0}
    window = series[-period:] if len(series) >= period else series
    sma = sum(window) / len(window)
    return {"sma": float(sma)}
