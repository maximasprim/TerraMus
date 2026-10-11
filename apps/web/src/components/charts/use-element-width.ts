"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Tracks an element's rendered width so a chart can draw at real pixel size
 * (crisp text, sensible tick density on phones) instead of scaling a fixed
 * viewBox. `initial` is used until measured and wherever there is no layout
 * (server render, tests).
 */
export function useElementWidth(initial = 640) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(initial);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = el.getBoundingClientRect().width;
      if (w > 0) setWidth(Math.floor(w));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, width] as const;
}
