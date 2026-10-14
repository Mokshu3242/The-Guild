"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { usd } from "@/lib/format";
import { AnimatedNumber } from "./AnimatedNumber";

export function PoolBalance({
  cents,
  className = "",
  tagClassName = "text-seal",
}: {
  // Pass undefined while loading, so the first real value doesn't animate.
  cents: number | undefined;
  className?: string;
  tagClassName?: string;
}) {
  const reduce = useReducedMotion();
  const prev = useRef<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [tag, setTag] = useState<{ id: number; delta: number } | null>(null);

  useEffect(() => {
    if (cents === undefined) return;
    if (prev.current !== null && cents > prev.current) {
      setTag({ id: Date.now(), delta: cents - prev.current });
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setTag(null), 1700);
    }
    prev.current = cents;
  }, [cents]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  if (cents === undefined) {
    return <span className={`tabular-nums text-muted ${className}`}>…</span>;
  }

  return (
    <span className={`relative inline-block ${className}`}>
      <AnimatedNumber value={cents} format={usd} />
      <AnimatePresence>
        {tag && !reduce && (
          <motion.span
            key={tag.id}
            initial={{ opacity: 0, y: 0 }}
            animate={{ opacity: [0, 1, 1, 0], y: -28 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.6, times: [0, 0.15, 0.7, 1], ease: "easeOut" }}
            className={`pointer-events-none absolute -top-5 right-0 whitespace-nowrap font-sans text-sm font-semibold ${tagClassName}`}
            aria-hidden="true"
          >
            +{usd(tag.delta)}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}
