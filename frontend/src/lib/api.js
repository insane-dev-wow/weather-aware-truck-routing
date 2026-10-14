const PRODUCTION_API = "https://weather-aware-truck-routing-green.vercel.app";
const BASE = (
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? PRODUCTION_API : "")
).replace(/\/$/, "");

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, { method = "GET", body, signal, timeoutMs = 120000 } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const forwardAbort = () => controller.abort();
  signal?.addEventListener("abort", forwardAbort);

  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      signal: controller.signal,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (timedOut) {
      throw new ApiError("The planner took too long to respond. Please try again.", 0);
    }
    if (error.name === "AbortError") throw error;
    throw new ApiError("Could not reach the API. Is the Django server running?", 0);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
  }

  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const payload = isJson ? await response.json() : null;

  if (!response.ok) {
    const detail =
      payload?.detail ||
      payload?.error ||
      (payload && typeof payload === "object" && Object.values(payload)[0]) ||
      `Request failed (${response.status}).`;
    throw new ApiError(Array.isArray(detail) ? detail[0] : String(detail), response.status);
  }
  return payload;
}

export function fetchThresholds() {
  return request("/api/thresholds/");
}

export function suggestPlaces(query, signal) {
  return request(`/api/places/?q=${encodeURIComponent(query)}`, { signal });
}

export function createRoutePlan(payload, signal) {
  return request("/api/route-plans/", { method: "POST", body: payload, signal });
}
