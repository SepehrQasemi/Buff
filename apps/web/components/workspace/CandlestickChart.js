import { useEffect, useMemo, useRef, useState } from "react";

const INITIAL_VIEW_BARS = 120;
const DEFAULT_MARKER_DENSITY_LIMIT = 900;
const MARKER_ALIGNMENT_MIN_TOLERANCE_MS = 1000;
const SINGLE_CANDLE_ALIGNMENT_TOLERANCE_MS = 60 * 60 * 1000;
const DRAWINGS_STORAGE_PREFIX = "buff_chart_drawings";
const DRAWINGS_STORAGE_VERSION = 1;
const DEBUG_MISMATCH_DELTA_THRESHOLD_MS = 24 * 60 * 60 * 1000;
const DEBUG_MISMATCH_RATIO_THRESHOLD = 0.3;
const MARKER_PALETTE = [
  { entry: "var(--accent)", exit: "var(--accent-2)", event: "var(--accent-2)" },
  { entry: "var(--chart-up)", exit: "var(--chart-down)", event: "var(--accent-2)" },
  { entry: "rgba(80, 125, 220, 0.9)", exit: "rgba(231, 129, 94, 0.9)", event: "rgba(209, 147, 47, 0.9)" },
];

const SIGNAL_ENTRY_TYPES = new Set(["signal_entry"]);
const SIGNAL_EXIT_TYPES = new Set(["signal_exit"]);
const DRAW_TOOL_LABELS = {
  select: "Select",
  trendline: "Trend",
  hline: "H-Line",
  rectangle: "Rect",
};
const DRAW_TOOL_ORDER = ["select", "trendline", "hline", "rectangle"];

