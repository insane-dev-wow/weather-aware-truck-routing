import test from "node:test";
import assert from "node:assert/strict";
import { resolveTripPlaces } from "./defaultPlaces.js";

const preset = ["Example", "Denver, Colorado", "Kansas City, Missouri"];

test("repeat visits reuse real autocomplete results without network requests", async () => {
  const entries = new Map();
  const storage = { getItem: (key) => entries.get(key), setItem: (key, value) => entries.set(key, value) };
  let calls = 0;
  const lookup = async (query) => {
    calls++;
    return { results: [{ value: `${query}, United States` }] };
  };
  const first = await resolveTripPlaces(preset, lookup, undefined, storage);
  assert.deepEqual(await resolveTripPlaces(preset, lookup, undefined, storage), first);
  assert.equal(calls, 2);
  const [key, value] = [...entries][0];
  storage.setItem(key, JSON.stringify({ ...JSON.parse(value), savedAt: 0 }));
  await resolveTripPlaces(preset, lookup, undefined, storage);
  assert.equal(calls, 4);
});

test("unavailable browser storage does not block autocomplete", async () => {
  const storage = { getItem() { throw new Error("Denied"); }, setItem() { throw new Error("Denied"); } };
  const result = await resolveTripPlaces(preset, async (query) => ({ results: [{ value: `${query}, United States` }] }), undefined, storage);
  assert.equal(result.origin, "Denver, Colorado, United States");
});

test("defaults use actual autocomplete values and match the correct state", async () => {
  const lookup = async (query) => ({ results: query.startsWith("Denver")
    ? [{ value: "Denver, Iowa, United States" }, { value: "Denver, Colorado, United States" }]
    : [{ value: "Kansas City, Kansas, United States" }, { value: "Kansas City, Missouri, United States" }],
  });
  assert.deepEqual(await resolveTripPlaces(preset, lookup), {
    origin: "Denver, Colorado, United States",
    destination: "Kansas City, Missouri, United States",
  });
});

test("missing defaults never fall back to invented input values", async () => {
  await assert.rejects(resolveTripPlaces(preset, async () => ({ results: [] })), /Could not load/);
});

test("default lookup forwards cancellation to both autocomplete requests", async () => {
  const controller = new AbortController();
  const signals = [];
  const lookup = async (query, signal) => {
    signals.push(signal);
    return { results: [{ value: `${query}, United States` }] };
  };
  await resolveTripPlaces(preset, lookup, controller.signal);
  assert.deepEqual(signals, [controller.signal, controller.signal]);
});
