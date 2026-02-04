import assert from "assert";

const importApi = async ({ runtimeConfig, envBase } = {}) => {
  if (runtimeConfig !== undefined) {
    global.window = { __RUNTIME_CONFIG__: runtimeConfig };
  } else {
    delete global.window;
  }

  if (envBase === undefined) {
    delete process.env.NEXT_PUBLIC_API_BASE;
  } else {
    process.env.NEXT_PUBLIC_API_BASE = envBase;
  }

  return import(`../lib/api.js?cache=${Date.now()}-${Math.random()}`);
};

const testUrlJoin = async () => {
  const { buildApiUrl } = await importApi({ envBase: "http://localhost:8000" });
  assert.strictEqual(buildApiUrl("/runs"), "http://localhost:8000/api/v1/runs");
};

const testUrlJoinTrailingSlash = async () => {
  const { buildApiUrl } = await importApi({ envBase: "http://localhost:8000/" });
  assert.strictEqual(buildApiUrl("runs"), "http://localhost:8000/api/v1/runs");
};

const testNoDoubleVersion = async () => {
  const { buildApiUrl } = await importApi({ envBase: "http://localhost:8000/api/v1" });
  const url = buildApiUrl("/runs");
  assert.strictEqual(url, "http://localhost:8000/api/v1/runs");
  assert.ok(!url.includes("/api/v1/api/v1"));
};

const testVersionWithTrailingSlash = async () => {
  const { buildApiUrl } = await importApi({ envBase: "http://localhost:8000/api/v1/" });
  assert.strictEqual(buildApiUrl("/runs"), "http://localhost:8000/api/v1/runs");
};

const testExportUrl = async () => {
  const { buildApiUrl } = await importApi({ envBase: "http://localhost:8000" });
  const url = buildApiUrl("/runs/run-1/decisions/export", { format: "csv" });
  assert.strictEqual(
    url,
    "http://localhost:8000/api/v1/runs/run-1/decisions/export?format=csv"
  );
};

const testRuntimeConfigPriority = async () => {
  const { buildApiUrl } = await importApi({
    runtimeConfig: { API_BASE: "http://runtime.local:9000" },
    envBase: "http://env.local:8000",
  });
  assert.strictEqual(buildApiUrl("/runs"), "http://runtime.local:9000/api/v1/runs");
};

const testEnvBaseFallback = async () => {
  const { buildApiUrl } = await importApi({ envBase: "http://env.local:8000" });
  assert.strictEqual(buildApiUrl("/runs"), "http://env.local:8000/api/v1/runs");
};

const testDefaultFallback = async () => {
  const { buildApiUrl } = await importApi();
  assert.strictEqual(buildApiUrl("/runs"), "http://127.0.0.1:8000/api/v1/runs");
};

await testUrlJoin();
await testUrlJoinTrailingSlash();
await testNoDoubleVersion();
await testVersionWithTrailingSlash();
await testExportUrl();
await testRuntimeConfigPriority();
await testEnvBaseFallback();
await testDefaultFallback();

console.log("URL join test OK");
