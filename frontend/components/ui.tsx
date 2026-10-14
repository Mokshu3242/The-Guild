"use client";

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export const focusRing =
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/50 focus-visible:ring-offset-2 focus-visible:ring-offset-white";

export const inputCls =
  "w-full rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm text-ink shadow-[inset_0_1px_0_rgba(21,32,27,0.03)] " +
  "placeholder:text-muted/70 transition-colors hover:border-muted/40 " +
  "focus:outline-none focus:border-guild focus:ring-4 focus:ring-guild/10";

type Variant = "primary" | "quiet" | "danger";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-guild text-white shadow-sm shadow-guild/20 hover:bg-guild-deep active:translate-y-px",
  quiet: "border border-line bg-white text-ink hover:border-muted/40 hover:bg-paper",
  danger: "border border-alert/30 bg-white text-alert hover:bg-alert-soft",
};

/** Same look as Button, for <a> and <Link>. */
export const buttonCls = (variant: Variant = "primary", className = "") =>
  `inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition ${focusRing} ` +
  `disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${className}`;

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button {...props} className={buttonCls(variant, className)} />;
}

export function Panel({
  title,
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-line bg-white ${className}`}>
      {title && (
        <header className="flex flex-wrap items-center justify-between gap-3 px-5 pt-5 sm:px-6">
          <h2 className="font-display text-lg font-semibold tracking-tight">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5 sm:p-6">{children}</div>
    </section>
  );
}

/** Page title block used on every signed-in page. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>
        {description && <p className="mt-2 max-w-prose text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Grey placeholder block while data loads. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-line/70 ${className}`} aria-hidden="true" />;
}

const STATUS: Record<string, { cls: string; dot: string }> = {
  open: { cls: "bg-paper text-muted", dot: "bg-muted/60" },
  matched: { cls: "bg-guild-soft text-guild", dot: "bg-guild" },
  in_progress: { cls: "bg-guild-soft text-guild", dot: "bg-guild" },
  pending: { cls: "bg-paper text-muted", dot: "bg-muted/60" },
  invoiced: { cls: "bg-seal-soft text-seal", dot: "bg-seal" },
  sent: { cls: "bg-seal-soft text-seal", dot: "bg-seal" },
  paid: { cls: "bg-guild text-white", dot: "bg-white" },
  covered: { cls: "bg-seal-soft text-seal", dot: "bg-seal" },
  disputed: { cls: "bg-alert-soft text-alert", dot: "bg-alert" },
  submitted: { cls: "bg-paper text-muted", dot: "bg-muted/60" },
  ai_reviewed: { cls: "bg-seal-soft text-seal", dot: "bg-seal" },
  rejected: { cls: "bg-alert-soft text-alert", dot: "bg-alert" },
  active: { cls: "bg-guild-soft text-guild", dot: "bg-guild" },
};

export function StatusPill({ status }: { status: string }) {
  const reduced = useReducedMotion();
  const prev = useRef<string>(status);
  const changed = prev.current !== status;

  useEffect(() => {
    prev.current = status;
  }, [status]);

  const s = STATUS[status] ?? STATUS.open;
  return (
    <motion.span
      key={status}
      initial={reduced || !changed ? false : { opacity: 0, y: -6, rotateX: -70 }}
      animate={{ opacity: 1, y: 0, rotateX: 0 }}
      transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
      style={{ transformPerspective: 500 }}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} aria-hidden="true" />
      {status.replaceAll("_", " ")}
    </motion.span>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" className="mt-3 rounded-lg border border-alert/20 bg-alert-soft px-3.5 py-2.5 text-sm text-alert">
      {children}
    </p>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <p role="status" className="mt-3 rounded-lg border border-guild/15 bg-guild-soft px-3.5 py-2.5 text-sm text-guild">
      {children}
    </p>
  );
}
