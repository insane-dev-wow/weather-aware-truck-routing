import test from "node:test";
import assert from "node:assert/strict";
import { schedulePlaceSearch } from "./placeSearch.js";

test("typing waits 200 ms and sends only the latest query", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const calls = [];
  const results = [];
  const lookup = async (query) => { calls.push(query); return query; };
  const cancel = schedulePlaceSearch("Den", lookup, (r) => results.push(r), assert.fail, () => {});
  t.mock.timers.tick(100);
  cancel();
  schedulePlaceSearch("Denver", lookup, (r) => results.push(r), assert.fail, () => {});
  t.mock.timers.tick(199);
  assert.deepEqual(calls, []);
  t.mock.timers.tick(1);
  await Promise.resolve();
  assert.deepEqual(calls, ["Denver"]);
  assert.deepEqual(results, ["Denver"]);
});

test("repeated searches reuse exact-query suggestions immediately", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let calls = 0;
  const lookup = async () => { calls++; return { results: ["Denver"] }; };
  schedulePlaceSearch("Denver", lookup, () => {}, assert.fail, () => {});
  t.mock.timers.tick(200);
  await Promise.resolve();
  let result;
  let settled = false;
  schedulePlaceSearch(" denver ", lookup, (data) => { result = data; }, assert.fail, () => { settled = true; });
  assert.equal(calls, 1);
  assert.deepEqual(result, { results: ["Denver"] });
  assert.equal(settled, true);
});

test("late responses cannot replace suggestions after typing or closing", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let resolve;
  let signal;
  const cancel = schedulePlaceSearch("Denver", (_query, s) => {
    signal = s;
    return new Promise((r) => { resolve = r; });
  }, assert.fail, assert.fail, assert.fail);
  t.mock.timers.tick(400);
  cancel();
  assert.equal(signal.aborted, true);
  resolve({ results: ["stale"] });
  await Promise.resolve();
});

test("closing before debounce fires prevents a request", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const cancel = schedulePlaceSearch("Denver", assert.fail, assert.fail, assert.fail, assert.fail);
  cancel();
  t.mock.timers.tick(1000);
});

test("provider errors stop loading and expose the error", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const expected = new Error("Unavailable");
  let error;
  let settled = false;
  schedulePlaceSearch("Denver", async () => { throw expected; }, assert.fail,
    (e) => { error = e; }, () => { settled = true; });
  t.mock.timers.tick(400);
  await Promise.resolve();
  assert.equal(error, expected);
  assert.equal(settled, true);
});
