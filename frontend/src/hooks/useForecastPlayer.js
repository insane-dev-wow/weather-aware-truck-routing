import { useCallback, useEffect, useState } from "react";

export function useForecastPlayer({ frameCount, intervalMs = 700 }) {
  const [playing, setPlaying] = useState(false);
  const [frame, updateFrame] = useState(0);
  const setFrame = useCallback((value) => {
    setPlaying(false);
    updateFrame(value);
  }, []);
  const toggle = useCallback(() => setPlaying((value) => !value), []);

  useEffect(() => {
    if (!playing || frameCount <= 1) return undefined;
    const timer = setInterval(() => {
      updateFrame((current) => (current + 1) % frameCount);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [playing, frameCount, intervalMs]);

  useEffect(() => {
    updateFrame((current) => Math.min(current, Math.max(0, frameCount - 1)));
    if (frameCount <= 1) setPlaying(false);
  }, [frameCount]);

  return { frame, setFrame, playing, toggle };
}
