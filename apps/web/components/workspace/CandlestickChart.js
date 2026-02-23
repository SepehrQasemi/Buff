import { useEffect, useMemo, useRef, useState } from "react";

const INITIAL_VIEW_BARS = 120;
const DEFAULT_MARKER_DENSITY_LIMIT = 900;
const MARKER_PALETTE = [
  { entry: "var(--accent)", exit: "var(--accent-2)", event: "var(--accent-2)" },
  { entry: "var(--chart-up)", exit: "var(--chart-down)", event: "var(--accent-2)" },
  { entry: "rgba(80, 125, 220, 0.9)", exit: "rgba(231, 129, 94, 0.9)", event: "rgba(209, 147, 47, 0.9)" },
];

const SIGNAL_ENTRY_TYPES = new Set(["signal_entry"]);
const SIGNAL_EXIT_TYPES = new Set(["signal_exit"]);

const toEpochMs = (value) => {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 1_000_000_000_000 ? value : value * 1000;
  }
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : null;
};

const toEpochSeconds = (value) => {
  const ms = toEpochMs(value);
  if (ms === null) {
    return null;
  }
  return Math.floor(ms / 1000);
};

const toFiniteNumber = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const readCssVar = (name, fallback) => {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = window
    .getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
};

const findNearestIndex = (sortedTimesMs, targetMs) => {
  if (!sortedTimesMs.length || targetMs === null) {
    return -1;
  }
  let low = 0;
  let high = sortedTimesMs.length - 1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const value = sortedTimesMs[mid];
    if (value === targetMs) {
      return mid;
    }
    if (value < targetMs) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  if (low <= 0) {
    return 0;
  }
  if (low >= sortedTimesMs.length) {
    return sortedTimesMs.length - 1;
  }
  const leftDistance = Math.abs(sortedTimesMs[low - 1] - targetMs);
  const rightDistance = Math.abs(sortedTimesMs[low] - targetMs);
  return leftDistance <= rightDistance ? low - 1 : low;
};

const normalizeMarkerSets = (markerSets, markers) => {
  if (Array.isArray(markerSets) && markerSets.length) {
    return markerSets;
  }
  if (Array.isArray(markers) && markers.length) {
    return [{ label: "Trades", markers }];
  }
  return [];
};

const classifyMarkerKind = (markerType, marker) => {
  const normalizedType = String(markerType || "").toLowerCase();
  if (normalizedType.startsWith("signal")) {
    return "signal";
  }
  if (marker?.signal_action || marker?.decision_id || marker?.reason_code) {
    return "signal";
  }
  return "trade";
};

const flattenMarkers = (sets) =>
  sets.flatMap((set, setIndex) => {
    const palette = MARKER_PALETTE[setIndex % MARKER_PALETTE.length];
    const entryColor = set?.entryColor || palette.entry;
    const exitColor = set?.exitColor || palette.exit;
    const eventColor = set?.eventColor || palette.event;
    const sourceLabel = String(set?.label || set?.runId || "Run");
    const setMarkers = Array.isArray(set?.markers) ? set.markers : [];
    return setMarkers.map((marker, markerIndex) => {
      const markerType = String(marker?.marker_type || "event").toLowerCase();
      return {
        ...marker,
        __runId: set?.runId ? String(set.runId) : "",
        __label: sourceLabel,
        __entryColor: entryColor,
        __exitColor: exitColor,
        __eventColor: eventColor,
        __type: markerType,
        __kind: classifyMarkerKind(markerType, marker),
        __setIndex: setIndex,
        __markerIndex: markerIndex,
      };
    });
  });

const formatPrice = (value) => {
  if (!Number.isFinite(value)) {
    return "n/a";
  }
  return value.toLocaleString("en-US", { maximumFractionDigits: 6 });
};

const formatTimestamp = (value) => {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  return String(value);
};

const downsampleMarkers = (rows, limit) => {
  if (!Array.isArray(rows) || rows.length <= limit) {
    return { rows: Array.isArray(rows) ? rows : [], downsampled: false };
  }
  const result = [];
  const step = rows.length / limit;
  for (let index = 0; index < limit; index += 1) {
    const sourceIndex = Math.floor(index * step);
    const marker = rows[sourceIndex];
    if (!marker) {
      continue;
    }
    if (result.length > 0 && result[result.length - 1].__uid === marker.__uid) {
      continue;
    }
    result.push(marker);
  }
  const last = rows[rows.length - 1];
  if (last && (result.length === 0 || result[result.length - 1].__uid !== last.__uid)) {
    result.push(last);
  }
  return { rows: result, downsampled: true };
};

