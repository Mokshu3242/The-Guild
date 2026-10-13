"use client";

import { useEffect, useRef, useState } from "react";
import { animate, useReducedMotion } from "motion/react";

const EASE = [0.22, 1, 0.36, 1] as const;

export function AnimatedNumber({
  value,
  format = (v) => String(v),
  duration = 0.7,
}: {
  value: number;
  format?: (v: number) => string;
  duration?: number;
}) {
  const reduce = useReducedMotion();
  const [display, setDisplay] = useState(value);
  const from = useRef(value);

  useEffect(() => {
    if (reduce || from.current === value) {
      from.current = value;
      setDisplay(value);
      return;
    }
    const controls = animate(from.current, value, {
      duration,
      ease: EASE,
      // Round so usd() always gets whole cents.
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    from.current = value;
    return () => controls.stop();
  }, [value, duration, reduce]);

  return <span className="tabular-nums">{format(display)}</span>;
}