import test from "node:test";
import assert from "node:assert/strict";
import {
  forecastCollection,
  forecastAtPoint,
  forecastMarks,
  forecastTiles,
  riskScore,
} from "./mapData.js";

test("area risk follows the selected hour and does not borrow distant or missing forecasts", () => {
  const tiles = forecastTiles([{ lat: 39, lon: -95, scores: [0, 3, null] }], 0.4);
  const point = { lat: 39.05, lon: -95.05 };
  assert.equal(forecastAtPoint(tiles, point, 0), 0);
  assert.equal(forecastAtPoint(tiles, point, 1), 3);
  assert.equal(forecastAtPoint(tiles, point, 2), null);
  assert.equal(forecastAtPoint(tiles, { lat: 40, lon: -95 }, 1), null);
  assert.equal(forecastAtPoint(tiles, point, 49), null);
});

test("risk classes retain their value and missing forecasts stay distinct from low risk", () => {
  for (let score = 0; score <= 4; score += 1)
    assert.equal(riskScore(score), score);
  for (const value of [null, undefined, NaN, "0", -1, 5, 2.5])
    assert.equal(riskScore(value), -1);
});

test("neighboring forecast cells share edges without accumulating risk", () => {
  const tiles = forecastTiles(
    [
      { lat: 40, lon: -100, scores: [1, 4] },
      { lat: 40, lon: -99.5, scores: [1, null] },
    ],
    0.5,
  );
  const early = forecastCollection(tiles, 0);
  const later = forecastCollection(tiles, 1);
  assert.equal(
    early.features[0].geometry.coordinates[0][1][0],
    early.features[1].geometry.coordinates[0][0][0],
  );
  assert.deepEqual(
    early.features.map((feature) => feature.properties.score),
    [1, 1],
  );
  assert.deepEqual(
    later.features.map((feature) => feature.properties.score),
    [4, -1],
  );
  assert.deepEqual(early.features[0].geometry, later.features[0].geometry);
  assert.equal("sample" in later.features[0], false);
});

test("grid geometry can infer provider spacing when metadata is absent", () => {
  const tiles = forecastTiles([
    { lat: 40, lon: -100 },
    { lat: 40.25, lon: -99.75 },
  ]);
  assert.deepEqual(tiles[0].geometry.coordinates[0][0], [-100.125, 39.875]);
  assert.deepEqual(
    forecastCollection(tiles, 99).features.map(
      (feature) => feature.properties.score,
    ),
    [-1, -1],
  );
});

test("forecast axis labels its actual endpoint, including hour 48", () => {
  assert.equal(forecastMarks(Array(49)).at(-1).label, "+48h");
  assert.equal(forecastMarks(Array(48)).at(-1).label, "+47h");
  assert.deepEqual(forecastMarks(Array(7)), [
    { value: 0, label: "Departure" },
    { value: 6, label: "+6h" },
  ]);
});
