import { useCallback, useEffect, useRef, useState } from "react";
import SwapHorizRounded from "@mui/icons-material/SwapHorizRounded";
import CircularProgress from "@mui/material/CircularProgress";
import LocationField from "./LocationField.jsx";
import { toLocalInputValue } from "../lib/format.js";
import { suggestPlaces } from "../lib/api.js";
import { resolveTripPlaces } from "../lib/defaultPlaces.js";
const PRESETS = [
  ["Denver → Kansas City", "Denver, Colorado", "Kansas City, Missouri"],
  ["Chicago → Minneapolis", "Chicago, Illinois", "Minneapolis, Minnesota"],
  ["Houston → New Orleans", "Houston, Texas", "New Orleans, Louisiana"],
  ["Phoenix → Los Angeles", "Phoenix, Arizona", "Los Angeles, California"],
];
function defaultDeparture() {
  const date = new Date(Date.now() + 2 * 3600000);
  date.setSeconds(0, 0);
  date.setMinutes(Math.ceil(date.getMinutes() / 15) * 15);
  return toLocalInputValue(date);
}
export default function PlannerForm({ onSubmit, loading, onNotify }) {
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [resolving, setResolving] = useState(true);
  const locationRequest = useRef(null);
  const cancelDefaults = () => {
    locationRequest.current?.abort();
    locationRequest.current = null;
    setResolving(false);
  };
  const loadPreset = useCallback(async (preset, initial = false) => {
    locationRequest.current?.abort();
    const controller = new AbortController();
    locationRequest.current = controller;
    setResolving(true);
    const timer = setTimeout(() => {
      if (controller.signal.aborted) return;
      controller.abort();
      if (locationRequest.current === controller) setResolving(false);
      if (!initial) onNotify("Location lookup took too long. Search for your locations or retry the sample trip.");
    }, initial ? 4000 : 10000);
    try {
      const places = await resolveTripPlaces(preset, suggestPlaces, controller.signal);
      if (controller.signal.aborted) return;
      setOrigin(places.origin);
      setDestination(places.destination);
    } catch (error) {
      if (!controller.signal.aborted) {
        controller.abort();
        if (!initial) onNotify(error.message || "Could not load default locations. Search for your origin and destination.");
      }
    } finally {
      clearTimeout(timer);
      if (locationRequest.current === controller) setResolving(false);
    }
  }, [onNotify]);
  useEffect(() => {
    loadPreset(PRESETS[0], true);
    return () => {
      locationRequest.current?.abort();
      locationRequest.current = null;
    };
  }, [loadPreset]);
  const [departAt, setDepartAt] = useState(defaultDeparture);
  const [loadLbs, setLoadLbs] = useState("44000");
  const [sampleInterval, setSampleInterval] = useState(25);
  const handleSubmit = (event) => {
    event.preventDefault();
    if (loading) return;
    if (!origin.trim() || !destination.trim())
      return onNotify("Enter both an origin and a destination.");
    if (origin.trim().toLowerCase() === destination.trim().toLowerCase())
      return onNotify("Choose two different locations.");
    cancelDefaults();
    const departure = new Date(departAt);
    if (!Number.isFinite(departure.getTime()))
      return onNotify("Choose a valid departure date and time.");
    if (
      loadLbs === "" ||
      !Number.isFinite(Number(loadLbs)) ||
      Number(loadLbs) < 0 ||
      Number(loadLbs) > 80000
    )
      return onNotify("Enter a load between 0 and 80,000 lb.");
    onSubmit({
      origin: origin.trim(),
      destination: destination.trim(),
      depart_at: departure.toISOString(),
      load_lbs: Number(loadLbs),
      sample_interval_miles: sampleInterval,
      heatmap_hours: 48,
    });
  };
  return (
    <form id="trip-planner" className="planner-card" onSubmit={handleSubmit} noValidate>
      <fieldset disabled={loading} className="planner-fields">
        <LocationField
          label="Origin"
          value={origin}
          onChange={(value) => { cancelDefaults(); setOrigin(value); }}
          placeholder={resolving ? "Finding default city… or type a location" : "City or address"}
          marker="origin"
        />
        <button
          type="button"
          className="swap-button"
          aria-label="Swap origin and destination"
          onClick={() => {
            cancelDefaults();
            setOrigin(destination);
            setDestination(origin);
          }}
        >
          <SwapHorizRounded />
        </button>
        <LocationField
          label="Destination"
          value={destination}
          onChange={(value) => { cancelDefaults(); setDestination(value); }}
          placeholder={resolving ? "Finding default city… or type a location" : "City or address"}
          marker="destination"
        />
        <label className="planner-field">
          <span>
            Departure <span className="field-note">(local time)</span>
          </span>
          <input
            type="datetime-local"
            required
            value={departAt}
            onChange={(event) => setDepartAt(event.target.value)}
            onInput={(event) => setDepartAt(event.currentTarget.value)}
          />
        </label>
        <label className="planner-field load-field">
          <span>Load weight</span>
          <div className="input-with-unit">
            <input
              type="number"
              aria-label="Load weight in pounds"
              min="0"
              max="80000"
              step="1"
              required
              value={loadLbs}
              onChange={(event) => setLoadLbs(event.target.value)}
            />
            <span>lb</span>
          </div>
        </label>
        <button type="submit" className="primary-button plan-button">
          {loading ? (
            <>
              <CircularProgress size={17} color="inherit" /> Planning…
            </>
          ) : (
            <>Calculate routes</>
          )}
        </button>
      </fieldset>
      <div className="planner-options">
        <div className="sampling-options">
          <span>Checkpoint interval</span>
          <div
            className="segmented-control"
            role="group"
            aria-label="Weather sampling interval"
          >
            {[10, 25, 50].map((interval) => (
              <button
                key={interval}
                type="button"
                disabled={loading}
                aria-pressed={sampleInterval === interval}
                onClick={() => setSampleInterval(interval)}
              >
                {interval} mi
              </button>
            ))}
          </div>
        </div>
        <label className="example-selector">
          <select
            aria-label="Example trip"
            value=""
            disabled={loading}
            onChange={(event) => {
              const preset = PRESETS[Number(event.target.value)];
              if (preset) {
                loadPreset(preset);
              }
            }}
          >
            <option value="" disabled>
              Sample trips
            </option>
            {PRESETS.map((preset, index) => (
              <option value={index} key={preset[0]}>
                {preset[0]}
              </option>
            ))}
          </select>
        </label>
      </div>
    </form>
  );
}
