import { createContext, useCallback, useContext, useMemo, useState } from "react";

const MAX_TOASTS = 3;
const DEFAULT_TOAST_DURATION_MS = 3000;

const ToastContext = createContext(null);

let toastCounter = 1;

const nextToastId = () => {
  const id = toastCounter;
  toastCounter += 1;
  return id;
};

const normalizeToastKind = (kind) => {
  if (kind === "success" || kind === "error") {
    return kind;
  }
  return "info";
};

const normalizeDuration = (durationMs) => {
  if (Number.isFinite(durationMs) && durationMs > 0) {
    return durationMs;
  }
  return DEFAULT_TOAST_DURATION_MS;
};

function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const removeToast = useCallback((toastId) => {
    setToasts((current) => current.filter((toast) => toast.id !== toastId));
  }, []);

  const toast = useCallback(({ title, message, kind = "info", durationMs = null }) => {
    const next = {
      id: nextToastId(),
      kind: normalizeToastKind(kind),
      title: String(title || ""),
      message: String(message || ""),
      durationMs: normalizeDuration(durationMs),
    };
    setToasts((current) => [...current, next].slice(-MAX_TOASTS));
    return next.id;
  }, []);

  const contextValue = useMemo(
    () => ({
      toasts,
      toast,
      removeToast,
    }),
    [removeToast, toast, toasts]
  );

  return <ToastContext.Provider value={contextValue}>{children}</ToastContext.Provider>;
}

function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}

export { DEFAULT_TOAST_DURATION_MS, MAX_TOASTS, ToastProvider, useToast };
