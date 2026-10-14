"""Route ranking and recommendation rationale."""

from __future__ import annotations


def format_hours(hours: float) -> str:
    total_minutes = int(round(max(hours, 0.0) * 60))
    whole, minutes = divmod(total_minutes, 60)
    return f"{whole}h {minutes:02d}m"


def is_blocked(summary: dict) -> bool:
    # A short No-Travel segment must not disappear when display miles round to zero.
    return summary.get("counts", {}).get("no_travel", 0) > 0 or summary["no_travel_miles"] > 0


def rank_key(summary: dict) -> tuple:
    return (
        not summary.get("forecast_complete", True),
        is_blocked(summary),
        summary["no_travel_miles"],
        summary["severe_miles"],
        summary["high_miles"],
        summary["avg_score"] if summary["avg_score"] is not None else float("inf"),
        summary["duration_hours"],
    )


def recommend(summaries: list[dict]) -> dict:
    ranked = sorted(summaries, key=rank_key)
    covered = [route for route in ranked if route.get("forecast_complete", True)]
    best = covered[0] if covered else None
    others = covered[1:]
    reasons: list[str] = []

    if len(summaries) == 1:
        reasons.append("Only one usable route is available from the routing service.")

    if best is None:
        reasons.append(
            "Every route has missing weather at one or more checkpoint arrival times. "
            "Choose a departure within the forecast window or retry when complete data is available."
        )
    elif len(covered) < len(summaries):
        reasons.append("Routes with incomplete forecast coverage were excluded from recommendation.")

    if best is not None and is_blocked(best):
        reasons.append(
            f"Even the least-risk fully assessed route contains No-Travel conditions "
            f"({best['no_travel_miles']:g} mi). Delay departure and reassess."
        )

    if others:
        next_severe = min(route["severe_miles"] for route in others)
        if best["severe_miles"] < next_severe - 0.1:
            reasons.append(
                f"Fewest severe-risk miles: {best['severe_miles']:.0f} mi vs "
                f"{next_severe:.0f} mi on the next-best route."
            )
        elif best["severe_miles"] <= 0.1:
            reasons.append("No severe-risk miles at checkpoint arrival times.")

        next_high = min(route["high_miles"] for route in others)
        if best["high_miles"] < next_high - 0.1:
            reasons.append(
                f"Fewest high-risk miles: {best['high_miles']:.0f} mi vs {next_high:.0f} mi."
            )
        elif best["high_miles"] <= 0.1:
            reasons.append("No high-risk miles at checkpoint arrival times.")

        next_avg = min(route["avg_score"] for route in others)
        if best["avg_score"] < next_avg - 1e-9:
            reasons.append(
                f"Lowest average risk score ({best['avg_score']:.2f} vs {next_avg:.2f})."
            )

        fastest = min(route["duration_hours"] for route in covered)
        if abs(best["duration_hours"] - fastest) <= 1e-6:
            reasons.append(f"Also the quickest option at {format_hours(best['duration_hours'])}.")
        else:
            reasons.append(
                f"Adds {format_hours(best['duration_hours'] - fastest)} over the fastest "
                "route \u2014 the trade the ranking accepts for lower weather exposure."
            )

    criteria = []
    for key, label in (
        ("no_travel_miles", "No-Travel miles"),
        ("severe_miles", "Severe miles"),
        ("high_miles", "High miles"),
        ("avg_score", "Average risk score"),
        ("duration_hours", "Travel time"),
    ):
        values = {
            route["id"]: route[key]
            if route.get("forecast_complete", True) or key == "duration_hours"
            else None
            for route in summaries
        }
        criteria.append(
            {
                "key": key,
                "label": label,
                "values": values,
                "winner": min(covered, key=lambda route: route[key])["id"] if covered else None,
            }
        )

    status = (
        "insufficient_forecast"
        if best is None
        else "blocked"
        if is_blocked(best)
        else "recommended"
    )
    headline = "No recommendation — incomplete forecast coverage"
    if best is not None:
        headline = (
            f"{best['label']} recommended"
            if status == "recommended"
            else f"No safe departure — {best['label']} is least risky but includes No Travel"
        )
    return {
        "status": status,
        "route_id": best["id"] if best else None,
        "label": best["label"] if best else None,
        "headline": headline,
        "reasons": reasons,
        "order": [route["id"] for route in ranked],
        "rank": {route["id"]: index + 1 for index, route in enumerate(ranked)},
        "criteria": criteria,
    }