const toEpochMs = (value) => {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 1_000_000_000_000 ? value : value * 1000;
  }
  if (typeof value === "string") {
    const raw = value.trim();
    if (!raw) {
      return null;
    }
    if (/^\d+$/.test(raw)) {
      const parsedNumber = Number(raw);
      if (Number.isFinite(parsedNumber)) {
        return parsedNumber > 1_000_000_000_000 ? parsedNumber : parsedNumber * 1000;
      }
    }
    const parsedString = new Date(raw).getTime();
    return Number.isFinite(parsedString) ? parsedString : null;
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

const resolveMarkerPlacement = (sortedTimesMs, targetMs) => {
  if (!Array.isArray(sortedTimesMs) || sortedTimesMs.length === 0 || targetMs === null) {
    return null;
  }
  // Keep placement deterministic and fail closed for markers too far from the nearest candle.
  const nearestIndex = findNearestIndex(sortedTimesMs, targetMs);
  if (nearestIndex < 0) {
    return null;
  }
  const nearestTime = sortedTimesMs[nearestIndex];
  if (!Number.isFinite(nearestTime)) {
    return null;
  }
  const deltaMs = Math.abs(nearestTime - targetMs);
  if (deltaMs === 0) {
    return { index: nearestIndex, mode: "exact", deltaMs, toleranceMs: 0 };
  }
  if (sortedTimesMs.length === 1) {
    if (deltaMs > SINGLE_CANDLE_ALIGNMENT_TOLERANCE_MS) {
      return null;
    }
    return {
      index: nearestIndex,
      mode: "nearest",
      deltaMs,
      toleranceMs: SINGLE_CANDLE_ALIGNMENT_TOLERANCE_MS,
    };
  }
  const leftGap =
    nearestIndex > 0 ? Math.abs(sortedTimesMs[nearestIndex] - sortedTimesMs[nearestIndex - 1]) : null;
  const rightGap =
    nearestIndex < sortedTimesMs.length - 1
      ? Math.abs(sortedTimesMs[nearestIndex + 1] - sortedTimesMs[nearestIndex])
      : null;
  const nearestGap = [leftGap, rightGap]
    .filter((gap) => Number.isFinite(gap) && gap > 0)
    .reduce((acc, gap) => (acc === null ? gap : Math.min(acc, gap)), null);
  const toleranceMs =
    nearestGap === null
      ? SINGLE_CANDLE_ALIGNMENT_TOLERANCE_MS
      : Math.max(MARKER_ALIGNMENT_MIN_TOLERANCE_MS, Math.floor(nearestGap / 2));
  if (deltaMs > toleranceMs) {
    return null;
  }
  return {
    index: nearestIndex,
    mode: "nearest",
    deltaMs,
    toleranceMs,
  };
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

const formatMs = (value) => {
  if (!Number.isFinite(value)) {
    return "n/a";
  }
  return `${Number(value).toLocaleString("en-US")} ms`;
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

const clamp01 = (value) => Math.max(0, Math.min(1, value));

const nextDrawingId = (drawings) => {
  let max = 0;
  drawings.forEach((drawing) => {
    const match = String(drawing?.id || "").match(/^d_(\d+)$/);
    if (!match) {
      return;
    }
    const parsed = Number.parseInt(match[1], 10);
    if (Number.isFinite(parsed)) {
      max = Math.max(max, parsed);
    }
  });
  return `d_${max + 1}`;
};

const normalizeDrawing = (drawing) => {
  if (!drawing || typeof drawing !== "object") {
    return null;
  }
  const id = String(drawing.id || "").trim();
  const type = String(drawing.type || "").toLowerCase();
  if (!id || !["trendline", "hline", "rectangle"].includes(type)) {
    return null;
  }
  if (type === "hline") {
    const y = toFiniteNumber(drawing.y);
    if (y === null) {
      return null;
    }
    return { id, type, y: clamp01(y) };
  }
  const x1 = toFiniteNumber(drawing.x1);
  const y1 = toFiniteNumber(drawing.y1);
  const x2 = toFiniteNumber(drawing.x2);
  const y2 = toFiniteNumber(drawing.y2);
  if (x1 === null || y1 === null || x2 === null || y2 === null) {
    return null;
  }
  return {
    id,
    type,
    x1: clamp01(x1),
    y1: clamp01(y1),
    x2: clamp01(x2),
    y2: clamp01(y2),
  };
};

const buildDrawingsStorageKey = (scopeKey, version = DRAWINGS_STORAGE_VERSION) => {
  const normalizedScope = String(scopeKey || "").trim();
  if (!normalizedScope) {
    return null;
  }
  return `${DRAWINGS_STORAGE_PREFIX}_v${version}:${normalizedScope}`;
};

const normalizeStoredDrawings = (payload) => {
  if (!payload || typeof payload !== "object") {
    return { drawings: [], invalid: true };
  }
  const versionRaw = payload.version;
  const version =
    versionRaw === undefined || versionRaw === null
      ? DRAWINGS_STORAGE_VERSION
      : Number.parseInt(versionRaw, 10);
  if (!Number.isFinite(version) || version < 1 || version > DRAWINGS_STORAGE_VERSION) {
    return { drawings: [], invalid: true };
  }
  const rows = Array.isArray(payload.drawings) ? payload.drawings : [];
  return {
    drawings: rows.map(normalizeDrawing).filter(Boolean),
    invalid: false,
  };
};

const distanceToSegment = (point, start, end) => {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  if (dx === 0 && dy === 0) {
    return Math.hypot(point.x - start.x, point.y - start.y);
  }
  const ratio = Math.max(
    0,
    Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy))
  );
  const px = start.x + ratio * dx;
  const py = start.y + ratio * dy;
  return Math.hypot(point.x - px, point.y - py);
};

const replaceDrawing = (drawings, nextDrawing) =>
  drawings.map((drawing) => (drawing.id === nextDrawing.id ? nextDrawing : drawing));

export default function CandlestickChart({
  data,
  markers,
  markerSets,
  height = 420,
  overlayControls = true,
  markerDensityLimit = DEFAULT_MARKER_DENSITY_LIMIT,
  enableDrawTools = false,
  drawingScopeKey = "",
}) {
  const containerRef = useRef(null);
  const drawingCanvasRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const crosshairHandlerRef = useRef(null);
  const hoverRafRef = useRef(0);
  const pendingHoverRef = useRef(null);
  const drawInteractionRef = useRef(null);
  const candleByTimeRef = useRef(new Map());
  const markerDetailsByTimeRef = useRef(new Map());
  const [containerWidth, setContainerWidth] = useState(0);
  const [hoverInfo, setHoverInfo] = useState(null);
  const [showTradeMarkers, setShowTradeMarkers] = useState(true);
  const [showSignalMarkers, setShowSignalMarkers] = useState(true);
  const [drawTool, setDrawTool] = useState("select");
  const [drawings, setDrawings] = useState([]);
  const [draftDrawing, setDraftDrawing] = useState(null);
  const [selectedDrawingId, setSelectedDrawingId] = useState("");
  const [debugEnabled, setDebugEnabled] = useState(false);
  const [debugAlignmentSummary, setDebugAlignmentSummary] = useState(null);

  const drawingsEnabled = enableDrawTools && Boolean(String(drawingScopeKey || "").trim());
  const drawingsStorageKey = drawingsEnabled
    ? buildDrawingsStorageKey(String(drawingScopeKey).trim())
    : null;

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

  const pointFromEvent = (event) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      return null;
    }
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    return {
      rect,
      x,
      y,
      nx: clamp01(x / rect.width),
      ny: clamp01(y / rect.height),
    };
  };

  const drawingToPixels = (drawing, width, chartHeight) => {
    if (!drawing) {
      return null;
    }
    if (drawing.type === "hline") {
      return { y: drawing.y * chartHeight };
    }
    return {
      start: { x: drawing.x1 * width, y: drawing.y1 * chartHeight },
      end: { x: drawing.x2 * width, y: drawing.y2 * chartHeight },
    };
  };

  const hitTestDrawing = (drawing, point, width, chartHeight) => {
    if (!drawing || !point) {
      return false;
    }
    if (drawing.type === "hline") {
      const y = drawing.y * chartHeight;
      return Math.abs(point.y - y) <= 6;
    }
    const projected = drawingToPixels(drawing, width, chartHeight);
    if (!projected?.start || !projected?.end) {
      return false;
    }
    if (drawing.type === "trendline") {
      return distanceToSegment(point, projected.start, projected.end) <= 6;
    }
    const left = Math.min(projected.start.x, projected.end.x);
    const right = Math.max(projected.start.x, projected.end.x);
    const top = Math.min(projected.start.y, projected.end.y);
    const bottom = Math.max(projected.start.y, projected.end.y);
    return point.x >= left - 5 && point.x <= right + 5 && point.y >= top - 5 && point.y <= bottom + 5;
  };

  const capturePointer = (event) => {
    if (event.currentTarget?.setPointerCapture) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  };

  const releasePointer = (event) => {
    if (event.currentTarget?.releasePointerCapture) {
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // Ignore if pointer was already released.
      }
    }
  };

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
      setDebugAlignmentSummary(null);
      return;
    }

    const candleTimesMs = normalizedCandleRows.map((row) => row.timeMs);
    const markerDetailsByTime = new Map();
    const chartMarkers = [];
    let invalidTimestampCount = 0;
    let rejectedPlacementCount = 0;
    let suspiciousMismatchCount = 0;
    let maxRejectedDeltaMs = 0;

    sampledMarkers.rows.forEach((marker) => {
      if (marker.__timestampMs === null) {
        invalidTimestampCount += 1;
        return;
      }
      const placement = resolveMarkerPlacement(candleTimesMs, marker.__timestampMs);
      if (!placement) {
        rejectedPlacementCount += 1;
        const nearestIndex = findNearestIndex(candleTimesMs, marker.__timestampMs);
        if (nearestIndex >= 0) {
          const nearestTime = candleTimesMs[nearestIndex];
          if (Number.isFinite(nearestTime)) {
            const rejectedDeltaMs = Math.abs(nearestTime - marker.__timestampMs);
            maxRejectedDeltaMs = Math.max(maxRejectedDeltaMs, rejectedDeltaMs);
            if (rejectedDeltaMs >= DEBUG_MISMATCH_DELTA_THRESHOLD_MS) {
              suspiciousMismatchCount += 1;
            }
          }
        }
        return;
      }
      const candle = normalizedCandleRows[placement.index];
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
        alignedTimestamp: candle.ts,
        alignmentMode: placement.mode,
        alignmentDeltaMs: placement.deltaMs,
        alignmentToleranceMs: placement.toleranceMs,
        price: priceCandidate === null ? candle.close : priceCandidate,
        side: marker?.side ? String(marker.side) : null,
        tradeId: marker?.trade_id ? String(marker.trade_id) : null,
        signalAction: marker?.signal_action ? String(marker.signal_action) : null,
        reasonCode: marker?.reason_code ? String(marker.reason_code) : null,
        riskState: marker?.risk_state ? String(marker.risk_state) : null,
      });
      markerDetailsByTime.set(candle.time, existing);
    });

    const totalMarkers = sampledMarkers.rows.length;
    const rejectedCount = invalidTimestampCount + rejectedPlacementCount;
    const suspiciousRatio = totalMarkers > 0 ? suspiciousMismatchCount / totalMarkers : 0;
    setDebugAlignmentSummary(
      totalMarkers > 0
        ? {
            totalMarkers,
            placedCount: chartMarkers.length,
            rejectedCount,
            invalidTimestampCount,
            rejectedPlacementCount,
            suspiciousMismatchCount,
            suspiciousRatio,
            maxRejectedDeltaMs,
            mismatchSuspected:
              suspiciousMismatchCount > 0 && suspiciousRatio >= DEBUG_MISMATCH_RATIO_THRESHOLD,
          }
        : null
    );
    markerDetailsByTimeRef.current = markerDetailsByTime;
    candleSeriesRef.current.setMarkers(chartMarkers);
  }, [normalizedCandleRows, sampledMarkers]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      const params = new URLSearchParams(window.location.search);
      const debugParam = params.get("debug");
      const legacyDebugParam = params.get("chart_debug");
      const value = String(debugParam ?? legacyDebugParam ?? "").toLowerCase();
      setDebugEnabled(value === "1" || value === "true" || value === "yes");
    } catch {
      setDebugEnabled(false);
    }
  }, []);

  useEffect(() => {
    if (!drawingsStorageKey || typeof window === "undefined") {
      setDrawings([]);
      setDraftDrawing(null);
      setSelectedDrawingId("");
      return;
    }
    try {
      const raw = window.localStorage.getItem(drawingsStorageKey);
      if (!raw) {
        setDrawings([]);
        setDraftDrawing(null);
        setSelectedDrawingId("");
        return;
      }
      const parsed = JSON.parse(raw);
      const normalized = normalizeStoredDrawings(parsed);
      if (normalized.invalid) {
        window.localStorage.removeItem(drawingsStorageKey);
      }
      setDrawings(normalized.drawings);
      setDraftDrawing(null);
      setSelectedDrawingId("");
    } catch {
      try {
        window.localStorage.removeItem(drawingsStorageKey);
      } catch {
        // Storage may be unavailable; keep load fail-closed and non-fatal.
      }
      setDrawings([]);
      setDraftDrawing(null);
      setSelectedDrawingId("");
    }
  }, [drawingsStorageKey]);

  useEffect(() => {
    if (!drawingsStorageKey || typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(
        drawingsStorageKey,
        JSON.stringify({
          version: DRAWINGS_STORAGE_VERSION,
          drawings: drawings.map((drawing) => ({ ...drawing })),
        })
      );
    } catch {
      // Local storage can be unavailable; keep chart interactions non-fatal.
    }
  }, [drawingsStorageKey, drawings]);

  useEffect(() => {
    if (!drawingsEnabled || typeof window === "undefined") {
      return;
    }
    const onKeyDown = (event) => {
      if (!selectedDrawingId) {
        return;
      }
      const isDeleteKey = event.key === "Delete" || event.key === "Backspace";
      if (!isDeleteKey) {
        return;
      }
      const target = event.target;
      const tagName = target?.tagName ? String(target.tagName).toLowerCase() : "";
      const isEditing =
        target?.isContentEditable ||
        tagName === "input" ||
        tagName === "textarea" ||
        tagName === "select";
      if (isEditing) {
        return;
      }
      event.preventDefault();
      setDrawings((current) => current.filter((drawing) => drawing.id !== selectedDrawingId));
      setSelectedDrawingId("");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [drawingsEnabled, selectedDrawingId]);

  useEffect(() => {
    if (!drawingsEnabled || !drawingCanvasRef.current) {
      return;
    }
    const canvas = drawingCanvasRef.current;
    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }
    const width = Math.max(1, containerWidth || containerRef.current?.clientWidth || 1);
    const dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);

    const drawOne = (drawing, options = {}) => {
      const { selected = false, draft = false } = options;
      context.save();
      context.lineWidth = selected ? 2.1 : 1.5;
      context.strokeStyle = selected
        ? "rgba(15, 107, 95, 0.96)"
        : draft
        ? "rgba(15, 107, 95, 0.65)"
        : "rgba(15, 107, 95, 0.84)";
      context.fillStyle = "rgba(15, 107, 95, 0.12)";
      if (draft) {
        context.setLineDash([5, 4]);
      }

      if (drawing.type === "hline") {
        const y = drawing.y * height;
        context.beginPath();
        context.moveTo(0, y);
        context.lineTo(width, y);
        context.stroke();
        context.restore();
        return;
      }

      const projected = drawingToPixels(drawing, width, height);
      if (!projected?.start || !projected?.end) {
        context.restore();
        return;
      }

      if (drawing.type === "trendline") {
        context.beginPath();
        context.moveTo(projected.start.x, projected.start.y);
        context.lineTo(projected.end.x, projected.end.y);
        context.stroke();
        context.restore();
        return;
      }

      const rectX = Math.min(projected.start.x, projected.end.x);
      const rectY = Math.min(projected.start.y, projected.end.y);
      const rectW = Math.abs(projected.end.x - projected.start.x);
      const rectH = Math.abs(projected.end.y - projected.start.y);
      context.strokeRect(rectX, rectY, rectW, rectH);
      context.fillRect(rectX, rectY, rectW, rectH);
      context.restore();
    };

    drawings.forEach((drawing) =>
      drawOne(drawing, {
        selected: drawing.id === selectedDrawingId,
      })
    );
    if (draftDrawing) {
      drawOne(draftDrawing, { draft: true });
    }
  }, [
    containerWidth,
    draftDrawing,
    drawings,
    drawingsEnabled,
    height,
    selectedDrawingId,
  ]);

  const handlePointerDown = (event) => {
    if (!drawingsEnabled) {
      return;
    }
    const target = event.target;
    if (target?.closest?.(".chart-drawtools") || target?.closest?.(".chart-overlay-controls")) {
      return;
    }
    if (event.button !== 0) {
      return;
    }
    const point = pointFromEvent(event);
    if (!point) {
      return;
    }

    if (drawTool === "select") {
      const hit = [...drawings]
        .reverse()
        .find((drawing) => hitTestDrawing(drawing, point, point.rect.width, height));
      if (!hit) {
        setSelectedDrawingId("");
        return;
      }
      setSelectedDrawingId(hit.id);
      drawInteractionRef.current = {
        mode: "move",
        pointerId: event.pointerId,
        drawingId: hit.id,
        original: { ...hit },
        start: { nx: point.nx, ny: point.ny },
      };
      capturePointer(event);
      event.preventDefault();
      return;
    }

    if (drawTool === "hline") {
      const next = normalizeDrawing({
        id: nextDrawingId(drawings),
        type: "hline",
        y: point.ny,
      });
      if (!next) {
        return;
      }
      setDrawings((current) => [...current, next]);
      setSelectedDrawingId(next.id);
      setDrawTool("select");
      event.preventDefault();
      return;
    }

    const nextDraft = normalizeDrawing({
      id: nextDrawingId(drawings),
      type: drawTool,
      x1: point.nx,
      y1: point.ny,
      x2: point.nx,
      y2: point.ny,
    });
    if (!nextDraft) {
      return;
    }
    setDraftDrawing(nextDraft);
    setSelectedDrawingId(nextDraft.id);
    drawInteractionRef.current = {
      mode: "create",
      pointerId: event.pointerId,
      drawingId: nextDraft.id,
    };
    capturePointer(event);
    event.preventDefault();
  };

  const handlePointerMove = (event) => {
    if (!drawingsEnabled || !drawInteractionRef.current) {
      return;
    }
    const interaction = drawInteractionRef.current;
    if (interaction.pointerId !== event.pointerId) {
      return;
    }
    const point = pointFromEvent(event);
    if (!point) {
      return;
    }
    if (interaction.mode === "create") {
      setDraftDrawing((current) =>
        current
          ? normalizeDrawing({
              ...current,
              x2: point.nx,
              y2: point.ny,
            })
          : current
      );
      event.preventDefault();
      return;
    }
    if (interaction.mode === "move") {
      const original = interaction.original;
      const deltaX = point.nx - interaction.start.nx;
      const deltaY = point.ny - interaction.start.ny;
      let moved = null;
      if (original.type === "hline") {
        moved = normalizeDrawing({
          ...original,
          y: original.y + deltaY,
        });
      } else {
        moved = normalizeDrawing({
          ...original,
          x1: original.x1 + deltaX,
          y1: original.y1 + deltaY,
          x2: original.x2 + deltaX,
          y2: original.y2 + deltaY,
        });
      }
      if (moved) {
        setDrawings((current) => replaceDrawing(current, moved));
      }
      event.preventDefault();
    }
  };

  const handlePointerUp = (event) => {
    if (!drawingsEnabled || !drawInteractionRef.current) {
      return;
    }
    const interaction = drawInteractionRef.current;
    if (interaction.pointerId !== event.pointerId) {
      return;
    }
    if (interaction.mode === "create" && draftDrawing) {
      const spanX = Math.abs(draftDrawing.x2 - draftDrawing.x1);
      const spanY = Math.abs(draftDrawing.y2 - draftDrawing.y1);
      const isDegenerate = spanX < 0.002 && spanY < 0.002;
      if (!isDegenerate) {
        setDrawings((current) => [...current, draftDrawing]);
        setSelectedDrawingId(draftDrawing.id);
      } else {
        setSelectedDrawingId("");
      }
      setDraftDrawing(null);
      setDrawTool("select");
    }
    drawInteractionRef.current = null;
    releasePointer(event);
  };

  const handlePointerLeave = (event) => {
    if (!drawingsEnabled || !drawInteractionRef.current) {
      return;
    }
    const interaction = drawInteractionRef.current;
    if (interaction.pointerId !== event.pointerId) {
      return;
    }
    if (interaction.mode === "create") {
      setDraftDrawing(null);
      setSelectedDrawingId("");
      setDrawTool("select");
    }
    drawInteractionRef.current = null;
    releasePointer(event);
  };

  const deleteSelectedDrawing = () => {
    if (!selectedDrawingId) {
      return;
    }
    setDrawings((current) => current.filter((drawing) => drawing.id !== selectedDrawingId));
    setSelectedDrawingId("");
  };

  const resetDrawings = () => {
    setDraftDrawing(null);
    setDrawings([]);
    setSelectedDrawingId("");
    setDrawTool("select");
    if (!drawingsStorageKey || typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.removeItem(drawingsStorageKey);
    } catch {
      // Ignore storage failures; state reset still clears active drawings.
    }
  };

  const debugMarker = hoverInfo?.markers?.[0] || null;
  const debugDeltaText = Number.isFinite(debugMarker?.alignmentDeltaMs)
    ? `${debugMarker.alignmentDeltaMs} ms`
    : "n/a";
  const debugModeText = debugMarker?.alignmentMode ? String(debugMarker.alignmentMode) : "n/a";
  const debugMarkerTimestamp = debugMarker?.timestamp ? String(debugMarker.timestamp) : "n/a";
  const mismatchDebugWarning =
    debugEnabled && debugAlignmentSummary?.mismatchSuspected
      ? `Potential timestamp unit mismatch detected. ${debugAlignmentSummary.suspiciousMismatchCount}/${debugAlignmentSummary.totalMarkers} markers exceeded ${formatMs(DEBUG_MISMATCH_DELTA_THRESHOLD_MS)} with max rejected delta ${formatMs(debugAlignmentSummary.maxRejectedDeltaMs)}.`
      : null;

  if (!normalizedCandleRows.length) {
    return (
      <div className="chart-empty" style={{ height }}>
        <p>No OHLCV candles available for this range.</p>
      </div>
    );
  }

  return (
    <div
      className="chart-frame"
      ref={containerRef}
      style={{ height, position: "relative" }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerLeave}
    >
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
      {drawingsEnabled && (
        <div className="chart-drawtools">
          {DRAW_TOOL_ORDER.map((tool) => (
            <button
              key={tool}
              type="button"
              className={`secondary ${drawTool === tool ? "chart-tool-active" : ""}`}
              onClick={() => setDrawTool(tool)}
            >
              {DRAW_TOOL_LABELS[tool]}
            </button>
          ))}
          <button
            type="button"
            className="secondary"
            onClick={deleteSelectedDrawing}
            disabled={!selectedDrawingId}
          >
            Delete
          </button>
          <button type="button" className="secondary" onClick={resetDrawings}>
            Reset
          </button>
        </div>
      )}
      {drawingsEnabled && (
        <canvas
          ref={drawingCanvasRef}
          className="chart-drawing-layer"
          aria-hidden="true"
        />
      )}
      {debugEnabled && (
        <div className="chart-debug-panel" data-testid="chart-debug-panel">
          <div className="chart-debug-title">Chart Debug</div>
          {mismatchDebugWarning && <div className="chart-debug-warning">{mismatchDebugWarning}</div>}
          <div className="chart-debug-row">
            <span>Candle ts</span>
            <strong>{hoverInfo?.timestamp ? String(hoverInfo.timestamp) : "n/a"}</strong>
          </div>
          <div className="chart-debug-row">
            <span>Marker ts</span>
            <strong>{debugMarkerTimestamp}</strong>
          </div>
          <div className="chart-debug-row">
            <span>Align mode</span>
            <strong>{debugModeText}</strong>
          </div>
          <div className="chart-debug-row">
            <span>Delta</span>
            <strong>{debugDeltaText}</strong>
          </div>
          <div className="chart-debug-row">
            <span>Placed</span>
            <strong>{debugAlignmentSummary ? debugAlignmentSummary.placedCount : "n/a"}</strong>
          </div>
          <div className="chart-debug-row">
            <span>Rejected</span>
            <strong>{debugAlignmentSummary ? debugAlignmentSummary.rejectedCount : "n/a"}</strong>
          </div>
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
