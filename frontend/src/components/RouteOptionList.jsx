import { formatHours, formatNumber } from "../lib/format.js";
import { ROUTE_COLORS, levelMeta } from "../lib/risk.js";

export default function RouteOptionList({
  routes,
  selectedId,
  recommendedId,
  rank,
  onSelect,
  onOpenRationale,
}) {
  const orderedRoutes = routes
    .map((route, index) => ({
      route,
      index,
      position: rank?.[route.id] ?? Infinity,
    }))
    .sort((a, b) =>
      a.position === b.position ? a.index - b.index : a.position - b.position,
    );

  return (
    <section className="route-comparison" aria-label="Route comparison">
      <div className="comparison-toolbar">
        <div className="comparison-title">
          <h2>Route comparison</h2>
          <span className="comparison-count">
            {routes.length} {routes.length === 1 ? "route" : "routes"} · Arrival-time risk
          </span>
        </div>
        {onOpenRationale && (
          <button
            type="button"
            className="comparison-rules"
            onClick={onOpenRationale}
          >
            Ranking rules
          </button>
        )}
      </div>
      <div
        className="comparison-scroll"
        role="region"
        tabIndex={0}
        aria-label="Route comparison data"
      >
        <table className="route-comparison-table">
          <thead>
            <tr>
              <th scope="col">Route</th>
              <th scope="col" className="numeric">
                Drive time
              </th>
              <th scope="col" className="numeric">
                Distance
              </th>
              <th scope="col">Peak risk</th>
              <th scope="col" className="numeric">
                No Travel mi
              </th>
              <th scope="col" className="numeric">
                Severe mi
              </th>
              <th scope="col" className="numeric">
                High mi
              </th>
              <th scope="col" className="numeric">
                <span title="Distance-weighted risk: Low 0, Moderate 1, High 2, Severe 3, No Travel 4. Zero means Low under the assessment rules, not no possible risk.">Avg risk (0–4)</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {orderedRoutes.map(({ route, index }) => {
              const selected = route.id === selectedId;
              const incomplete = route.forecast_complete === false;
              const recommended =
                route.id === recommendedId &&
                !incomplete &&
                route.viable !== false;
              const risk = levelMeta(route.max_level);
              return (
                <tr
                  key={route.id}
                  className={selected ? "is-selected" : ""}
                  onClick={(event) => {
                    if (!event.target.closest("input, label"))
                      onSelect(route.id);
                  }}
                >
                  <th scope="row">
                    <label className="comparison-route-select">
                      <input
                        type="radio"
                        name="selected-route"
                        checked={selected}
                        aria-label={`Select ${route.label}`}
                        onChange={() => onSelect(route.id)}
                      />
                      <span
                        className="comparison-route-line"
                        style={{
                          backgroundColor:
                            ROUTE_COLORS[index % ROUTE_COLORS.length],
                        }}
                        aria-hidden="true"
                      />
                      <span className="comparison-route-name">
                        {route.label}
                      </span>
                    </label>
                    {recommended && (
                      <span className="comparison-route-status">
                        Recommended
                      </span>
                    )}
                    {incomplete && (
                      <span className="comparison-route-warning">
                        Incomplete forecast
                      </span>
                    )}
                  </th>
                  <td className="numeric">
                    {formatHours(route.duration_hours)}
                  </td>
                  <td className="numeric">{formatNumber(route.distance_miles)} mi</td>
                  <td
                    className="comparison-peak-risk"
                    style={{ color: risk.color }}
                  >
                    {risk.label}
                    {incomplete && route.max_level !== "unknown"
                      ? " (partial)"
                      : ""}
                  </td>
                  <td className="numeric">{formatNumber(route.no_travel_miles)}</td>
                  <td className="numeric">{formatNumber(route.severe_miles)}</td>
                  <td className="numeric">{formatNumber(route.high_miles)}</td>
                  <td className="numeric">
                    {route.avg_score == null
                      ? "—"
                      : Number(route.avg_score).toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
