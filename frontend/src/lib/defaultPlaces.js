/** Resolve both sample cities before changing either input. Never invent a match. */
export async function resolveTripPlaces(preset, lookup, signal, storage) {
  const key = `wayline-places-v1:${preset.slice(1).join("|")}`;
  try {
    storage ??= globalThis.localStorage;
    const saved = JSON.parse(storage?.getItem(key) || "null");
    if (saved && Date.now() - saved.savedAt < 7 * 86400000 &&
        typeof saved.origin === "string" && saved.origin &&
        typeof saved.destination === "string" && saved.destination) {
      return { origin: saved.origin, destination: saved.destination };
    }
  } catch { /* Storage may be unavailable; use autocomplete. */ }
  const matches = await Promise.all(preset.slice(1).map(async (query) => {
    const [city, state] = query.toLowerCase().split(",").map((part) => part.trim());
    const data = await lookup(query, signal);
    const match = data?.results?.find((option) => {
      const parts = option.value.toLowerCase().split(",").map((part) => part.trim());
      return parts[0] === city && parts.includes(state);
    });
    if (!match) throw new Error(`Could not load ${query}. Choose a location using autocomplete.`);
    return match.value;
  }));
  const places = { origin: matches[0], destination: matches[1] };
  if (!signal?.aborted) {
    try { storage?.setItem(key, JSON.stringify({ ...places, savedAt: Date.now() })); }
    catch { /* Private browsing must not prevent location selection. */ }
  }
  return places;
}
