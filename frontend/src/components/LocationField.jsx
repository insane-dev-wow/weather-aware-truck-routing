import { useEffect, useId, useRef, useState } from "react";
import SearchRounded from "@mui/icons-material/SearchRounded";
import CircularProgress from "@mui/material/CircularProgress";
import { usePlaceSearch } from "../hooks/usePlaceSearch.js";

export default function LocationField({ label, value, onChange, placeholder, marker }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [composing, setComposing] = useState(false);
  const [active, setActive] = useState(-1);
  const inputRef = useRef(null);
  const optionRefs = useRef([]);
  const { options, loading, message } = usePlaceSearch(value, open && !composing);
  const visible = open && !composing && value.trim().length >= 2;

  useEffect(() => setActive(-1), [options]);
  useEffect(() => {
    if (active >= 0) optionRefs.current[active]?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function select(option) {
    onChange(option.value);
    inputRef.current?.focus();
    setOpen(false);
    setActive(-1);
  }

  return (
    <div
      className={`planner-field location-field location-field--${marker}`}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <label htmlFor={id}>{label}</label>
      <div className="location-input">
        <span className={`location-dot ${marker}`} />
        <input
          ref={inputRef}
          id={id}
          value={value}
          placeholder={placeholder}
          required
          maxLength={255}
          autoComplete="off"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={visible}
          aria-controls={visible ? `${id}-results` : undefined}
          aria-activedescendant={visible && active >= 0 && options[active] ? `${id}-option-${active}` : undefined}
          onFocus={() => setOpen(true)}
          onCompositionStart={() => setComposing(true)}
          onCompositionEnd={() => setComposing(false)}
          onChange={(event) => {
            onChange(event.target.value);
            setActive(-1);
            setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing) return;
            if (event.key === "Escape") {
              event.preventDefault();
              setOpen(false);
            } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setOpen(true);
              if (options.length) setActive((current) =>
                event.key === "ArrowDown"
                  ? (current + 1) % options.length
                  : (current <= 0 ? options.length - 1 : current - 1));
            } else if (event.key === "Enter" && visible) {
              event.preventDefault();
              if (options[active]) select(options[active]);
              else if (!loading && options.length) select(options[0]);
            }
          }}
        />
        <span className="location-search" aria-hidden="true">
          {loading ? <CircularProgress size={15} /> : <SearchRounded />}
        </span>
      </div>
      {visible && (
        <div className="place-results">
          <span className="place-results-title" role="status">
            {loading ? "Finding places..." : message || `${options.length} locations`}
          </span>
          <div id={`${id}-results`} role="listbox" aria-label={`${label} suggestions`} aria-busy={loading}>
            {options.map((option, index) => (
              <div
                id={`${id}-option-${index}`}
                ref={(element) => { optionRefs.current[index] = element; }}
                key={`${option.lat}-${option.lon}-${index}`}
                role="option"
                aria-selected={active === index}
                className="place-option"
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActive(index)}
                onClick={() => select(option)}
              >
                <strong>{option.label}</strong>
                <span>{option.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
