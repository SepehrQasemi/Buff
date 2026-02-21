import { useEffect } from "react";
import { DEFAULT_TOAST_DURATION_MS, useToast } from "../lib/toast";

function ToastCard({ item, onClose }) {
  useEffect(() => {
    const timeoutMs =
      Number.isFinite(item.durationMs) && item.durationMs > 0
        ? item.durationMs
        : DEFAULT_TOAST_DURATION_MS;
    const timer = setTimeout(() => {
      onClose(item.id);
    }, timeoutMs);
    return () => clearTimeout(timer);
  }, [item.durationMs, item.id, onClose]);

  return (
    <div className={`toast-card toast-${item.kind}`}>
      <div className="toast-content">
        {item.title && <strong>{item.title}</strong>}
        {item.message && <p>{item.message}</p>}
      </div>
      <button
        type="button"
        className="toast-close"
        onClick={() => onClose(item.id)}
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </div>
  );
}

export default function ToastHost() {
  const { toasts, removeToast } = useToast();
  if (!toasts.length) {
    return null;
  }

  return (
    <div className="toast-host" aria-live="polite" aria-atomic="false">
      {toasts.map((item) => (
        <ToastCard key={item.id} item={item} onClose={removeToast} />
      ))}
    </div>
  );
}
