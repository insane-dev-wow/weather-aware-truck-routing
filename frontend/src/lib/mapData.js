export const EMPTY_COLLECTION = { type: "FeatureCollection", features: [] };

export function riskScore(value) {
  return typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 0 &&
    value <= 4
    ? value
    : -1;
}

function inferredStep(cells) {
  const gaps = ["lat", "lon"].flatMap((axis) => {
    const values = [...new Set(cells.map((cell) => cell[axis]))].sort(
      (a, b) => a - b,
    );
    return values
      .slice(1)
      .map((value, index) => value - values[index])
      .filter((gap) => gap > 0.001);
  });
  return gaps.length ? Math.round(Math.min(...gaps) * 1000) / 1000 : 0.1;
}

export function forecastTiles(cells = [], cellSizeDegrees) {
  const validCells = cells.filter(
    (cell) => Number.isFinite(cell.lat) && Number.isFinite(cell.lon),
  );
  const step =
    Number.isFinite(cellSizeDegrees) && cellSizeDegrees > 0
      ? cellSizeDegrees
      : inferredStep(validCells);
  const half = step / 2;
  return validCells.map((cell, index) => ({
    type: "Feature",
    id: index,
    properties: { index },
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [cell.lon - half, Math.max(-90, cell.lat - half)],
          [cell.lon + half, Math.max(-90, cell.lat - half)],
          [cell.lon + half, Math.min(90, cell.lat + half)],
          [cell.lon - half, Math.min(90, cell.lat + half)],
          [cell.lon - half, Math.max(-90, cell.lat - half)],
        ],
      ],
    },
    sample: cell,
  }));
}

export function forecastCollection(tiles, frame) {
  return {
    type: "FeatureCollection",
    features: tiles.map(({ sample, ...feature }) => ({
      ...feature,
      properties: {
        ...feature.properties,
        score: riskScore(sample.scores?.[frame]),
      },
    })),
  };
}

export function forecastAtPoint(tiles, point, frame) {
  const tile = tiles.find(({ geometry }) => {
    const [sw, , ne] = geometry.coordinates[0];
    return point.lon >= sw[0] && point.lon < ne[0] &&
      point.lat >= sw[1] && point.lat < ne[1];
  });
  const score = riskScore(tile?.sample.scores?.[frame]);
  return score < 0 ? null : score;
}

export function forecastMarks(hours = []) {
  const last = Math.max(0, hours.length - 1);
  const indexes = [
    ...new Set([0, 12, 24, 36, last].filter((index) => index <= last)),
  ];
  return indexes.map((value) => ({
    value,
    label: value === 0 ? "Departure" : `+${value}h`,
  }));
}
