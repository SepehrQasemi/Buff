import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const WEB_ROOT = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..", "..");

const UI_BASE = process.env.UI_BASE || "http://localhost:3000";
const API_BASE = process.env.API_BASE || "http://localhost:8000/api/v1";
const RUN_TIMEOUT_MS = Number.parseInt(process.env.JOURNEY_RUN_TIMEOUT_MS || "180000", 10);
const FIXTURE_PATH =
  process.env.JOURNEY_CSV_PATH || path.join(REPO_ROOT, "tests", "fixtures", "phase6", "cross.csv");

const FATAL_BANNERS = ["RUNS_ROOT is not ready", "RUNS_ROOT is not writable"];
const TERMINAL_STATES = new Set(["COMPLETED", "FAILED", "CORRUPTED", "OK"]);
const MAX_FAILURE_BODY = 500;
const INFRA_ERROR_CODES = new Set([
  "RUNS_ROOT_UNSET",
  "RUNS_ROOT_MISSING",
  "RUNS_ROOT_INVALID",
  "RUNS_ROOT_NOT_WRITABLE",
  "REGISTRY_LOCK_TIMEOUT",
]);

const nowIso = () => new Date().toISOString();
const timestampToken = () => nowIso().replace(/[-:.]/g, "").replace(/\.\d{3}Z$/, "Z");
const toStepId = (index) => `step-${String(index).padStart(2, "0")}`;
const toRelative = (value) => path.relative(WEB_ROOT, value).replace(/\\/g, "/");

const buildArtifactsDir = () =>
  path.join(WEB_ROOT, "test-artifacts", "journey", process.env.JOURNEY_TIMESTAMP || timestampToken());

const asTextSnippet = (value, max = MAX_FAILURE_BODY) =>
  String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);

const normalizeError = (error) => {
  if (!error) {
    return "Unknown error";
  }
  if (typeof error === "string") {
    return error;
  }
  if (error.stack) {
    return String(error.stack);
  }
  if (error.message) {
    return String(error.message);
  }
  return String(error);
};

const lineify = (item) => {
  const base = `${item.timestamp} [${item.type}] ${item.text}`;
  if (item.url) {
    return `${base} (${item.url}:${item.line || 0}:${item.column || 0})`;
  }
  return base;
};

const readLiveState = async (page) => {
  const badge = page.locator('section:has(h3:has-text("Live Status")) .badge').first();
  if ((await badge.count()) === 0) {
    return "";
  }
  const text = await badge.innerText({ timeout: 3000 }).catch(() => "");
  return String(text || "").trim().toUpperCase();
};

const waitForTerminalState = async (page, timeoutMs, report) => {
  const started = Date.now();
  let previous = "";
  while (Date.now() - started < timeoutMs) {
    const state = await readLiveState(page);
    if (state && state !== previous) {
      previous = state;
      report.run_state_transitions.push({ timestamp: nowIso(), state });
    }
    if (TERMINAL_STATES.has(state)) {
      return state;
    }
    await page.waitForTimeout(2000);
  }
  throw new Error(`Run status did not reach a terminal state within ${timeoutMs}ms.`);
};

const assertNoFatalBanner = async (page, stepName) => {
  for (const text of FATAL_BANNERS) {
    const locator = page.getByText(text, { exact: false });
    const count = await locator.count();
    for (let idx = 0; idx < count; idx += 1) {
      const visible = await locator.nth(idx).isVisible().catch(() => false);
      if (visible) {
        throw new Error(`${stepName}: found fatal banner "${text}".`);
      }
    }
  }
};

const parseBarsCount = async (page) => {
  const locator = page.locator(".chart-status strong").nth(1);
  if ((await locator.count()) === 0) {
    return null;
  }
  const text = await locator.innerText({ timeout: 3000 }).catch(() => "");
  const match = String(text || "").match(/-?\d+/);
  if (!match) {
    return null;
  }
  return Number.parseInt(match[0], 10);
};

