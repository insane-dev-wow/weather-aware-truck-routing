import Chip from "@mui/material/Chip";

import { levelMeta, riskChipSx } from "../lib/risk.js";

export default function RiskChip({ level, label, size = "small" }) {
  return <Chip size={size} label={label ?? levelMeta(level).label} sx={riskChipSx(level)} />;
}
