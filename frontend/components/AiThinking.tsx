"use client";

import { motion, useReducedMotion } from "motion/react";
import { Shimmer } from "./Shimmer";

export function AiThinking({ label }: { label: string }) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="rounded-md border border-line bg-paper p-4"
      role="status"
      aria-live="polite"
    >
      <p className="mb-3 flex items-center gap-2 text-sm text-guild">
        <span className="relative flex h-2 w-2">
          {!reduce && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-guild opacity-60" />
          )}
          <span className="relative inline-flex h-2 w-2 rounded-full bg-guild" />
        </span>
        {label}
      </p>
      <Shimmer lines={2} />
    </motion.div>
  );
}