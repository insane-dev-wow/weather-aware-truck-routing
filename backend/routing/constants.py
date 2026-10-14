"""Shared risk thresholds and planner defaults."""

from __future__ import annotations

LEVELS: tuple[str, ...] = ("low", "moderate", "high", "severe", "no_travel")

LEVEL_LABELS: dict[str, str] = {
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "severe": "Severe",
    "no_travel": "No Travel",
}

LEVEL_RANK: dict[str, int] = {level: index for index, level in enumerate(LEVELS)}
LEVEL_SCORE: dict[str, float] = {level: float(index) for index, level in enumerate(LEVELS)}
LEVEL_COLORS: dict[str, str] = {
    "low": "#22c55e",
    "moderate": "#eab308",
    "high": "#f97316",
    "severe": "#ef4444",
    "no_travel": "#7f1d1d",
}

SAMPLE_INTERVALS: tuple[int, ...] = (10, 25, 50)
DEFAULT_SAMPLE_INTERVAL_MILES = 25
HEATMAP_HOURS = 48

# Band tuples are (low, high, level). Wind uppers are exclusive; rain/snow include
# the severe ceiling and treat only values above it as No Travel.
WIND_BANDS: tuple[tuple[float, float | None, str], ...] = (
    (0.0, 25.0, "low"),
    (25.0, 35.0, "moderate"),
    (35.0, 45.0, "high"),
    (45.0, 55.0, "severe"),
    (55.0, None, "no_travel"),
)

RAIN_BANDS: tuple[tuple[float, float | None, str], ...] = (
    (0.0, 0.10, "low"),
    (0.10, 0.25, "moderate"),
    (0.25, 0.50, "high"),
    (0.50, 1.00, "severe"),
    (1.00, None, "no_travel"),
)

SNOW_BANDS: tuple[tuple[float, float | None, str], ...] = (
    (0.0, 0.5, "low"),
    (0.5, 1.0, "moderate"),
    (1.0, 2.0, "high"),
    (2.0, 3.0, "severe"),
    (3.0, None, "no_travel"),
)

HEAVY_LOAD_LBS = 30_000
MAX_LOAD_LBS = 40_000
LOAD_LIMIT_LBS = 80_000

ROUTE_OPTION_COUNT = 3
