import assert from "assert";
import { parseViewState, serializeViewState } from "../lib/urlState.js";

const query = {
  symbol: "BTCUSDT, ,ETHUSDT",
  action: "placed",
  page: "2",
  page_size: "100",
  start_ts: "2026-02-04T12:34:56Z",
};

const parsed = parseViewState(query);
assert.strictEqual(parsed.symbol, "BTCUSDT,ETHUSDT");
assert.strictEqual(parsed.action, "placed");
assert.strictEqual(parsed.page, 2);
assert.strictEqual(parsed.page_size, 100);
assert.ok(parsed.start_ts.endsWith("Z"));

const serialized = serializeViewState(parsed);
assert.strictEqual(serialized.symbol, "BTCUSDT,ETHUSDT");
assert.strictEqual(serialized.page, "2");
assert.strictEqual(serialized.page_size, "100");
assert.ok(serialized.start_ts.endsWith("Z"));

console.log("URL state test OK");
