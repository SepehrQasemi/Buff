const baseUrl = process.env.NEXT_PUBLIC_API_BASE || process.env.API_BASE || "http://127.0.0.1:8000";

const requestJson = async (path) => {
  const response = await fetch(`${baseUrl}${path}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${path} failed (${response.status}): ${text}`);
  }
  return response.json();
};

const run = async () => {
  try {
    await requestJson("/api/health");
    const runs = await requestJson("/api/runs");
    if (!Array.isArray(runs) || runs.length === 0) {
      throw new Error("No runs returned from /api/runs");
    }
    const runId = runs[0].id;
    if (!runId) {
      throw new Error("First run is missing id");
    }
    await requestJson(`/api/runs/${runId}/summary`);
    console.log("Smoke OK", { runId });
  } catch (error) {
    console.error("Smoke FAILED", error.message || error);
    process.exit(1);
  }
};

run();
