import { useLayoutEffect, useRef, useState } from "react";

/** Keep the map height stable after a plan loads by expanding from the empty baseline. */
export function useMapCanvasHeight(hasPlan) {
  const mapCanvasRef = useRef(null);
  const mapSizeRef = useRef(null);
  const [mapHeight, setMapHeight] = useState(null);

  useLayoutEffect(() => {
    const canvas = mapCanvasRef.current;
    if (!canvas) return undefined;
    if (!hasPlan) {
      const rememberSize = () => {
        const height = canvas.getBoundingClientRect().height;
        mapSizeRef.current = { height, viewport: window.innerHeight };
        setMapHeight(height);
      };
      rememberSize();
      const observer = new ResizeObserver(rememberSize);
      observer.observe(canvas);
      return () => observer.disconnect();
    }
    const resize = () => {
      const baseline = mapSizeRef.current;
      if (baseline) {
        setMapHeight(
          Math.max(310, baseline.height + window.innerHeight - baseline.viewport),
        );
      }
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [hasPlan]);

  return { mapCanvasRef, mapHeight };
}
