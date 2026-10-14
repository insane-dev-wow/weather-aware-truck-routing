const lookupCaches = new WeakMap();
const CACHE_TTL = 5 * 60 * 1000;

/** Reuse exact-query results; debounce uncached lookups and suppress stale replies. */
export function schedulePlaceSearch(query, lookup, onResult, onError, onSettled) {
  let cache = lookupCaches.get(lookup);
  if (!cache) {
    cache = new Map();
    lookupCaches.set(lookup, cache);
  }
  const key = query.trim().toLowerCase();
  const saved = cache.get(key);
  if (saved && Date.now() - saved.time < CACHE_TTL) {
    onResult(saved.result);
    onSettled();
    return () => {};
  }
  const controller = new AbortController();
  const timer = setTimeout(async () => {
    try {
      const result = await lookup(query, controller.signal);
      if (!controller.signal.aborted) {
        cache.delete(key);
        cache.set(key, { result, time: Date.now() });
        if (cache.size > 100) cache.delete(cache.keys().next().value);
        onResult(result);
      }
    } catch (error) {
      if (!controller.signal.aborted) onError(error);
    } finally {
      if (!controller.signal.aborted) onSettled();
    }
  }, 200);
  return () => {
    clearTimeout(timer);
    controller.abort();
  };
}