const assertChartNotSilentBlank = async (page) => {
  await page.locator("section.chart-panel").first().waitFor({ state: "visible", timeout: 30000 });
  const canvasVisible = await page.locator(".chart-frame canvas").first().isVisible().catch(() => false);
  const emptyMessageVisible = await page
    .getByText("No OHLCV candles available for this range.", { exact: false })
    .first()
    .isVisible()
    .catch(() => false);
  const loadingMessageVisible = await page
    .getByText("Loading OHLCV artifacts...", { exact: false })
    .first()
    .isVisible()
    .catch(() => false);
  const ohlcvUnavailableVisible = await page
    .getByText("OHLCV timeframe unavailable", { exact: false })
    .first()
    .isVisible()
    .catch(() => false);

  const barsCount = await parseBarsCount(page);
  const hasRenderableChart = canvasVisible && (barsCount === null || barsCount > 0);
  const hasExplanatoryMessage =
    emptyMessageVisible || loadingMessageVisible || ohlcvUnavailableVisible;
  if (!hasRenderableChart && !hasExplanatoryMessage) {
    throw new Error("Chart appears blank with no explanatory message.");
  }
};

const assertRiskWarningConsistency = async (page) => {
  const warning = page.getByText("Risk artifacts missing or incomplete", { exact: false }).first();
  if ((await warning.count()) === 0) {
    return;
  }
  const visible = await warning.isVisible().catch(() => false);
  if (!visible) {
    return;
  }
  const warningText = (await warning.innerText().catch(() => "")).toUpperCase();
  const statusMatch = warningText.match(/STATUS:\s*([A-Z0-9_/-]+)/);
  const status = statusMatch ? statusMatch[1] : "";
  if (!status || status === "OK" || status === "UNKNOWN" || status === "N/A" || status === "NA") {
    throw new Error(`Risk warning is visible without explicit failed status. status=${status || "missing"}`);
  }
};

const waitForRunInRunsList = async (page, runId, timeoutMs = 60000) => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const locator = page.locator("h3", { hasText: runId }).first();
    const visible = (await locator.count()) > 0 && (await locator.isVisible().catch(() => false));
    if (visible) {
      return;
    }
    const refresh = page.getByRole("button", { name: "Refresh" }).first();
    if ((await refresh.count()) > 0) {
      await refresh.click().catch(() => {});
    } else {
      await page.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
    }
    await page.waitForTimeout(2000);
  }
  throw new Error(`Run ${runId} did not appear in the runs list within timeout.`);
};

const safeBodySnippet = async (response) => {
  const contentType = (response.headers()["content-type"] || "").toLowerCase();
  const isTextLike =
    contentType.includes("json") ||
    contentType.includes("text") ||
    contentType.includes("xml") ||
    contentType.includes("html") ||
    contentType.includes("javascript");
  if (!isTextLike) {
    return "";
  }
  try {
    return asTextSnippet(await response.text(), MAX_FAILURE_BODY);
  } catch {
    return "";
  }
};

const ensureDir = async (target) => {
  await fsp.mkdir(target, { recursive: true });
};

const readJsonFile = async (filePath, fallback) => {
  try {
    const payload = await fsp.readFile(filePath, "utf8");
    return JSON.parse(payload);
  } catch {
    return fallback;
  }
};

const extractErrorCode = (entry) => {
  if (!entry || typeof entry !== "object") {
    return null;
  }
  const bodySnippet = String(entry.body_snippet || "");
  if (!bodySnippet) {
    return null;
  }
  try {
    const parsed = JSON.parse(bodySnippet);
    const envelopeCode = parsed?.error_envelope?.error_code;
    if (typeof envelopeCode === "string" && envelopeCode.trim()) {
      return envelopeCode.trim();
    }
    const code = parsed?.code;
    if (typeof code === "string" && code.trim()) {
      return code.trim();
    }
  } catch {
    const envelopeMatch = bodySnippet.match(/"error_code"\s*:\s*"([^"]+)"/i);
    if (envelopeMatch?.[1]) {
      return envelopeMatch[1].trim();
    }
    const codeMatch = bodySnippet.match(/"code"\s*:\s*"([^"]+)"/i);
    if (codeMatch?.[1]) {
      return codeMatch[1].trim();
    }
  }
  return null;
};

