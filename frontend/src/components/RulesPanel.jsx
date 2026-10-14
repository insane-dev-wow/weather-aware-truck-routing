import { useEffect, useState } from "react";
import { fetchThresholds } from "../lib/api.js";
import { levelMeta } from "../lib/risk.js";
export default function RulesPanel() {
  const [rules, setRules] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    fetchThresholds()
      .then((data) => {
        if (alive) setRules(data);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);
  if (failed)
    return (
      <p>Risk rules could not be loaded. Close the guide and try again.</p>
    );
  if (!rules) return <p role="status">Loading risk rules…</p>;
  return (
    <div className="rules-content">
      <div className="rules-factors">
        {rules.factors.map((factor) => (
          <div key={factor.key}>
            <h3>{factor.name}</h3>
            {factor.bands.map((band) => (
              <div className="rule-band" key={band.label}>
                <span style={{ background: levelMeta(band.level).color }} />
                <span>{band.label}</span>
                <strong>{levelMeta(band.level).label}</strong>
              </div>
            ))}
          </div>
        ))}
      </div>
      <h3>Your load matters</h3>
      <div className="load-rules">
        {rules.load_rules.map((rule) => (
          <p key={rule.when}>
            {rule.when}
            {rule.load_above_lbs
              ? ` and over ${rule.load_above_lbs.toLocaleString()} lb`
              : " for any load"}
            <strong>{rule.result}</strong>
          </p>
        ))}
      </div>
      <h3>How the best route is chosen</h3>
      <ol className="ranking-list">
        {rules.recommendation_order.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <p className="rules-footnote">
        No Travel conditions prevent a safe recommendation. Routes with
        incomplete forecasts remain available to inspect, but are excluded from
        the recommendation.
      </p>
    </div>
  );
}
