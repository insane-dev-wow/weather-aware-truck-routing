import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Slider from "@mui/material/Slider";
import PauseRounded from "@mui/icons-material/PauseRounded";
import PlayArrowRounded from "@mui/icons-material/PlayArrowRounded";
import { formatDayClock } from "../lib/format.js";
import { forecastMarks } from "../lib/mapData.js";
import { LEVEL_ORDER, levelMeta } from "../lib/risk.js";

export default function HeatmapControls({
  hours = [],
  frame = 0,
  onFrame,
  playing,
  onTogglePlay,
  showCells,
  onToggleCells,
  weatherVisible = true,
  arriveAt,
}) {
  const last = Math.max(0, hours.length - 1);
  const current = hours[frame];
  const disabled = hours.length <= 1 || !weatherVisible;
  return (
    <div className={`forecast-controls ${!weatherVisible ? "is-muted" : ""}`}>
      <div className="forecast-timeline">
        <IconButton
          onClick={onTogglePlay}
          disabled={disabled}
          aria-label={playing ? "Pause forecast" : "Play forecast"}
          size="small"
          className="forecast-play"
        >
          {playing ? (
            <PauseRounded fontSize="small" />
          ) : (
            <PlayArrowRounded fontSize="small" />
          )}
        </IconButton>
        <div className="forecast-time">
          <strong>
            {weatherVisible ? "Area forecast" : "Weather hidden"}{" "}
            <span>+{frame}h</span>
          </strong>
          <time>{current ? formatDayClock(current) : "No forecast"}</time>
        </div>
        <Box className="forecast-slider">
          <Slider
            size="small"
            min={0}
            max={Math.max(last, 1)}
            step={1}
            value={Math.min(frame, last)}
            disabled={disabled}
            onChange={(_event, value) => onFrame(value)}
            marks={forecastMarks(hours)}
            valueLabelDisplay="auto"
            valueLabelFormat={(value) => `+${value}h`}
            getAriaValueText={(value) => `${value} hours after departure`}
            aria-label="Weather forecast hours after departure"
            sx={{
              "& .MuiSlider-markLabel": {
                fontSize: 10,
                color: "text.secondary",
              },
              "& .MuiSlider-thumb": { width: 11, height: 11 },
              "& .MuiSlider-markLabel[data-index='0']": { transform: "none" },
              "& .MuiSlider-markLabel:last-child": {
                transform: "translateX(-100%)",
              },
            }}
          />
        </Box>
      </div>
      <div className="forecast-key-row">
        <div className="forecast-legend" aria-label="Weather risk legend">
          {[...LEVEL_ORDER, "unknown"].map((level) => (
            <span key={level}>
              <i style={{ background: levelMeta(level).color }} />
              {levelMeta(level).label}
            </span>
          ))}
        </div>
        <label className="grid-control">
          <input
            type="checkbox"
            checked={Boolean(showCells)}
            onChange={(event) => onToggleCells(event.target.checked)}
            disabled={disabled}
          />
          Grid
        </label>
      </div>
      <div className="forecast-basis">
        Checkpoint dots and route scores use arrival-time weather.
        {weatherVisible && current && arriveAt && new Date(current) > new Date(arriveAt)
          ? " This area forecast is after the selected trip ends."
          : " The slider changes the area forecast only."}
      </div>
    </div>
  );
}
