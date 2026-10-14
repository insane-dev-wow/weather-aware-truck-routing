import { memo, useState } from "react";
import NearMeOutlined from "@mui/icons-material/NearMeOutlined";
import { formatDayClock, formatNumber } from "../lib/format.js";
import RiskChip from "./RiskChip.jsx";
function CheckpointTable({ route, onFocus, selectedIndex }) {
  const [filter, setFilter] = useState("all");
  const checkpoints = route.checkpoints.filter(
    (point) =>
      filter === "all" ||
      (filter === "unknown"
        ? point.level === "unknown"
        : ["moderate", "high", "severe", "no_travel"].includes(point.level)),
  );
  return (
    <div className="checkpoint-section">
      <div className="checkpoint-toolbar">
        <div>
          <h3>Checkpoints · {route.label}</h3>
        </div>
        <select
          aria-label="Filter checkpoints"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        >
          <option value="all">All checkpoints</option>
          <option value="risk">Elevated risk</option>
          <option value="unknown">Missing forecasts</option>
        </select>
      </div>
      <div className="checkpoint-scroll">
        <table className="checkpoint-table">
          <thead>
            <tr>
              <th scope="col">Point</th>
              <th scope="col">Mile</th>
              <th scope="col">Estimated arrival</th>
              <th scope="col">Conditions</th>
              <th scope="col">Wind</th>
              <th scope="col">Rain (in/hr)</th>
              <th scope="col">Snow (in/hr)</th>
              <th scope="col">Risk</th>
              <th scope="col">
                <span className="sr-only">View on map</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {checkpoints.map((point) => (
              <tr
                key={point.index}
                className={point.index === selectedIndex ? "is-selected" : ""}
              >
                <td>{String(point.index + 1).padStart(2, "0")}</td>
                <td>{formatNumber(point.mile, 0)} mi</td>
                <td>{formatDayClock(point.eta)}</td>
                <td>
                  {point.weather}
                  <small title={point.headline}>{point.headline}</small>
                </td>
                <td>
                  {point.wind_mph == null ? "—" : `${point.wind_mph} mph`}
                </td>
                <td>{formatNumber(point.rain_in_hr, 2)}</td>
                <td>{formatNumber(point.snow_in_hr, 2)}</td>
                <td>
                  <RiskChip level={point.level} label={point.level_label} />
                </td>
                <td>
                  <button
                    type="button"
                    aria-label={`Show checkpoint ${point.index + 1} on map`}
                    onClick={() => onFocus(point)}
                  >
                    <NearMeOutlined />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!checkpoints.length && (
          <p className="no-checkpoints">No checkpoints match this filter.</p>
        )}
      </div>
    </div>
  );
}
export default memo(CheckpointTable);
