import { alpha } from "@mui/material/styles";

export const LEVEL_ORDER = ["low", "moderate", "high", "severe", "no_travel"];

export const LEVEL_META = {
  low: { label: "Low", color: "#2e7d32" },
  moderate: { label: "Moderate", color: "#b26a00" },
  high: { label: "High", color: "#c2410c" },
  severe: { label: "Severe", color: "#b3261e" },
  no_travel: { label: "No Travel", color: "#6b1113" },
  unknown: { label: "No forecast", color: "#6b7280" },
};

export const ROUTE_COLORS = ["#1d4e79", "#6a1b9a", "#00695c", "#8d6e63"];

export function levelMeta(level) {
  return LEVEL_META[level] || LEVEL_META.unknown;
}

export function levelFromScore(score) {
  if (score == null) return "unknown";
  const rounded = Math.round(score);
  return LEVEL_ORDER[Math.max(0, Math.min(LEVEL_ORDER.length - 1, rounded))] || "low";
}

export function riskChipSx(level) {
  const { color } = levelMeta(level);
  return {
    color,
    backgroundColor: alpha(color, 0.1),
    border: `1px solid ${alpha(color, 0.35)}`,
    fontWeight: 700,
    height: 22,
  };
}
