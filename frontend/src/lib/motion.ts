/** Shared motion helpers. Every animation in the app respects prefers-reduced-motion. */

import { useEffect, useRef, useState } from "react";

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    const onChange = () => setReduced(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/**
 * Count a number up from 0 on FIRST arrival only.
 *
 * Deliberately not re-triggered when the value changes on a later poll — a
 * dashboard whose numbers re-animate every few seconds is a distraction
 * during a live demo, not polish.
 */
export function useCountUp(value: number | null, durationMs = 500): number {
  const reduced = usePrefersReducedMotion();
  const [display, setDisplay] = useState(0);
  const hasAnimated = useRef(false);
  const frame = useRef<number>();

  useEffect(() => {
    if (value === null || value === undefined) return;

    if (hasAnimated.current || reduced) {
      setDisplay(value);
      return;
    }
    hasAnimated.current = true;

    const from = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
      setDisplay(Math.round(from + (value - from) * eased));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [value, durationMs, reduced]);

  // Later updates (polling) apply instantly.
  useEffect(() => {
    if (hasAnimated.current && value !== null && value !== undefined) {
      const id = setTimeout(() => setDisplay(value), durationMs);
      return () => clearTimeout(id);
    }
  }, [value, durationMs]);

  return value === null || value === undefined ? 0 : display;
}

/** Inline style for a staggered entrance (index * step ms). */
export function stagger(index: number, stepMs = 50): React.CSSProperties {
  return { animationDelay: `${index * stepMs}ms` };
}
