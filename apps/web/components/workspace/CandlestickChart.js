import { useEffect, useMemo, useRef, useState } from "react";

const INITIAL_VIEW_BARS = 120;
const MARKER_PALETTE = [
  { entry: "var(--accent)", exit: "var(--accent-2)" },
  { entry: "var(--chart-up)", exit: "var(--chart-down)" },
  { entry: "rgba(80, 125, 220, 0.9)", exit: "rgba(231, 129, 94, 0.9)" },
];

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
    return [{ label: "Run", markers }];
  }
  return [];
};

const flattenMarkers = (sets) =>
  sets.flatMap((set, index) => {
    const palette = MARKER_PALETTE[index % MARKER_PALETTE.length];
    const entryColor = set?.entryColor || palette.entry;
    const exitColor = set?.exitColor || palette.exit;
    const sourceLabel = String(set?.label || set?.runId || "Run");
    return (Array.isArray(set?.markers) ? set.markers : []).map((marker) => ({
      ...marker,
      __runId: set?.runId ? String(set.runId) : "",
      __label: sourceLabel,
      __entryColor: entryColor,
      __exitColor: exitColor,
    }));
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

export default function CandlestickChart({ data, markers, markerSets, height = 420 }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const crosshairHandlerRef = useRef(null);
  const candlesRef = useRef([]);
  const candleByTimeRef = useRef(new Map());
  const markerDetailsByTimeRef = useRef(new Map());
  const [containerWidth, setContainerWidth] = useState(0);
  const [hoverInfo, setHoverInfo] = useState(null);

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
    return flattenMarkers(sets);
  }, [markerSets, markers]);

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

    const create = async () => {
      if (!containerRef.current || typeof window === "undefined") {
        return;
      }
      const {
        CrosshairMode,
        ColorType,
        LineStyle,
        createChart,
      } = await import("lightweight-charts");
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
        if (
          !param?.point ||
          !param?.time ||
          !param.seriesData ||
          !candleSeriesRef.current
        ) {
          setHoverInfo(null);
          return;
        }
        const bar = param.seriesData.get(candleSeriesRef.current);
        if (!bar) {
          setHoverInfo(null);
          return;
        }
        const candle = candleByTimeRef.current.get(bar.time) || null;
        const markerDetail = markerDetailsByTimeRef.current.get(bar.time) || null;
        setHoverInfo({
          x: Math.round(param.point.x),
          y: Math.round(param.point.y),
          time: bar.time,
          timestamp: candle?.ts || formatTimestamp(bar.time),
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
          marker: markerDetail,
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
    candlesRef.current = normalizedCandleRows;
    candleByTimeRef.current = new Map(
      normalizedCandleRows.map((row) => [row.time, row])
    );
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
    const candleTimesToRows = new Map(
      normalizedCandleRows.map((row) => [row.time, row])
    );
    const seriesMarkers = [];
    const markerDetailsByTime = new Map();

    normalizedMarkerRows.forEach((marker) => {
      const markerTimeMs = toEpochMs(marker?.timestamp);
      const nearestIndex = findNearestIndex(candleTimesMs, markerTimeMs);
      if (nearestIndex < 0) {
        return;
      }
      const candle = normalizedCandleRows[nearestIndex];
      if (!candle) {
        return;
      }
      const markerType = String(marker?.marker_type || "event").toLowerCase();
      const isEntry = markerType === "entry";
      const shape = isEntry ? "arrowUp" : "arrowDown";
      const position = isEntry ? "belowBar" : "aboveBar";
      const color = isEntry ? marker.__entryColor : marker.__exitColor;
      const priceCandidate = toFiniteNumber(marker?.price);
      const priceValue = priceCandidate === null ? candle.close : priceCandidate;
      const details = {
        type: markerType,
        sourceLabel: marker.__label || marker.__runId || "Run",
        runId: marker.__runId || "",
        timestamp: formatTimestamp(marker?.timestamp || candle.ts),
        price: priceValue,
        side: marker?.side ? String(marker.side) : null,
        tradeId: marker?.trade_id ? String(marker.trade_id) : null,
      };

      seriesMarkers.push({
        time: candle.time,
        position,
        color,
        shape,
      });
      if (!markerDetailsByTime.has(candle.time)) {
        markerDetailsByTime.set(candle.time, details);
      }
    });

    markerDetailsByTimeRef.current = markerDetailsByTime;
    candleSeriesRef.current.setMarkers(seriesMarkers);

    if (hoverInfo?.time && !candleTimesToRows.has(hoverInfo.time)) {
      setHoverInfo(null);
    }
  }, [normalizedCandleRows, normalizedMarkerRows, hoverInfo?.time]);

  if (!normalizedCandleRows.length) {
    return (
      <div className="chart-empty" style={{ height }}>
        <p>No OHLCV candles available for this range.</p>
      </div>
    );
  }

  return (
    <div className="chart-frame" ref={containerRef} style={{ height, position: "relative" }}>
      {hoverInfo && (
        <div
          className="chart-tooltip"
          style={{
            left: Math.max(8, Math.min((hoverInfo.x || 0) + 12, Math.max(8, containerWidth - 220))),
            top: Math.max(8, Math.min((hoverInfo.y || 0) + 12, Math.max(8, height - 96))),
          }}
        >
          <div className="chart-tooltip-title">{formatTimestamp(hoverInfo.timestamp)}</div>
          <div className="chart-tooltip-row">O: {formatPrice(hoverInfo.open)}</div>
          <div className="chart-tooltip-row">H: {formatPrice(hoverInfo.high)}</div>
          <div className="chart-tooltip-row">L: {formatPrice(hoverInfo.low)}</div>
          <div className="chart-tooltip-row">C: {formatPrice(hoverInfo.close)}</div>
          {hoverInfo.marker && (
            <>
              <div className="chart-tooltip-divider" />
              <div className="chart-tooltip-row">
                {hoverInfo.marker.sourceLabel} {hoverInfo.marker.type}
              </div>
              {hoverInfo.marker.tradeId && (
                <div className="chart-tooltip-row">Trade: {hoverInfo.marker.tradeId}</div>
              )}
              {hoverInfo.marker.side && (
                <div className="chart-tooltip-row">Side: {hoverInfo.marker.side}</div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
