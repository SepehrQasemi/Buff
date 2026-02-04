import fs from "fs";
import path from "path";

const DEFAULT_API_BASE = "http://127.0.0.1:8000/api/v1";

const rawValue = process.env.NEXT_PUBLIC_API_BASE || DEFAULT_API_BASE;
const candidate = String(rawValue).trim();

const hasControlChars = /[\u0000-\u001F\u007F]/.test(candidate);
const hasProtocol = /^https?:\/\//.test(candidate);

let apiBase = candidate;
if (!hasProtocol || hasControlChars) {
  console.warn(
    `[runtime-config] Invalid NEXT_PUBLIC_API_BASE "${rawValue}". Falling back to ${DEFAULT_API_BASE}.`
  );
  apiBase = DEFAULT_API_BASE;
}

const payload = { API_BASE: apiBase };
const content = `window.__RUNTIME_CONFIG__ = ${JSON.stringify(
  payload
)};\nwindow.__BUFF_API_BASE__ = ${JSON.stringify(apiBase)};\n`;

const outputPath = path.join(process.cwd(), "public", "runtime-config.js");
fs.writeFileSync(outputPath, content, "utf8");
