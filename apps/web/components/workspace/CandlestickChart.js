import { useEffect, useMemo, useRef, useState } from "react";

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const toTime = (value) => {
  if (!value) {
    return null;
  }
  const ts = new Date(value).getTime();
  return Number.isFinite(ts) ? ts : null;
};

const findNearestIndex = (sortedTimes, target) => {
  if (!sortedTimes.length || target === null) {
    return -1;
  }
  let low = 0;
  let high = sortedTimes.length - 1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const value = sortedTimes[mid];
    if (value === target) {
      return mid;
    }
    if (value < target) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return clamp(low, 0, sortedTimes.length - 1);
};

export default function CandlestickChart({ data, markers, height = 420 }) {
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const [size, setSize] = useState({ width: 0, height });
  const [view, setView] = useState({ start: 0, end: 0 });
  const dragRef = useRef(null);
  const candleWidthRef = useRef(6);

  const times = useMemo(
    () => (Array.isArray(data) ? data.map((item) => toTime(item.ts)) : []),
    [data]
  );

  useEffect(() => {
    if (!Array.isArray(data) || data.length === 0) {
      setView({ start: 0, end: 0 });
      return;
    }
    const windowSize = clamp(data.length, 30, 120);
    const end = data.length;
    const start = clamp(end - windowSize, 0, end - 1);
    setView({ start, end });
  }, [data]);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      if (!entries.length) {
        return;
      }
      const { width, height: observedHeight } = entries[0].contentRect;
      setSize({ width, height: observedHeight });
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data || !data.length) {
      return;
    }
    const width = Math.floor(size.width || 0);
    const heightPx = Math.floor(size.height || height);
    if (width <= 0 || heightPx <= 0) {
      return;
    }
    canvas.width = width;
    canvas.height = heightPx;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    ctx.clearRect(0, 0, width, heightPx);
    ctx.fillStyle = "var(--chart-bg)";
    ctx.fillRect(0, 0, width, heightPx);

    const padding = { top: 20, right: 16, bottom: 28, left: 56 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = heightPx - padding.top - padding.bottom;
    const visibleCount = Math.max(view.end - view.start, 1);
    const candleWidth = plotWidth / visibleCount;
    candleWidthRef.current = candleWidth;

    const visible = data.slice(view.start, view.end);
    if (!visible.length) {
      return;
    }

    let minPrice = Math.min(...visible.map((candle) => candle.low));
    let maxPrice = Math.max(...visible.map((candle) => candle.high));
    if (minPrice === maxPrice) {
      minPrice -= 1;
      maxPrice += 1;
    }
    const paddingPct = (maxPrice - minPrice) * 0.08;
    minPrice -= paddingPct;
    maxPrice += paddingPct;

    const priceToY = (price) => {
      const ratio = (price - minPrice) / (maxPrice - minPrice || 1);
      return padding.top + plotHeight * (1 - ratio);
    };

    ctx.strokeStyle = "rgba(27, 32, 36, 0.12)";
    ctx.lineWidth = 1;
    const gridLines = 4;
    for (let i = 0; i <= gridLines; i += 1) {
      const y = padding.top + (plotHeight / gridLines) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();
    }

    ctx.fillStyle = "var(--muted)";
    ctx.font = "12px var(--font-mono)";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= gridLines; i += 1) {
      const value = maxPrice - ((maxPrice - minPrice) / gridLines) * i;
      const y = padding.top + (plotHeight / gridLines) * i;
      ctx.fillText(value.toFixed(2), 8, y);
    }

    visible.forEach((candle, idx) => {
      const xCenter = padding.left + (idx + 0.5) * candleWidth;
      const openY = priceToY(candle.open);
      const closeY = priceToY(candle.close);
      const highY = priceToY(candle.high);
      const lowY = priceToY(candle.low);
      const bullish = candle.close >= candle.open;
      const color = bullish ? "var(--chart-up)" : "var(--chart-down)";
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(xCenter, highY);
      ctx.lineTo(xCenter, lowY);
      ctx.stroke();

      const bodyTop = Math.min(openY, closeY);
      const bodyHeight = Math.max(Math.abs(closeY - openY), 1.2);
      const bodyWidth = Math.max(candleWidth * 0.6, 2);
      ctx.fillStyle = color;
      ctx.fillRect(xCenter - bodyWidth / 2, bodyTop, bodyWidth, bodyHeight);
    });

    if (Array.isArray(markers) && markers.length) {
      markers.forEach((marker) => {
        const markerTime = toTime(marker.timestamp);
        const index = data.findIndex((item) => item.ts === marker.timestamp);
        const resolvedIndex = index >= 0 ? index : findNearestIndex(times, markerTime);
        if (resolvedIndex < view.start || resolvedIndex >= view.end) {
          return;
        }
        const xCenter =
          padding.left + (resolvedIndex - view.start + 0.5) * candleWidthRef.current;
        const price = Number.isFinite(marker.price)
          ? marker.price
          : data[resolvedIndex]?.close;
        const yPos = price ? priceToY(price) : padding.top;
        const type = marker.marker_type || "event";
        const isEntry = type === "entry";
        const color = isEntry ? "var(--accent)" : "var(--accent-2)";

        ctx.fillStyle = color;
        ctx.beginPath();
        if (isEntry) {
          ctx.moveTo(xCenter, yPos - 8);
          ctx.lineTo(xCenter - 6, yPos + 6);
          ctx.lineTo(xCenter + 6, yPos + 6);
        } else {
          ctx.moveTo(xCenter, yPos + 8);
          ctx.lineTo(xCenter - 6, yPos - 6);
          ctx.lineTo(xCenter + 6, yPos - 6);
        }
        ctx.closePath();
        ctx.fill();
      });
    }
  }, [data, markers, size, view, height, times]);

  const handleWheel = (event) => {
    event.preventDefault();
    if (!data || data.length === 0) {
      return;
    }
    const direction = event.deltaY > 0 ? 1 : -1;
    const visibleCount = Math.max(view.end - view.start, 1);
    const nextCount = Math.round(visibleCount * (direction > 0 ? 1.12 : 0.88));
    const clampedCount = clamp(nextCount, 20, data.length);
    const center = (view.start + view.end) / 2;
    let start = Math.round(center - clampedCount / 2);
    start = clamp(start, 0, data.length - clampedCount);
    setView({ start, end: start + clampedCount });
  };

  const handlePointerDown = (event) => {
    if (!data || data.length === 0) {
      return;
    }
    dragRef.current = {
      startX: event.clientX,
      startView: view,
    };
  };

  const handlePointerMove = (event) => {
    if (!dragRef.current || !data || data.length === 0) {
      return;
    }
    const dx = event.clientX - dragRef.current.startX;
    const candleShift = Math.round(-dx / (candleWidthRef.current || 1));
    const visibleCount = Math.max(view.end - view.start, 1);
    let start = dragRef.current.startView.start + candleShift;
    start = clamp(start, 0, data.length - visibleCount);
    setView({ start, end: start + visibleCount });
  };

  const handlePointerUp = () => {
    dragRef.current = null;
  };

  if (!data || data.length === 0) {
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
      style={{ height }}
      onWheel={handleWheel}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerUp}
    >
      <canvas ref={canvasRef} />
    </div>
  );
}
