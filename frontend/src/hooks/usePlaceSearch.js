import { useEffect, useState } from "react";
import { suggestPlaces } from "../lib/api.js";
import { schedulePlaceSearch } from "../lib/placeSearch.js";

/** Search only while the combobox is open; cancel stale queries and timers. */
export function usePlaceSearch(query, enabled) {
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setOptions([]);
    setMessage("");
    const text = query.trim();
    if (!enabled || text.length < 2) {
      setLoading(false);
      return;
    }
    setLoading(true);
    return schedulePlaceSearch(
      text,
      suggestPlaces,
      (data) => {
        setOptions(data?.results ?? []);
        if (!data?.results?.length) setMessage("No matches. Try a city, state, or address.");
      },
      (error) => setMessage(error.message || "Location search is unavailable."),
      () => setLoading(false),
    );
  }, [query, enabled]);

  return { options, loading, message };
}
