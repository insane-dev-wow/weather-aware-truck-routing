import { formatDayClock } from "./format.js";
import { forecastAtPoint } from "./mapData.js";
import { levelFromScore, levelMeta } from "./risk.js";

export function popupContent(checkpoint, forecast) {
  const wrap = document.createElement("div");
  wrap.className = "map-popup";
  const kicker = document.createElement("div");
  kicker.className = "map-popup__eyebrow";
  kicker.textContent = `CHECKPOINT ${checkpoint.index + 1} · MILE ${Math.round(checkpoint.mile)}`;
  const title = document.createElement("div");
  title.className = "map-popup__title";
  title.textContent = `Arrival · ${formatDayClock(checkpoint.eta)}`;
  const risk = document.createElement("span");
  risk.className = "map-popup__risk";
  const meta = levelMeta(checkpoint.level);
  risk.style.color = meta.color;
  risk.style.backgroundColor = `${meta.color}12`;
  risk.textContent = meta.label;
  const headline = document.createElement("p");
  headline.className = "map-popup__headline";
  headline.textContent =
    checkpoint.headline || checkpoint.weather || "Forecast unavailable";
  const grid = document.createElement("dl");
  grid.className = "map-popup__grid";
  [
    ["Wind", checkpoint.wind_mph == null ? "—" : `${checkpoint.wind_mph} mph`],
    [
      "Rain",
      checkpoint.rain_in_hr == null
        ? "—"
        : `${Number(checkpoint.rain_in_hr).toFixed(2)} in/hr`,
    ],
    [
      "Snow",
      checkpoint.snow_in_hr == null
        ? "—"
        : `${Number(checkpoint.snow_in_hr).toFixed(2)} in/hr`,
    ],
  ].forEach(([label, value]) => {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    grid.append(dt, dd);
  });
  wrap.append(kicker, title, risk);
  if (checkpoint.level !== "low") wrap.append(headline);
  wrap.append(grid);
  if (forecast?.visible && forecast.time) {
    const comparison = document.createElement("p");
    comparison.className = "map-popup__headline";
    const area = levelMeta(
      levelFromScore(forecastAtPoint(forecast.tiles, checkpoint, forecast.frame)),
    );
    comparison.textContent = `Area forecast · ${formatDayClock(forecast.time)}: ${area.label}. Route risk uses arrival-time weather at this checkpoint.`;
    wrap.append(comparison);
  }
  return wrap;
}