const evaluateJourneyGate = async (artifactsDir) => {
  const reportPath = path.join(artifactsDir, "report.json");
  const failuresPath = path.join(artifactsDir, "network-failures.json");

  const report = await readJsonFile(reportPath, {});
  const failedRequests = await readJsonFile(failuresPath, []);
  const failures = Array.isArray(failedRequests) ? failedRequests : [];

  const consoleErrorCount = Number(report.console_error_count || 0);
  const failedRequestCount = Number(report.failed_request_count || 0);

  const allCodes = new Set();
  const infraCodes = new Set();
  for (const entry of failures) {
    const code = extractErrorCode(entry);
    if (!code) {
      continue;
    }
    allCodes.add(code);
    if (INFRA_ERROR_CODES.has(code)) {
      infraCodes.add(code);
    }
  }

  const shouldFail =
    consoleErrorCount > 0 || failedRequestCount > 0 || infraCodes.size > 0;

  const failingEndpoints = failures.slice(0, 5).map((entry) => ({
    method: entry?.method || "UNKNOWN",
    url: entry?.url || "",
    status: entry?.status ?? "requestfailed",
  }));

  return {
    shouldFail,
    consoleErrorCount,
    failedRequestCount,
    allErrorCodes: Array.from(allCodes).sort(),
    infraErrorCodes: Array.from(infraCodes).sort(),
    failingEndpoints,
  };
};

const writeReportArtifacts = async (artifactsDir, report) => {
  await ensureDir(artifactsDir);
  const reportPath = path.join(artifactsDir, "report.json");
  const consolePath = path.join(artifactsDir, "console.log");
  const pageErrorsPath = path.join(artifactsDir, "page-errors.log");
  const failedRequestsPath = path.join(artifactsDir, "network-failures.json");

  await fsp.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await fsp.writeFile(consolePath, `${report.console_messages.map(lineify).join("\n")}\n`, "utf8");
  await fsp.writeFile(pageErrorsPath, `${report.page_errors.map(lineify).join("\n")}\n`, "utf8");
  await fsp.writeFile(failedRequestsPath, `${JSON.stringify(report.failed_requests, null, 2)}\n`, "utf8");
};

const summaryLine = (label, value) => `${label}: ${value}`;