export default function CandlestickChart({
  data,
  markers,
  markerSets,
  height = 420,
  overlayControls = true,
  markerDensityLimit = DEFAULT_MARKER_DENSITY_LIMIT,
}) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const crosshairHandlerRef = useRef(null);
  const hoverRafRef = useRef(0);
  const pendingHoverRef = useRef(null);
  const candleByTimeRef = useRef(new Map());
  const markerDetailsByTimeRef = useRef(new Map());
  const [containerWidth, setContainerWidth] = useState(0);
  const [hoverInfo, setHoverInfo] = useState(null);
  const [showTradeMarkers, setShowTradeMarkers] = useState(true);
  const [showSignalMarkers, setShowSignalMarkers] = useState(true);

  const normalizedCandleRows = useMemo(() => {
    const rows = Array.isArray(data) ? data : [];
    return rows
      .map((item) => {
        const time = toEpochSeconds(item?.ts);
        const timeMs = toEpochMs(item?.ts);
        const open = toFiniteNumber(item?.open);
        const high = toFiniteNumber(item?.high);
        const low = toFiniteNumber(item?.low);
        const close = toFiniteNumber(item?.close);
        const volume = toFiniteNumber(item?.volume);
        if (
          time === null ||
          timeMs === null ||
          open === null ||
          high === null ||
          low === null ||
          close === null ||
          volume === null
        ) {
          return null;
        }
        return {
          time,
          timeMs,
          ts: String(item.ts),
          open,
          high,
          low,
          close,
          volume,
        };
      })
      .filter(Boolean);
  }, [data]);

  const normalizedMarkerRows = useMemo(() => {
    const sets = normalizeMarkerSets(markerSets, markers);
    return flattenMarkers(sets)
      .map((marker, index) => ({
        ...marker,
        __uid: `${marker.__setIndex}:${marker.__markerIndex}:${index}`,
        __timestampMs: toEpochMs(marker.timestamp),
      }))
      .sort((left, right) => {
        if (left.__timestampMs !== null && right.__timestampMs !== null) {
          if (left.__timestampMs !== right.__timestampMs) {
            return left.__timestampMs - right.__timestampMs;
          }
        } else if (left.__timestampMs !== null) {
          return -1;
        } else if (right.__timestampMs !== null) {
          return 1;
        }
        return left.__uid.localeCompare(right.__uid);
      });
  }, [markerSets, markers]);

  const markerCounts = useMemo(
    () =>
      normalizedMarkerRows.reduce(
        (acc, marker) => {
          if (marker.__kind === "signal") {
            acc.signal += 1;
          } else {
            acc.trade += 1;
          }
          return acc;
        },
        { trade: 0, signal: 0 }
      ),
    [normalizedMarkerRows]
  );

  const filteredMarkerRows = useMemo(
    () =>
      normalizedMarkerRows.filter((marker) => {
        if (marker.__kind === "signal") {
          return showSignalMarkers;
        }
        return showTradeMarkers;
      }),
    [normalizedMarkerRows, showSignalMarkers, showTradeMarkers]
  );

  const sampledMarkers = useMemo(
    () => downsampleMarkers(filteredMarkerRows, Math.max(100, markerDensityLimit)),
    [filteredMarkerRows, markerDensityLimit]
  );

  useEffect(() => {
    if (!containerRef.current || typeof window === "undefined") {
      return undefined;
    }
    const element = containerRef.current;
    const observer = new ResizeObserver((entries) => {
      if (!entries.length) {
        return;
      }
      const width = Math.max(0, Math.floor(entries[0].contentRect.width));
      setContainerWidth(width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let active = true;
    let cleanup = null;

    const scheduleHover = (nextHover) => {
      pendingHoverRef.current = nextHover;
      if (hoverRafRef.current || typeof window === "undefined") {
        return;
      }
      hoverRafRef.current = window.requestAnimationFrame(() => {
        hoverRafRef.current = 0;
        setHoverInfo(pendingHoverRef.current);
      });
    };

    const create = async () => {
      if (!containerRef.current || typeof window === "undefined") {
        return;
      }
      const { CrosshairMode, ColorType, LineStyle, createChart } = await import("lightweight-charts");
      if (!active || !containerRef.current) {
        return;
      }

      const upColor = readCssVar("--chart-up", "#1a7f4f");
      const downColor = readCssVar("--chart-down", "#b64b39");
      const borderColor = readCssVar("--border", "#d6cfc2");
      const textColor = readCssVar("--muted", "#6b737f");
      const chartBg = readCssVar("--chart-bg", "#fcfbf7");

      const chart = createChart(containerRef.current, {
        width: Math.max(1, containerRef.current.clientWidth),
        height,
        autoSize: false,
        layout: {
          background: { type: ColorType.Solid, color: chartBg },
          textColor,
          fontFamily: "Space Mono, SFMono-Regular, Consolas, monospace",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "rgba(27, 32, 36, 0.06)" },
          horzLines: { color: "rgba(27, 32, 36, 0.06)" },
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          horzLine: { style: LineStyle.Solid, color: "rgba(27, 32, 36, 0.3)" },
          vertLine: { style: LineStyle.Solid, color: "rgba(27, 32, 36, 0.3)" },
        },
        rightPriceScale: {
          borderColor,
          scaleMargins: { top: 0.12, bottom: 0.1 },
        },
        timeScale: {
          borderColor,
          rightOffset: 6,
          barSpacing: 8,
          minBarSpacing: 3,
          fixLeftEdge: true,
          timeVisible: true,
          secondsVisible: false,
        },
        handleScale: {
          axisPressedMouseMove: true,
          mouseWheel: true,
          pinch: true,
        },
        handleScroll: {
          mouseWheel: true,
          pressedMouseMove: true,
          horzTouchDrag: true,
          vertTouchDrag: false,
        },
      });

      const candleSeries = chart.addCandlestickSeries({
        upColor,
        downColor,
        borderUpColor: upColor,
        borderDownColor: downColor,
        wickUpColor: upColor,
        wickDownColor: downColor,
        lastValueVisible: true,
        priceLineVisible: false,
      });

      const crosshairHandler = (param) => {
        if (!param?.point || !param?.time || !param.seriesData || !candleSeriesRef.current) {
          scheduleHover(null);
          return;
        }
        const bar = param.seriesData.get(candleSeriesRef.current);
        if (!bar) {
          scheduleHover(null);
          return;
        }
        const candle = candleByTimeRef.current.get(bar.time) || null;
        const markerDetails = markerDetailsByTimeRef.current.get(bar.time) || [];
        scheduleHover({
          x: Math.round(param.point.x),
          y: Math.round(param.point.y),
          time: bar.time,
          timestamp: candle?.ts || formatTimestamp(bar.time),
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
          markers: markerDetails.slice(0, 3),
        });
      };

      chart.subscribeCrosshairMove(crosshairHandler);
      chartRef.current = chart;
      candleSeriesRef.current = candleSeries;
      crosshairHandlerRef.current = crosshairHandler;

      cleanup = () => {
        if (chartRef.current && crosshairHandlerRef.current) {
          chartRef.current.unsubscribeCrosshairMove(crosshairHandlerRef.current);
        }
        if (hoverRafRef.current && typeof window !== "undefined") {
          window.cancelAnimationFrame(hoverRafRef.current);
          hoverRafRef.current = 0;
        }
        crosshairHandlerRef.current = null;
        candleSeriesRef.current = null;
        chart.remove();
        chartRef.current = null;
      };
    };

    create();
    return () => {
      active = false;
      if (cleanup) {
        cleanup();
      } else if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        candleSeriesRef.current = null;
        crosshairHandlerRef.current = null;
      }
      if (hoverRafRef.current && typeof window !== "undefined") {
        window.cancelAnimationFrame(hoverRafRef.current);
        hoverRafRef.current = 0;
      }
    };
  }, [height]);

  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current) {
      return;
    }
    chartRef.current.applyOptions({
      width: Math.max(1, containerWidth || containerRef.current?.clientWidth || 1),
      height,
    });
    chartRef.current.timeScale().fitContent();
  }, [containerWidth, height]);

  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current) {
      return;
    }
    candleByTimeRef.current = new Map(normalizedCandleRows.map((row) => [row.time, row]));
    candleSeriesRef.current.setData(
      normalizedCandleRows.map((row) => ({
        time: row.time,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
      }))
    );
    markerDetailsByTimeRef.current = new Map();
    if (normalizedCandleRows.length > 0) {
      const from = Math.max(0, normalizedCandleRows.length - INITIAL_VIEW_BARS);
      const to = normalizedCandleRows.length + 2;
      chartRef.current.timeScale().setVisibleLogicalRange({ from, to });
    }
  }, [normalizedCandleRows]);

  useEffect(() => {
    if (!candleSeriesRef.current || !normalizedCandleRows.length) {
      if (candleSeriesRef.current) {
        candleSeriesRef.current.setMarkers([]);
      }
      markerDetailsByTimeRef.current = new Map();
      return;
    }

    const candleTimesMs = normalizedCandleRows.map((row) => row.timeMs);
    const markerDetailsByTime = new Map();
    const chartMarkers = [];

    sampledMarkers.rows.forEach((marker) => {
      const nearestIndex = findNearestIndex(candleTimesMs, marker.__timestampMs);
      if (nearestIndex < 0) {
        return;
      }
      const candle = normalizedCandleRows[nearestIndex];
      if (!candle) {
        return;
      }
      const markerType = marker.__type;
      const isTradeMarker = marker.__kind === "trade";
      let shape = "circle";
      let position = "inBar";
      let color = marker.__eventColor;

      if (isTradeMarker) {
        if (markerType === "entry") {
          shape = "arrowUp";
          position = "belowBar";
          color = marker.__entryColor;
        } else if (markerType === "exit") {
          shape = "arrowDown";
          position = "aboveBar";
          color = marker.__exitColor;
        } else {
          shape = "circle";
          position = "inBar";
          color = marker.__eventColor;
        }
      } else if (SIGNAL_ENTRY_TYPES.has(markerType)) {
        shape = "circle";
        position = "belowBar";
        color = marker.__entryColor;
      } else if (SIGNAL_EXIT_TYPES.has(markerType)) {
        shape = "circle";
        position = "aboveBar";
        color = marker.__exitColor;
      } else {
        shape = "square";
        position = "inBar";
        color = marker.__eventColor;
      }

      chartMarkers.push({
        time: candle.time,
        position,
        color,
        shape,
      });

      const existing = markerDetailsByTime.get(candle.time) || [];
      const priceCandidate = toFiniteNumber(marker?.price);
      existing.push({
        uid: marker.__uid,
        kind: marker.__kind,
        type: markerType,
        sourceLabel: marker.__label || marker.__runId || "Run",
        runId: marker.__runId || "",
        timestamp: formatTimestamp(marker?.timestamp || candle.ts),
        price: priceCandidate === null ? candle.close : priceCandidate,
        side: marker?.side ? String(marker.side) : null,
        tradeId: marker?.trade_id ? String(marker.trade_id) : null,
        signalAction: marker?.signal_action ? String(marker.signal_action) : null,
        reasonCode: marker?.reason_code ? String(marker.reason_code) : null,
        riskState: marker?.risk_state ? String(marker.risk_state) : null,
      });
      markerDetailsByTime.set(candle.time, existing);
    });

    markerDetailsByTimeRef.current = markerDetailsByTime;
    candleSeriesRef.current.setMarkers(chartMarkers);
  }, [normalizedCandleRows, sampledMarkers]);

  if (!normalizedCandleRows.length) {
    return (
      <div className="chart-empty" style={{ height }}>
        <p>No OHLCV candles available for this range.</p>
      </div>
    );
  }

  return (
    <div className="chart-frame" ref={containerRef} style={{ height, position: "relative" }}>
      {overlayControls && (markerCounts.trade > 0 || markerCounts.signal > 0) && (
        <div className="chart-overlay-controls">
          {markerCounts.trade > 0 && (
            <label className="chart-overlay-toggle">
              <input
                type="checkbox"
                checked={showTradeMarkers}
                onChange={(event) => setShowTradeMarkers(event.target.checked)}
              />
              <span>Trades ({markerCounts.trade})</span>
            </label>
          )}
          {markerCounts.signal > 0 && (
            <label className="chart-overlay-toggle">
              <input
                type="checkbox"
                checked={showSignalMarkers}
                onChange={(event) => setShowSignalMarkers(event.target.checked)}
              />
              <span>Signals ({markerCounts.signal})</span>
            </label>
          )}
          {sampledMarkers.downsampled && (
            <span className="chart-overlay-note">
              Showing {sampledMarkers.rows.length}/{filteredMarkerRows.length} markers
            </span>
          )}
        </div>
      )}
      {hoverInfo && (
        <div
          className="chart-tooltip"
          style={{
            left: Math.max(8, Math.min((hoverInfo.x || 0) + 12, Math.max(8, containerWidth - 250))),
            top: Math.max(8, Math.min((hoverInfo.y || 0) + 12, Math.max(8, height - 170))),
          }}
        >
          <div className="chart-tooltip-title">{formatTimestamp(hoverInfo.timestamp)}</div>
          <div className="chart-tooltip-row">O: {formatPrice(hoverInfo.open)}</div>
          <div className="chart-tooltip-row">H: {formatPrice(hoverInfo.high)}</div>
          <div className="chart-tooltip-row">L: {formatPrice(hoverInfo.low)}</div>
          <div className="chart-tooltip-row">C: {formatPrice(hoverInfo.close)}</div>
          {Array.isArray(hoverInfo.markers) && hoverInfo.markers.length > 0 && (
            <>
              <div className="chart-tooltip-divider" />
              {hoverInfo.markers.map((marker) => (
                <div key={marker.uid} className="chart-tooltip-marker">
                  <div className="chart-tooltip-row">
                    {marker.sourceLabel} {marker.kind}
                  </div>
                  {marker.signalAction && (
                    <div className="chart-tooltip-row">Action: {marker.signalAction}</div>
                  )}
                  {marker.tradeId && (
                    <div className="chart-tooltip-row">Trade: {marker.tradeId}</div>
                  )}
                  {marker.reasonCode && (
                    <div className="chart-tooltip-row">Reason: {marker.reasonCode}</div>
                  )}
                  {marker.riskState && (
                    <div className="chart-tooltip-row">Risk: {marker.riskState}</div>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
