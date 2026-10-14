import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AttributionControl,
  LngLatBounds,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  ScaleControl,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "../lib/maplibreWorker.js";

import { formatDayClock, formatHours } from "../lib/format.js";
import {
  EMPTY_COLLECTION,
  forecastCollection,
  forecastTiles,
} from "../lib/mapData.js";
import {
  BASEMAP_STYLE,
  EMPTY_ROUTES,
  RISK_COLOR,
  checkpointCollection,
  routeCollection,
} from "../lib/mapGeoJson.js";
import { popupContent } from "../lib/mapPopup.js";
import { ROUTE_COLORS, levelMeta } from "../lib/risk.js";

function motionDuration(duration) {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? 0
    : duration;
}

export default function TripMap({
  plan,
  selectedRouteId,
  onSelectRoute,
  frame = 0,
  showCells = false,
  focusTarget,
  selectedCheckpointIndex,
  onSelectCheckpoint,
  heatmapVisible = true,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const selectRef = useRef(onSelectRoute);
  const checkpointRef = useRef(onSelectCheckpoint);
  const routeRef = useRef(null);
  const forecastRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [mapError, setMapError] = useState("");
  selectRef.current = onSelectRoute;
  checkpointRef.current = onSelectCheckpoint;
  const routes = plan?.routes ?? EMPTY_ROUTES;
  const route = routes.find((item) => item.id === selectedRouteId) ?? routes[0];
  routeRef.current = route;
  const tiles = useMemo(
    () => forecastTiles(plan?.heatmap?.cells, plan?.heatmap?.cell_size_degrees),
    [plan?.heatmap],
  );
  forecastRef.current = {
    tiles,
    frame,
    time: plan?.heatmap?.hours?.[frame],
    visible: heatmapVisible,
  };

  const fitRoutes = useCallback((items) => {
    const coords = items.flatMap((item) => item.geometry ?? []);
    if (!mapRef.current || !coords.length) return;
    const bounds = coords.reduce(
      (acc, [lat, lon]) => acc.extend([lon, lat]),
      new LngLatBounds(),
    );
    const narrow = containerRef.current?.clientWidth < 600;
    mapRef.current.fitBounds(bounds, {
      padding: {
        top: 88,
        bottom: 80,
        left: narrow ? 38 : 80,
        right: narrow ? 38 : 80,
      },
      maxZoom: 10,
      duration: motionDuration(650),
    });
  }, []);

  useEffect(() => {
    let map;
    try {
      map = new MapLibreMap({
        container: containerRef.current,
        style: BASEMAP_STYLE,
        center: [-98.6, 38.7],
        zoom: 3.6,
        attributionControl: false,
        dragRotate: false,
        failIfMajorPerformanceCaveat: false,
      });
    } catch {
      setMapError(
        "This browser could not start the map. Route details are available in the list below.",
      );
      return undefined;
    }
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    map.addControl(
      new NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    map.addControl(
      new ScaleControl({ unit: "imperial", maxWidth: 90 }),
      "bottom-left",
    );
    map.addControl(new AttributionControl({ compact: true }), "bottom-right");

    const forceResize = () => {
      map.resize();
    };
    map.on("load", () => {
      forceResize();
      requestAnimationFrame(forceResize);
      for (const name of ["routes", "checkpoints", "forecast", "selected"]) {
        map.addSource(name, { type: "geojson", data: EMPTY_COLLECTION });
      }
      map.addLayer({
        id: "forecast-fill",
        type: "fill",
        source: "forecast",
        paint: {
          "fill-color": RISK_COLOR,
          "fill-opacity": 0.27,
          "fill-antialias": false,
        },
      });
      map.addLayer({
        id: "forecast-grid",
        type: "line",
        source: "forecast",
        layout: { visibility: "none" },
        paint: {
          "line-color": RISK_COLOR,
          "line-width": 0.8,
          "line-opacity": 0.55,
        },
      });
      map.addLayer({
        id: "route-casing",
        type: "line",
        source: "routes",
        layout: {
          "line-cap": "round",
          "line-join": "round",
          "line-sort-key": ["case", ["get", "selected"], 1, 0],
        },
        paint: {
          "line-color": "#ffffff",
          "line-width": ["case", ["get", "selected"], 9, 6],
          "line-opacity": 0.95,
        },
      });
      map.addLayer({
        id: "route-line",
        type: "line",
        source: "routes",
        layout: {
          "line-cap": "round",
          "line-join": "round",
          "line-sort-key": ["case", ["get", "selected"], 1, 0],
        },
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["case", ["get", "selected"], 4.5, 3],
          "line-opacity": ["case", ["get", "selected"], 1, 0.55],
        },
      });
      map.addLayer({
        id: "checkpoint-dot",
        type: "circle",
        source: "checkpoints",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 3, 8, 5.5],
          "circle-color": ["get", "color"],
          "circle-stroke-width": 1.75,
          "circle-stroke-color": "#ffffff",
        },
      });
      map.addLayer({
        id: "selected-checkpoint-halo",
        type: "circle",
        source: "selected",
        paint: {
          "circle-radius": 11,
          "circle-color": "#ffffff",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#245ba8",
        },
      });
      map.addLayer({
        id: "selected-checkpoint-core",
        type: "circle",
        source: "selected",
        paint: { "circle-radius": 5.5, "circle-color": ["get", "color"] },
      });

      map.on("click", (event) => {
        const checkpoint = map.queryRenderedFeatures(event.point, {
          layers: ["selected-checkpoint-core", "checkpoint-dot"],
        })[0];
        if (checkpoint) {
          const index = Number(checkpoint.properties.index);
          checkpointRef.current?.(index);
          const reading = routeRef.current?.checkpoints.find(
            (item) => item.index === index,
          );
          if (reading) {
            popupRef.current
              .setLngLat([reading.lon, reading.lat])
              .setDOMContent(popupContent(reading, forecastRef.current))
              .addTo(map);
          }
          return;
        }
        const candidate = map.queryRenderedFeatures(event.point, {
          layers: ["route-line"],
        })[0];
        if (candidate) {
          selectRef.current?.(candidate.properties.id);
        } else {
          popupRef.current?.remove();
          checkpointRef.current?.(null);
        }
      });
      map.on("mousemove", (event) => {
        const features = map.queryRenderedFeatures(event.point, {
          layers: ["checkpoint-dot", "selected-checkpoint-core", "route-line"],
        });
        map.getCanvas().style.cursor = features.length ? "pointer" : "";
      });
      popupRef.current = new Popup({
        closeButton: true,
        closeOnClick: false,
        offset: 18,
        maxWidth: "285px",
      });
      setReady(true);
      forceResize();
    });
    map.on("error", (event) => {
      const message = event?.error?.message || "Map failed to render.";
      if (/webgl|worker|context/i.test(message)) {
        setMapError(
          "This browser could not render the map. Route details are available in the list below.",
        );
      }
    });
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(containerRef.current);
    // Parent flex layout often settles after the first paint.
    const shell = containerRef.current?.parentElement;
    if (shell) observer.observe(shell);
    window.addEventListener("resize", forceResize);
    return () => {
      window.removeEventListener("resize", forceResize);
      observer.disconnect();
      popupRef.current?.remove();
      popupRef.current = null;
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    mapRef.current
      .getSource("routes")
      .setData(routeCollection(routes, route?.id));
    mapRef.current
      .getSource("checkpoints")
      .setData(checkpointCollection(route));
    popupRef.current?.remove();
  }, [ready, routes, route]);

  useEffect(() => {
    if (!ready) return;
    mapRef.current
      .getSource("selected")
      .setData(checkpointCollection(route, selectedCheckpointIndex ?? null));
    const checkpoint = route?.checkpoints.find(
      (item) => item.index === selectedCheckpointIndex,
    );
    if (!checkpoint) {
      popupRef.current?.remove();
      return;
    }
    popupRef.current
      .setLngLat([checkpoint.lon, checkpoint.lat])
      .setDOMContent(popupContent(checkpoint, forecastRef.current))
      .addTo(mapRef.current);
  }, [ready, route, selectedCheckpointIndex, frame, tiles, heatmapVisible]);

  useEffect(() => {
    if (!ready) return;
    mapRef.current
      .getSource("forecast")
      .setData(forecastCollection(tiles, frame));
  }, [ready, tiles, frame]);

  useEffect(() => {
    if (!ready) return;
    mapRef.current.setLayoutProperty(
      "forecast-fill",
      "visibility",
      heatmapVisible ? "visible" : "none",
    );
    mapRef.current.setLayoutProperty(
      "forecast-grid",
      "visibility",
      heatmapVisible && showCells ? "visible" : "none",
    );
  }, [ready, showCells, heatmapVisible]);

  useEffect(() => {
    if (!ready) return undefined;
    const markers = [];
    for (const [place, letter, label, checkpoint] of [
      [plan?.origin, "O", "Origin", route?.checkpoints?.[0]],
      [plan?.destination, "D", "Destination", route?.checkpoints?.at(-1)],
    ]) {
      if (!place) continue;
      const badge = document.createElement("button");
      badge.type = "button";
      badge.className = `map-endpoint map-endpoint--${letter.toLowerCase()}`;
      badge.textContent = letter;
      const risk = levelMeta(checkpoint?.level);
      badge.style.backgroundColor = risk.color;
      badge.title = `${label}: ${place.name} · ${risk.label}${checkpoint ? ` at arrival, ${formatDayClock(checkpoint.eta)}` : ""}`;
      badge.setAttribute("aria-label", badge.title);
      badge.disabled = !checkpoint;
      badge.onclick = (event) => {
        event.stopPropagation();
        if (!checkpoint) return;
        checkpointRef.current?.(checkpoint.index);
        popupRef.current
          ?.setLngLat([checkpoint.lon, checkpoint.lat])
          .setDOMContent(popupContent(checkpoint, forecastRef.current))
          .addTo(mapRef.current);
      };
      markers.push(
        new Marker({ element: badge, anchor: "center" })
          .setLngLat([place.lon, place.lat])
          .addTo(mapRef.current),
      );
    }
    routes.forEach((item, index) => {
      if (!item.geometry?.length) return;
      const coordinate =
        item.geometry[
          Math.floor((item.geometry.length - 1) * (0.36 + index * 0.15))
        ];
      const label = document.createElement("button");
      label.type = "button";
      label.className = `map-route-label${item.id === route?.id ? " is-selected" : ""}`;
      label.style.setProperty(
        "--route-color",
        ROUTE_COLORS[index % ROUTE_COLORS.length],
      );
      label.textContent = `${item.label} · ${formatHours(item.duration_hours)}`;
      label.setAttribute(
        "aria-label",
        `Select ${item.label}, ${formatHours(item.duration_hours)}`,
      );
      label.setAttribute("aria-pressed", String(item.id === route?.id));
      label.onclick = (event) => {
        event.stopPropagation();
        selectRef.current?.(item.id);
      };
      markers.push(
        new Marker({ element: label, anchor: "bottom", offset: [0, -12] })
          .setLngLat([coordinate[1], coordinate[0]])
          .addTo(mapRef.current),
      );
    });
    return () => markers.forEach((marker) => marker.remove());
  }, [ready, routes, route, plan?.origin, plan?.destination]);

  useEffect(() => {
    if (ready) fitRoutes(routes);
  }, [ready, routes, fitRoutes]);

  useEffect(() => {
    if (!ready || !focusTarget) return;
    mapRef.current.flyTo({
      center: [focusTarget.lon, focusTarget.lat],
      zoom: Math.max(mapRef.current.getZoom(), 8),
      duration: motionDuration(550),
    });
  }, [ready, focusTarget]);

  return (
    <div className="trip-map-shell">
      <div
        ref={containerRef}
        className="trip-map"
        aria-label="Trip routes and weather forecast map"
      />
      {plan && (
        <div className="map-actions">
          <button
            type="button"
            onClick={() => fitRoutes(routes)}
            disabled={!ready}
            title="Fit every route on the map"
          >
            <span aria-hidden="true">⤢</span> Fit routes
          </button>
          <button
            type="button"
            onClick={() => fitRoutes(route ? [route] : [])}
            disabled={!ready}
            title="Zoom to the selected route"
          >
            Fit selected
          </button>
        </div>
      )}
      {mapError && (
        <div className="map-error" role="alert">
          {mapError}
        </div>
      )}
    </div>
  );
}
