import { useCallback, useEffect, useRef, useState } from "react";

import { createRoutePlan } from "../lib/api.js";

export function useRoutePlan() {
  const [status, setStatus] = useState("idle");
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);
  const controllerRef = useRef(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const submit = useCallback(async (payload) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setStatus("loading");
    setError(null);
    setPlan(null);
    try {
      const data = await createRoutePlan(payload, controller.signal);
      if (controller.signal.aborted) return null;
      setPlan(data);
      setStatus("ready");
      return data;
    } catch (err) {
      if (err.name === "AbortError") return null;
      setError(err.message || "Something went wrong.");
      setStatus("error");
      return null;
    }
  }, []);

  return { status, plan, error, submit };
}
