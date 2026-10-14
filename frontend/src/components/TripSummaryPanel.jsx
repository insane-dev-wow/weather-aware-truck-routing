import { formatFullDateTime } from "../lib/format.js";
export default function TripSummaryPanel({ plan, route }) {
  const stats = [
    ["Departure", formatFullDateTime(route.depart_at)],
    ["Arrival", formatFullDateTime(route.arrive_at)],
    ["Load", `${Number(plan.request.load_lbs).toLocaleString()} lb`],
    [
      "Forecast coverage",
      route.forecast_coverage_pct == null
        ? "—"
        : `${route.forecast_coverage_pct}%`,
    ],
  ];
  return (
    <div className="trip-summary-strip">
      <div className="summary-route">
        <strong>{route.label}</strong>
      </div>
      {stats.map(([label, value]) => (
        <div className="summary-stat" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
