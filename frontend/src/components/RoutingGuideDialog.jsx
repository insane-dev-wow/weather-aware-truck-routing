import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import CloseRounded from "@mui/icons-material/CloseRounded";
import RulesPanel from "./RulesPanel.jsx";

export default function RoutingGuideDialog({ open, onClose, plan }) {
  const ranking = open === "ranking";
  return (
    <Dialog open={Boolean(open)} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle className="guide-title">
        {ranking ? "Route ranking" : "Routing rules"}
        <button
          type="button"
          className="icon-button"
          aria-label="Close routing guide"
          onClick={onClose}
        >
          <CloseRounded />
        </button>
      </DialogTitle>
      <DialogContent>
        {ranking && plan ? (
          <div className="ranking-detail">
            <p>{plan.recommendation.headline}</p>
            <ul>
              {(plan.recommendation.reasons ?? []).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            <p>
              Order: No Travel eligibility, severe miles, high miles, average
              risk, then drive time. Incomplete forecasts are excluded from
              recommendation.
            </p>
          </div>
        ) : (
          <>
            <p className="guide-intro">
              We sample forecast wind, rain, and snow at your estimated arrival
              at each checkpoint, then apply your load weight. Routes with
              missing forecasts or No Travel conditions are clearly flagged.
            </p>
            <RulesPanel />
            <p className="source-note">
              {plan?.routing?.provider_label || "Routing API"} · Open-Meteo ·
              OpenStreetMap. Estimates exclude truck restrictions, breaks, and
              road closures.
            </p>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
