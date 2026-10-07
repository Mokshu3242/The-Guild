import type { ButtonHTMLAttributes, ReactNode } from "react";

export const inputCls =
  "w-full rounded-md border border-line bg-white px-3 py-2 text-sm placeholder:text-muted/70 " +
  "focus:outline-none focus:ring-2 focus:ring-guild/40 focus:border-guild";

type Variant = "primary" | "quiet" | "danger";

export function Button({ variant = "primary", className = "", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const styles: Record<Variant, string> = {
    primary: "bg-guild text-white hover:bg-guild/90",
    quiet: "border border-line bg-white text-ink hover:bg-paper",
    danger: "border border-alert/40 bg-white text-alert hover:bg-alert-soft",
  };
  return (
    <button
      {...props}
      className={`rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-guild ${styles[variant]} ${className}`}
    />
  );
}

export function Panel({ title, action, children, className = "" }:
  { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-line bg-white ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <h2 className="font-display text-lg font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

const STATUS: Record<string, string> = {
  open: "bg-paper text-muted border-line",
  matched: "bg-guild-soft text-guild border-guild/20",
  in_progress: "bg-guild-soft text-guild border-guild/20",
  pending: "bg-paper text-muted border-line",
  invoiced: "bg-seal-soft text-seal border-seal/25",
  sent: "bg-seal-soft text-seal border-seal/25",
  paid: "bg-guild text-white border-guild",
  disputed: "bg-alert-soft text-alert border-alert/25",
  submitted: "bg-paper text-muted border-line",
  ai_reviewed: "bg-seal-soft text-seal border-seal/25",
  rejected: "bg-alert-soft text-alert border-alert/25",
  active: "bg-guild-soft text-guild border-guild/20",
};

export function StatusPill({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS[status] ?? STATUS.open}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  if (!children) return null;
  return <p role="alert" className="mt-3 rounded-md bg-alert-soft px-3 py-2 text-sm text-alert">{children}</p>;
}

export function Notice({ children }: { children: ReactNode }) {
  if (!children) return null;
  return <p role="status" className="mt-3 rounded-md bg-guild-soft px-3 py-2 text-sm text-guild">{children}</p>;
}