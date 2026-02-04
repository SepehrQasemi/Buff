export default function FiltersBar({ filters, onChange, onRefresh, disabled }) {
  const update = (updates) => {
    onChange({ ...filters, ...updates });
  };

  return (
    <div className="toolbar">
      <label>
        Symbol(s)
        <input
          value={filters.symbol}
          onChange={(event) => update({ symbol: event.target.value, page: 1 })}
          placeholder="BTCUSDT, ETHUSDT"
        />
      </label>
      <label>
        Action
        <input
          value={filters.action}
          onChange={(event) => update({ action: event.target.value, page: 1 })}
          placeholder="placed, blocked"
        />
      </label>
      <label>
        Severity
        <input
          value={filters.severity}
          onChange={(event) => update({ severity: event.target.value, page: 1 })}
          placeholder="ERROR, RED"
        />
      </label>
      <label>
        Reason code
        <input
          value={filters.reason_code}
          onChange={(event) => update({ reason_code: event.target.value, page: 1 })}
          placeholder="RISK_BLOCK"
        />
      </label>
      <label>
        Start
        <input
          value={filters.start_ts}
          onChange={(event) => update({ start_ts: event.target.value, page: 1 })}
          placeholder="2026-01-01T00:00:00Z"
        />
      </label>
      <label>
        End
        <input
          value={filters.end_ts}
          onChange={(event) => update({ end_ts: event.target.value, page: 1 })}
          placeholder="2026-01-02T00:00:00Z"
        />
      </label>
      <label>
        Page size
        <select
          value={filters.page_size}
          onChange={(event) => update({ page_size: Number(event.target.value), page: 1 })}
        >
          {[10, 25, 50, 100].map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </label>
      <button className="secondary" onClick={onRefresh} disabled={disabled}>
        Refresh
      </button>
    </div>
  );
}
