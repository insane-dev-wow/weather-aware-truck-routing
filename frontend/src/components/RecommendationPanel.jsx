import VerifiedUserOutlined from "@mui/icons-material/VerifiedUserOutlined";
import WarningAmberRounded from "@mui/icons-material/WarningAmberRounded";
export default function RecommendationPanel({
  recommendation,
  routes,
  onSelect,
}) {
  const winner = routes.find((route) => route.id === recommendation.route_id);
  const status = recommendation.status ?? "recommended";
  const safe = status === "recommended" && winner;
  const rationale = [
    ...new Set([
      ...(!safe && recommendation.headline ? [recommendation.headline] : []),
      ...(recommendation.reasons ?? []),
    ]),
  ];
  return (
    <div
      className={`recommendation-banner ${safe ? "is-recommended" : "is-caution"}`}
      role="status"
    >
      <span className="recommendation-icon" aria-hidden="true">
        {safe ? <VerifiedUserOutlined /> : <WarningAmberRounded />}
      </span>
      <div className="recommendation-copy">
        <strong>
          {safe ? `${winner.label} recommended` : "No route recommended"}
        </strong>
        {!safe && (
          <span>
            {status === "blocked"
              ? "No Travel conditions"
              : "Forecast incomplete"}
          </span>
        )}
      </div>
      {rationale.length > 0 && (
        <details className="recommendation-reasons">
          <summary>Rationale</summary>
          <ul>
            {rationale.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </details>
      )}
      {safe && (
        <button type="button" onClick={() => onSelect(winner.id)}>
          Select route <span aria-hidden="true">↗</span>
        </button>
      )}
    </div>
  );
}
