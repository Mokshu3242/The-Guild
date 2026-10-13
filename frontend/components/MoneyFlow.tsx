"use client";

import { useEffect, useRef, useState } from "react";
import {
  AnimatePresence,
  animate,
  motion,
  useReducedMotion,
} from "motion/react";
import { usd } from "@/lib/format";
import { createPortal } from "react-dom";

export interface SplitData {
  amountCents: number;
  workerCents: number;
  referrerCents: number;
  poolCents: number;
  recoveredCents?: number;
  workerName: string;
  referrerName: string;
  source: "invoice" | "deposit" | "claim";
}

const EASE = [0.22, 1, 0.36, 1] as const;
const SHOW_MS = 3600;

function CountUp({ to, delay = 0 }: { to: number; delay?: number }) {
  const reduce = useReducedMotion();
  const [value, setValue] = useState(reduce ? to : 0);

  useEffect(() => {
    if (reduce) {
      setValue(to);
      return;
    }
    const controls = animate(0, to, {
      duration: 0.9,
      delay,
      ease: EASE,
      onUpdate: (v) => setValue(Math.round(v)),
    });
    return () => controls.stop();
  }, [to, delay, reduce]);

  return <span className="tabular-nums">{usd(value)}</span>;
}

function Row({
  color,
  label,
  cents,
  delay,
}: {
  color: string;
  label: string;
  cents: number;
  delay: number;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.li
      className="flex items-center justify-between text-sm"
      initial={reduce ? false : { opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.35, delay, ease: EASE }}
    >
      <span className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${color}`} />
        <span className="text-muted">{label}</span>
      </span>
      <span className="font-medium">
        <CountUp to={cents} delay={delay} />
      </span>
    </motion.li>
  );
}

export function MoneyFlow({
  data,
  onDone,
}: {
  data: SplitData | null;
  onDone?: () => void;
}) {
  const reduce = useReducedMotion();

  // Keep the latest onDone in a ref. The parent passes a new arrow every
  // render, and we don't want that to restart the close timer.
  const doneRef = useRef(onDone);
  useEffect(() => {
    doneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (!data) return;
    const close = () => doneRef.current?.();
    const t = setTimeout(close, SHOW_MS);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [data]);

  const total = data?.amountCents ?? 0;
  const parts = data
    ? [
        { cents: data.workerCents, color: "bg-guild", delay: 0.15 },
        { cents: data.referrerCents, color: "bg-gray-500", delay: 0.35 },
        { cents: data.poolCents, color: "bg-seal", delay: 0.55 },
      ].filter((p) => p.cents > 0)
    : [];

  const title =
    data?.source === "deposit"
      ? "Deposit captured"
      : data?.source === "claim"
        ? "Pool paid a claim"
        : "Invoice paid";

  if (typeof document === "undefined") return null;

  return createPortal(
    <AnimatePresence>
      {data && (
        <motion.div
          key="money-flow"
          className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          onClick={() => doneRef.current?.()}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className="w-full max-w-xl rounded-2xl bg-white p-8 shadow-2xl"
            initial={reduce ? false : { scale: 0.9, y: 20, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ duration: 0.3, ease: EASE }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-6 flex items-baseline justify-between">
              <p className="text-sm text-muted">{title}</p>
              <p className="font-display text-3xl font-bold">
                <CountUp to={total} />
              </p>
            </div>

            <div className="flex h-4 w-full overflow-hidden rounded-full bg-paper">
              {parts.map((p, i) => (
                <motion.div
                  key={i}
                  className={`${p.color} h-full`}
                  initial={reduce ? false : { width: 0 }}
                  animate={{ width: `${(p.cents / total) * 100}%` }}
                  transition={{ duration: 0.9, delay: p.delay, ease: EASE }}
                />
              ))}
            </div>

            <ul className="mt-5 space-y-3">
              {data.workerCents > 0 && (
                <Row color="bg-guild" label={data.workerName} cents={data.workerCents} delay={0.35} />
              )}
              {data.referrerCents > 0 && (
                <Row color="bg-gray-500" label={data.referrerName} cents={data.referrerCents} delay={0.55} />
              )}
              {data.poolCents > 0 && (
                <Row color="bg-seal" label="Safety pool" cents={data.poolCents} delay={0.75} />
              )}
              {data.recoveredCents ? (
                <Row
                  color="bg-seal/60"
                  label="Returned to pool (recovered)"
                  cents={data.recoveredCents}
                  delay={0.9}
                />
              ) : null}
            </ul>

            <p className="mt-6 text-xs text-muted">
              Paid out automatically through PayPal. Click anywhere or press Esc to close.
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  , document.body);
}