const main = async () => {
  const artifactsDir = buildArtifactsDir();
  const report = {
    started_at: nowIso(),
    completed_at: null,
    pass: false,
    failing_step: null,
    error: null,
    ui_base: UI_BASE,
    api_base: API_BASE,
    fixture_csv: FIXTURE_PATH,
    artifacts_dir: artifactsDir,
    run_id: null,
    final_state: null,
    run_state_transitions: [],
    steps: [],
    console_messages: [],
    page_errors: [],
    failed_requests: [],
    downloads: [],
  };

  let browser;
  let context;
  let page;

  try {
    if (!fs.existsSync(FIXTURE_PATH)) {
      throw new Error(`CSV fixture not found: ${FIXTURE_PATH}`);
    }

    await ensureDir(artifactsDir);

    browser = await chromium.launch({
      headless: process.env.JOURNEY_HEADLESS !== "0",
    });
    context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      acceptDownloads: true,
    });
    context.setDefaultTimeout(45000);
    page = await context.newPage();

    page.on("console", (message) => {
      const location = message.location() || {};
      report.console_messages.push({
        timestamp: nowIso(),
        type: message.type(),
        text: message.text(),
        url: location.url || "",
        line: location.lineNumber || 0,
        column: location.columnNumber || 0,
      });
    });

    page.on("pageerror", (error) => {
      report.page_errors.push({
        timestamp: nowIso(),
        type: "pageerror",
        text: normalizeError(error),
        url: page.url(),
        line: 0,
        column: 0,
      });
    });

    page.on("requestfailed", (request) => {
      const failure = request.failure()?.errorText || "request failed";
      if (failure === "net::ERR_ABORTED") {
        return;
      }
      report.failed_requests.push({
        timestamp: nowIso(),
        source: "requestfailed",
        method: request.method(),
        url: request.url(),
        status: null,
        body_snippet: "",
        failure,
      });
    });

    page.on("response", async (response) => {
      if (response.status() < 400) {
        return;
      }
      report.failed_requests.push({
        timestamp: nowIso(),
        source: "response",
        method: response.request().method(),
        url: response.url(),
        status: response.status(),
        body_snippet: await safeBodySnippet(response),
      });
    });

    let stepIndex = 0;
    const runStep = async (name, action) => {
      stepIndex += 1;
      const stepId = toStepId(stepIndex);
      const screenshotPath = path.join(artifactsDir, `${stepId}.png`);
      const step = {
        id: stepId,
        name,
        started_at: nowIso(),
        ended_at: null,
        status: "PASS",
        url: "",
        screenshot: toRelative(screenshotPath),
        error: null,
      };

      try {
        await action();
        await assertNoFatalBanner(page, name);
      } catch (error) {
        step.status = "FAIL";
        step.error = normalizeError(error);
        if (!report.failing_step) {
          report.failing_step = name;
        }
        throw error;
      } finally {
        step.url = page.url();
        await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
        step.ended_at = nowIso();
        report.steps.push(step);
      }
    };

    await runStep("Step A: Home (/)", async () => {
      await page.goto(new URL("/", `${UI_BASE}/`).toString(), { waitUntil: "domcontentloaded" });
      await page.getByRole("heading", { name: "Buff Local UI" }).waitFor({ state: "visible" });
    });

    await runStep("Step B: Runs list (/runs)", async () => {
      await page.goto(new URL("/runs", `${UI_BASE}/`).toString(), { waitUntil: "domcontentloaded" });
      await page.getByRole("heading", { name: "Run Explorer" }).waitFor({ state: "visible" });
    });

    await runStep("Step C: New run wizard (/runs/new)", async () => {
      await page.goto(new URL("/runs/new", `${UI_BASE}/`).toString(), {
        waitUntil: "domcontentloaded",
      });
      await page.locator('[data-testid="create-run-step-import"]').waitFor({ state: "visible" });
    });

    await runStep("Step D: Upload sample CSV", async () => {
      const importStep = page.locator('[data-testid="create-run-step-import"]').first();
      const input = importStep.locator('input[type="file"]').first();
      if ((await input.count()) === 0) {
        throw new Error("CSV input control not found.");
      }
      await input.setInputFiles(FIXTURE_PATH);
      await importStep.getByRole("button", { name: "Import Data" }).click();
      await page.locator('[data-testid="create-run-step-strategy"]').waitFor({
        state: "visible",
        timeout: 60000,
      });
    });

    await runStep("Step E: Choose strategy", async () => {
      const strategyButtons = page.locator(
        '[data-testid="create-run-step-strategy"] button.selector-card'
      );
      const count = await strategyButtons.count();
      if (count < 1) {
        throw new Error("No strategy options available in step 2.");
      }
      await strategyButtons.first().click();
      await page.getByRole("button", { name: "Continue to Configure" }).click();
      await page.locator('[data-testid="create-run-step-configure"]').waitFor({
        state: "visible",
        timeout: 20000,
      });
    });

    await runStep("Step F: Start run", async () => {
      await page.getByRole("button", { name: "Continue to Run" }).click();
      await page.locator('[data-testid="create-run-step-run"]').waitFor({
        state: "visible",
        timeout: 20000,
      });
      await page.getByRole("button", { name: /Create Run/i }).click();
      await page.waitForURL(
        (url) => url.pathname.startsWith("/runs/") && url.pathname !== "/runs/new",
        { timeout: 60000 }
      );
      const url = new URL(page.url());
      const runId = url.pathname.split("/").filter(Boolean).pop();
      if (!runId || runId === "new") {
        throw new Error(`Invalid run id from URL: ${page.url()}`);
      }
      report.run_id = runId;
    });

    await runStep("Step G: Run detail status + chart/risk checks", async () => {
      await page.locator('[data-testid="chart-workspace"]').waitFor({
        state: "visible",
        timeout: 30000,
      });
      report.final_state = await waitForTerminalState(page, RUN_TIMEOUT_MS, report);
      await assertChartNotSilentBlank(page);
      await assertRiskWarningConsistency(page);
    });

    await runStep("Step H: Export report", async () => {
      if (!report.run_id) {
        throw new Error("Run id missing before export.");
      }
      const runId = report.run_id;
      const exportResponsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === "GET" &&
          response.url().includes(`${API_BASE.replace(/\/+$/, "")}/runs/${runId}/report/export`),
        { timeout: 60000 }
      );
      const downloadPromise = page.waitForEvent("download", { timeout: 60000 });
      await page.getByRole("button", { name: /Export Report/i }).click();
      const [exportResponse, download] = await Promise.all([exportResponsePromise, downloadPromise]);
      if (exportResponse.status() !== 200) {
        throw new Error(`Report export returned HTTP ${exportResponse.status()}.`);
      }
      const suggestedFilename = download.suggestedFilename() || `${runId}-report.zip`;
      const savePath = path.join(artifactsDir, suggestedFilename);
      await download.saveAs(savePath);
      report.downloads.push({
        timestamp: nowIso(),
        url: exportResponse.url(),
        status: exportResponse.status(),
        file: toRelative(savePath),
      });
    });

    await runStep("Step I: Runs list contains created run", async () => {
      if (!report.run_id) {
        throw new Error("Run id missing before runs-list verification.");
      }
      await page.goto(new URL("/runs", `${UI_BASE}/`).toString(), { waitUntil: "domcontentloaded" });
      await page.getByRole("heading", { name: "Run Explorer" }).waitFor({ state: "visible" });
      await waitForRunInRunsList(page, report.run_id, 60000);
    });

    report.pass = true;
  } catch (error) {
    report.pass = false;
    report.error = normalizeError(error);
  } finally {
    report.completed_at = nowIso();
    report.console_error_count = report.console_messages.filter(
      (entry) => entry.type === "error"
    ).length;
    report.page_error_count = report.page_errors.length;
    report.failed_request_count = report.failed_requests.length;
    await writeReportArtifacts(artifactsDir, report);
    const gateResult = await evaluateJourneyGate(artifactsDir);
    if (gateResult.shouldFail) {
      report.pass = false;
      if (!report.failing_step) {
        report.failing_step = "Journey gate validation";
      }
      report.error = [
        `journey gate failed: console_error_count=${gateResult.consoleErrorCount}`,
        `failed_request_count=${gateResult.failedRequestCount}`,
        `error_codes=${gateResult.allErrorCodes.join(",") || "none"}`,
      ].join("; ");
      await writeReportArtifacts(artifactsDir, report);
      console.log(summaryLine("journey_gate", "FAIL"));
      console.log(
        summaryLine(
          "journey_gate_counts",
          `console_error_count=${gateResult.consoleErrorCount}, failed_request_count=${gateResult.failedRequestCount}`
        )
      );
      console.log(
        summaryLine(
          "journey_gate_error_codes",
          gateResult.allErrorCodes.join(",") || "none"
        )
      );
      console.log(
        summaryLine(
          "journey_gate_infra_error_codes",
          gateResult.infraErrorCodes.join(",") || "none"
        )
      );
      for (const endpoint of gateResult.failingEndpoints) {
        console.log(
          summaryLine(
            "journey_gate_endpoint",
            `${endpoint.method} ${endpoint.url} ${endpoint.status}`
          )
        );
      }
    }
    if (context) {
      await context.close().catch(() => {});
    }
    if (browser) {
      await browser.close().catch(() => {});
    }

    const status = report.pass ? "PASS" : "FAIL";
    const failingStep = report.failing_step || "none";
    console.log(summaryLine("journey", status));
    console.log(summaryLine("failing_step", failingStep));
    console.log(summaryLine("console_error_count", report.console_error_count));
    console.log(summaryLine("failed_request_count", report.failed_request_count));
    console.log(summaryLine("artifacts", artifactsDir));
    if (!report.pass) {
      if (report.error) {
        console.log(summaryLine("error", asTextSnippet(report.error, 1000)));
      }
      process.exitCode = 1;
    }
  }
};

await main();
