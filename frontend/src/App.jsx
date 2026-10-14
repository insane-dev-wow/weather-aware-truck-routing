import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import CircularProgress from "@mui/material/CircularProgress";
import LayersOutlined from "@mui/icons-material/LayersOutlined";
import ExpandMoreRounded from "@mui/icons-material/ExpandMoreRounded";
import AppHeader from "./components/AppHeader.jsx";
import CheckpointTable from "./components/CheckpointTable.jsx";
import HeatmapControls from "./components/HeatmapControls.jsx";
import PlannerForm from "./components/PlannerForm.jsx";
import RecommendationPanel from "./components/RecommendationPanel.jsx";
import RouteOptionList from "./components/RouteOptionList.jsx";
import RoutingGuideDialog from "./components/RoutingGuideDialog.jsx";
import TripSummaryPanel from "./components/TripSummaryPanel.jsx";
import ToastNotice from "./components/ToastNotice.jsx";
import { useForecastPlayer } from "./hooks/useForecastPlayer.js";
import { useMapCanvasHeight } from "./hooks/useMapCanvasHeight.js";
import { useRoutePlan } from "./hooks/useRoutePlan.js";

const TripMap = lazy(() => import("./components/TripMap.jsx"));

export default function App() {
  const { status, plan, error, submit } = useRoutePlan();
  const [notice, setNotice] = useState(null);
  const noticeId = useRef(0);
  const lastRequest = useRef(null);
  const notify = useCallback((message, severity = "error", retry = null) => {
    setNotice({ id: ++noticeId.current, message, severity, retry });
  }, []);
  const handleSubmit = useCallback(
    (payload) => {
      lastRequest.current = payload;
      setNotice(null);
      return submit(payload);
    },
    [submit],
  );
  useEffect(() => {
    if (error) notify(error, "error", () => handleSubmit(lastRequest.current));
  }, [error, notify, handleSubmit]);
  useEffect(() => {
    if (plan?.warnings?.length) notify(plan.warnings.join("\n"), "warning");
  }, [plan, notify]);

  const [selectedRouteId, setSelectedRouteId] = useState(null);
  const [showCells, setShowCells] = useState(false);
  const [heatmapVisible, setHeatmapVisible] = useState(true);
  const [focusTarget, setFocusTarget] = useState(null);
  const [selectedCheckpointIndex, setSelectedCheckpointIndex] = useState(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const mapSectionRef = useRef(null);
  const { mapCanvasRef, mapHeight } = useMapCanvasHeight(Boolean(plan));

  const hours = plan?.heatmap?.hours ?? [];
  const { frame, setFrame, playing, toggle } = useForecastPlayer({
    frameCount: hours.length,
  });

  useEffect(() => {
    setSelectedRouteId(
      plan?.recommendation?.route_id ?? plan?.routes?.[0]?.id ?? null,
    );
    setFrame(0);
    setFocusTarget(null);
    setSelectedCheckpointIndex(null);
    setDetailsOpen(false);
  }, [plan, setFrame]);

  useEffect(() => {
    setSelectedCheckpointIndex(null);
    setFocusTarget(null);
  }, [selectedRouteId]);

  const selectedRoute = useMemo(
    () =>
      plan?.routes.find((route) => route.id === selectedRouteId) ??
      plan?.routes[0] ??
      null,
    [plan, selectedRouteId],
  );

  const handleFocusCheckpoint = useCallback((checkpoint) => {
    setFocusTarget({
      lat: checkpoint.lat,
      lon: checkpoint.lon,
      nonce: Date.now(),
    });
    setSelectedCheckpointIndex(checkpoint.index);
    mapSectionRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, []);

  const loading = status === "loading";

  return (
    <div className="app-shell">
      <AppHeader onOpenGuide={() => setRulesOpen(true)} />
      <ToastNotice notice={notice} onClose={() => setNotice(null)} />
      <main className="workspace">
        <div className="page-heading">
          <h1>Route planning</h1>
          <span className="workspace-context">
            {plan
              ? `${plan.routes.length} ${plan.routes.length === 1 ? "route available" : "routes compared"}`
              : "New trip"}
          </span>
        </div>
        <PlannerForm onSubmit={handleSubmit} loading={loading} onNotify={notify} />
        {plan && plan.recommendation.status !== "recommended" && (
          <RecommendationPanel
            recommendation={plan.recommendation}
            routes={plan.routes}
            onSelect={setSelectedRouteId}
          />
        )}
        <section
          className={`route-workspace ${!plan ? "is-empty" : ""}`}
          aria-label="Route comparison and map"
          aria-busy={loading}
        >
          {plan && (
            <RouteOptionList
              routes={plan.routes}
              selectedId={selectedRoute?.id}
              recommendedId={
                plan.recommendation.status === "recommended"
                  ? plan.recommendation.route_id
                  : null
              }
              rank={plan.recommendation.rank}
              onSelect={setSelectedRouteId}
              onOpenRationale={() => setRulesOpen("ranking")}
            />
          )}
          <div className="map-panel" ref={mapSectionRef}>
            <div className="map-panel-heading">
              <div>
                <h2>
                  {plan
                    ? `${selectedRoute?.label} · ${plan.request.origin.split(",")[0]} → ${plan.request.destination.split(",")[0]}`
                    : "Route map"}
                </h2>
              </div>
              {plan ? (
                <button
                  className={`layer-button ${heatmapVisible ? "is-active" : ""}`}
                  type="button"
                  aria-pressed={heatmapVisible}
                  onClick={() => {
                    if (heatmapVisible && playing) toggle();
                    setHeatmapVisible((value) => !value);
                  }}
                >
                  <LayersOutlined /> Weather
                </button>
              ) : (
                <span className="quiet-badge">United States</span>
              )}
            </div>
            <div
              ref={mapCanvasRef}
              className="map-canvas"
              style={
                plan && mapHeight
                  ? { height: mapHeight, flex: "0 0 auto" }
                  : undefined
              }
            >
              <Suspense
                fallback={
                  <div className="map-loading">
                    <CircularProgress size={24} />
                    <span>Loading map…</span>
                  </div>
                }
              >
                <TripMap
                  plan={plan}
                  selectedRouteId={selectedRoute?.id}
                  onSelectRoute={setSelectedRouteId}
                  frame={frame}
                  showCells={showCells}
                  heatmapVisible={heatmapVisible}
                  focusTarget={focusTarget}
                  selectedCheckpointIndex={selectedCheckpointIndex}
                  onSelectCheckpoint={setSelectedCheckpointIndex}
                />
              </Suspense>
              {loading && (
                <div className="planning-overlay" role="status">
                  <CircularProgress size={23} />
                  <div>
                    <strong>Calculating routes…</strong>
                    <span>Checking arrival-time weather</span>
                  </div>
                </div>
              )}
            </div>
            {plan ? (
              <div className="forecast-strip">
                <HeatmapControls
                  hours={hours}
                  frame={frame}
                  onFrame={setFrame}
                  playing={playing}
                  onTogglePlay={toggle}
                  showCells={showCells}
                  onToggleCells={setShowCells}
                  weatherVisible={heatmapVisible}
                  arriveAt={selectedRoute?.arrive_at}
                />
              </div>
            ) : (
              <div className="map-empty-caption">
                <span>Road routing</span>
                <span>48-hour weather forecast</span>
              </div>
            )}
          </div>
        </section>
        {selectedRoute && (
          <section className="journey-details">
            <TripSummaryPanel plan={plan} route={selectedRoute} />
            <button
              className="details-toggle"
              type="button"
              aria-expanded={detailsOpen}
              aria-controls="checkpoint-details"
              onClick={() => setDetailsOpen((value) => !value)}
            >
              <span>
                <strong>Checkpoints</strong>
                <span>
                  {selectedRoute.checkpoint_count} points ·{" "}
                  {plan.request.sample_interval_miles}-mile spacing
                </span>
              </span>
              <span className="details-toggle-action">
                {detailsOpen ? "Collapse" : "Expand"}
                <ExpandMoreRounded className={detailsOpen ? "rotated" : ""} />
              </span>
            </button>
            <div id="checkpoint-details" hidden={!detailsOpen}>
              {detailsOpen && (
                <CheckpointTable
                  route={selectedRoute}
                  onFocus={handleFocusCheckpoint}
                  selectedIndex={selectedCheckpointIndex}
                />
              )}
            </div>
          </section>
        )}
      </main>
      <RoutingGuideDialog
        open={rulesOpen}
        onClose={() => setRulesOpen(false)}
        plan={plan}
      />
    </div>
  );
}
