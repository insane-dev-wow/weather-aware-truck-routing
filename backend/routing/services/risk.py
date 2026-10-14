"""Pure weather-risk classification (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..constants import (
    HEAVY_LOAD_LBS,
    LEVEL_LABELS,
    LEVEL_RANK,
    LEVEL_SCORE,
    MAX_LOAD_LBS,
    RAIN_BANDS,
    SNOW_BANDS,
    WIND_BANDS,
)


def level_from_bands(
    value: float,
    bands: tuple[tuple[float, float | None, str], ...],
    *,
    inclusive_last_finite: bool = False,
) -> str:
    """Map a reading onto band tuples ``(low, high, level)``.

    Finite uppers are exclusive unless ``inclusive_last_finite`` is set, which
    matches rain/snow where the severe ceiling is included and only values
    above it are No Travel.
    """
    value = max(0.0, float(value))
    finite = bands[:-1]
    for index, (_low, high, level) in enumerate(finite):
        if high is None:
            return level
        if inclusive_last_finite and index == len(finite) - 1:
            if value <= high:
                return level
        elif value < high:
            return level
    return bands[-1][2]


def wind_level(mph: float) -> str:
    return level_from_bands(mph, WIND_BANDS)


def rain_level(inches_per_hour: float) -> str:
    return level_from_bands(inches_per_hour, RAIN_BANDS, inclusive_last_finite=True)


def snow_level(inches_per_hour: float) -> str:
    return level_from_bands(inches_per_hour, SNOW_BANDS, inclusive_last_finite=True)


def worst(*levels: str) -> str:
    return max(levels, key=lambda level: LEVEL_RANK.get(level, 0))


def load_escalation(wind_mph: float, load_lbs: float) -> tuple[str | None, str | None]:
    wind_mph = float(wind_mph)
    load_lbs = float(load_lbs)

    if wind_mph >= 55.0:
        return "no_travel", "Wind ≥ 55 mph → No Travel for any load"
    if wind_mph >= 45.0 and load_lbs > HEAVY_LOAD_LBS:
        return (
            "no_travel",
            f"{wind_mph:.0f} mph wind with {load_lbs:,.0f} lb (> 30,000 lb) → No Travel",
        )
    if 35.0 <= wind_mph < 45.0 and load_lbs > MAX_LOAD_LBS:
        return (
            "severe",
            f"{wind_mph:.0f} mph wind with {load_lbs:,.0f} lb (> 40,000 lb) → Severe",
        )
    return None, None


@dataclass
class RiskFactor:
    key: str
    label: str
    value: float
    unit: str
    level: str

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "value": round(self.value, 3),
            "unit": self.unit,
            "level": self.level,
            "level_label": LEVEL_LABELS[self.level],
        }


@dataclass
class RiskAssessment:
    level: str
    score: float
    factors: list[RiskFactor] = field(default_factory=list)
    escalations: list[str] = field(default_factory=list)
    headline: str = ""


def _headline(factors: list[RiskFactor], escalations: list[str], level: str) -> str:
    if escalations:
        return escalations[0]

    notable = [f for f in factors if f.level != "low"]
    if not notable:
        return "Clear — no weather threats at this checkpoint"

    notable.sort(key=lambda f: LEVEL_RANK[f.level], reverse=True)
    parts = [
        f"{f.label.lower()} {f.value:g} {f.unit} ({LEVEL_LABELS[f.level].lower()})"
        for f in notable[:2]
    ]
    return f"{LEVEL_LABELS[level]} — " + ", ".join(parts)


def classify(
    *,
    wind_mph: float,
    rain_in_hr: float,
    snow_in_hr: float,
    load_lbs: float,
) -> RiskAssessment:
    factors = [
        RiskFactor("wind", "Wind", float(wind_mph), "mph", wind_level(wind_mph)),
        RiskFactor("rain", "Rain", float(rain_in_hr), "in/hr", rain_level(rain_in_hr)),
        RiskFactor("snow", "Snow", float(snow_in_hr), "in/hr", snow_level(snow_in_hr)),
    ]

    level = worst(*(factor.level for factor in factors))

    escalations: list[str] = []
    forced, explanation = load_escalation(wind_mph, load_lbs)
    if forced and LEVEL_RANK[forced] > LEVEL_RANK[level]:
        level = forced
    if explanation:
        escalations.append(explanation)

    return RiskAssessment(
        level=level,
        score=LEVEL_SCORE[level],
        factors=factors,
        escalations=escalations,
        headline=_headline(factors, escalations, level),
    )


def band_table() -> dict:
    labels = {
        "wind": ["< 25 mph", "25–34 mph", "35–44 mph", "45–54 mph", "≥ 55 mph"],
        "rain": ["< 0.10 in/hr", "0.10–0.25 in/hr", "0.25–0.50 in/hr", "0.50–1.00 in/hr", "> 1.00 in/hr"],
        "snow": ["< 0.5 in/hr", "0.5–1.0 in/hr", "1.0–2.0 in/hr", "2.0–3.0 in/hr", "> 3.0 in/hr"],
    }

    def bands(name: str, source) -> list[dict]:
        return [
            {"label": labels[name][index], "level": level}
            for index, (_low, _high, level) in enumerate(source)
        ]

    return {
        "levels": [
            {"key": level, "label": LEVEL_LABELS[level], "score": LEVEL_SCORE[level]}
            for level in ("low", "moderate", "high", "severe", "no_travel")
        ],
        "factors": [
            {"key": "wind", "name": "Wind", "bands": bands("wind", WIND_BANDS)},
            {"key": "rain", "name": "Rain", "bands": bands("rain", RAIN_BANDS)},
            {"key": "snow", "name": "Snow", "bands": bands("snow", SNOW_BANDS)},
        ],
        "load_rules": [
            {"when": "Wind ≥ 55 mph", "result": "No Travel", "any_load": True},
            {"when": "Wind 45–54 mph", "result": "No Travel", "load_above_lbs": HEAVY_LOAD_LBS},
            {"when": "Wind 35–44 mph", "result": "Severe", "load_above_lbs": MAX_LOAD_LBS},
        ],
        "recommendation_order": [
            "Fewest No-Travel miles",
            "Fewest Severe miles",
            "Fewest High miles",
            "Lowest average risk score",
            "Shortest travel time",
        ],
    }
