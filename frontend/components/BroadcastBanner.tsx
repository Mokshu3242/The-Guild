"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { apiGet } from "@/lib/api";

export interface Notices {
  broadcasts: { id: string; level: "info" | "warning" | "critical"; title: string; body: string }[];
  maintenance: { id: string; mode: "read_only" | "full_pause"; message: string; ends_at: string | null } | null;
  upcoming: { id: string; mode: string; message: string; starts_at: string } | null;
}

export const NOTICES_KEY = "notices";
export const fetchNotices = () => apiGet<Notices>("/me/notices");

const LEVEL = {
  info: "bg-guild-soft text-guild-deep border-guild/15",
  warning: "bg-seal-soft text-seal border-seal/20",
  critical: "bg-alert-soft text-alert border-alert/20",
} as const;

const DISMISS_KEY = "guild-dismissed-broadcasts";

function readDismissed(): string[] {
  try {
    return JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]");
  } catch {
    return [];
  }
}

function minutesUntil(iso: string) {
  return Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 60000));
}

function inWords(min: number) {
  if (min < 1) return "less than a minute";
  if (min < 60) return `${min} minute${min === 1 ? "" : "s"}`;
  const h = Math.round(min / 60);
  return `about ${h} hour${h === 1 ? "" : "s"}`;
}

export function BroadcastBanner() {
  const { data } = useSWR<Notices>(NOTICES_KEY, fetchNotices, { refreshInterval: 30_000 });
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [, tick] = useState(0);

  useEffect(() => setDismissed(readDismissed()), []);
  // Re-render every 30s so the countdown stays fresh.
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 30_000);
    return () => clearInterval(t);
  }, []);

  if (!data) return null;

  function dismiss(id: string) {
    const next = [...dismissed, id];
    setDismissed(next);
    try {
      localStorage.setItem(DISMISS_KEY, JSON.stringify(next.slice(-50)));
    } catch {
      /* private mode: dismiss for this visit only */
    }
  }

  const rows: { id: string; cls: string; title: string; body: string; canDismiss: boolean }[] = [];

  if (data.maintenance?.mode === "read_only") {
    rows.push({
      id: data.maintenance.id,
      cls: LEVEL.warning,
      title: "Read only for maintenance",
      body: `${data.maintenance.message}${data.maintenance.ends_at ? ` Back in ${inWords(minutesUntil(data.maintenance.ends_at))}.` : ""}`,
      canDismiss: false,
    });
  }
  if (data.upcoming) {
    rows.push({
      id: data.upcoming.id,
      cls: LEVEL.warning,
      title: `Maintenance in ${inWords(minutesUntil(data.upcoming.starts_at))}`,
      body: data.upcoming.message,
      canDismiss: false,
    });
  }
  for (const b of data.broadcasts) {
    if (dismissed.includes(b.id)) continue;
    rows.push({ id: b.id, cls: LEVEL[b.level] ?? LEVEL.info, title: b.title, body: b.body, canDismiss: b.level !== "critical" });
  }

  if (rows.length === 0) return null;

  return (
    <div role="region" aria-label="Announcements">
      {rows.map((r) => (
        <div key={r.id} className={`border-b ${r.cls}`}>
          <div className="mx-auto flex max-w-6xl items-start justify-between gap-3 px-4 py-2.5 text-sm sm:px-6">
            <p>
              <span className="font-semibold">{r.title}.</span> {r.body}
            </p>
            {r.canDismiss && (
              <button
                onClick={() => dismiss(r.id)}
                aria-label="Dismiss"
                className="-mr-1 shrink-0 rounded p-1 opacity-70 hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-current"
              >
                <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
                  <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
