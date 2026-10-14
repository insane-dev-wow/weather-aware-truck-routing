import { ROUTE_COLORS, levelMeta } from "./risk.js";

export const EMPTY_ROUTES = [];

// Key-free MapLibre style (OSM data via OpenFreeMap).
// Do not use tile.openstreetmap.org (blocks hosted apps) or CartoCDN without a key.
export const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/positron";

export const RISK_COLOR = [
  "match",
  ["get", "score"],
  0,
  levelMeta("low").color,
  1,
  levelMeta("moderate").color,
  2,
  levelMeta("high").color,
  3,
  levelMeta("severe").color,
  4,
  levelMeta("no_travel").color,
  levelMeta("unknown").color,
];

export function routeCollection(routes, selectedId) {
  return {
    type: "FeatureCollection",
    features: routes.map((route, index) => ({
      type: "Feature",
      properties: {
        id: route.id,
        color: ROUTE_COLORS[index % ROUTE_COLORS.length],
        selected: route.id === selectedId,
      },
      geometry: {
        type: "LineString",
        coordinates: route.geometry.map(([lat, lon]) => [lon, lat]),
      },
    })),
  };
}

export function checkpointCollection(route, onlyIndex) {
  return {
    type: "FeatureCollection",
    features: (route?.checkpoints ?? [])
      .filter(
        (checkpoint) =>
          onlyIndex === undefined || checkpoint.index === onlyIndex,
      )
      .map((checkpoint) => ({
        type: "Feature",
        properties: {
          index: checkpoint.index,
          color: levelMeta(checkpoint.level).color,
        },
        geometry: {
          type: "Point",
          coordinates: [checkpoint.lon, checkpoint.lat],
        },
      })),
  };
}
