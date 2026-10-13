"use client";

import { useReducedMotion } from "motion/react";

export function Shimmer({
  lines = 2,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();

  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`h-3 rounded ${reduce ? "bg-line" : "guild-shimmer"}`}
          style={{ animationDelay: `${i * 0.14}s`, width: `${100 - i * 12}%` }}
        />
      ))}
    </div>
  );
}