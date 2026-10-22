"use client";

import useSWR from "swr";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { usd } from "@/lib/format";
import { Panel, Skeleton } from "@/components/ui";

interface Booking {
  job_id: string;
  client: string;
  start: string;
  end: string;
  days: number;
  work_cents: number;
}
interface Row {
  id: string;
  name: string;
  skills: string[];
  state: "free" | "busy" | "off";
  free_from: string | null;
  away_until: string | null;
  bookings: Booking[];
}
interface Capacity {
  today: string;
  start: string;
  days: number;
  hours_per_day: number;
  members: Row[];
}

// Dates come as YYYY-MM-DD. Compare them as strings, so time zones never shift a day.
const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
const short = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });

function status(r: Row, today: string) {
  if (r.state === "off") return { text: "Not taking work", cls: "text-muted" };
  if (r.state === "free" || !r.free_from || r.free_from <= today) return { text: "Free now", cls: "text-guild" };
  return { text: `Free ${short(r.free_from)}`, cls: "text-ink" };
}

/** 14B. Who is busy until when, estimated from open milestones. No library, just a grid. */
export function CapacityBoard() {
  const { data } = useSWR<Capacity>("capacity", () => apiGet<Capacity>("/capacity?weeks=2"), {
    refreshInterval: 60_000,
  });
  if (!data) return <Skeleton className="h-48" />;

  const days = Array.from({ length: data.days }, (_, i) => {
    const iso = addDays(data.start, i);
    const dow = new Date(`${iso}T00:00:00Z`).getUTCDay();
    return { iso, weekend: dow === 0 || dow === 6, today: iso === data.today, dow };
  });
  const cols = `minmax(7.5rem, 9rem) repeat(${data.days}, minmax(2rem, 1fr))`;

  return (
    <Panel title="Who's free">
      <p className="text-sm text-muted">
        Estimated from each member&apos;s unfinished milestones at their own rate, {data.hours_per_day} hours a working
        day, one job after another. The AI matcher reads the same dates.
      </p>

      <div className="mt-4 overflow-x-auto">
        <div className="min-w-[44rem]" role="table" aria-label="Member bookings for the next two weeks">
          <div className="grid" style={{ gridTemplateColumns: cols }} role="row">
            <div role="columnheader" />
            {days.map((d) => (
              <div
                key={d.iso}
                role="columnheader"
                className={`pb-2 text-center text-[11px] leading-tight ${d.today ? "font-semibold text-ink" : "text-muted"} ${d.weekend ? "opacity-50" : ""}`}
              >
                {new Date(`${d.iso}T00:00:00Z`).toLocaleDateString(undefined, { weekday: "narrow", timeZone: "UTC" })}
                <span className="block">{Number(d.iso.slice(8))}</span>
              </div>
            ))}
          </div>

          {data.members.map((r) => {
            const s = status(r, data.today);
            return (
              <div key={r.id} className="grid border-t border-line" style={{ gridTemplateColumns: cols }} role="row">
                <div className="py-2.5 pr-2" role="rowheader">
                  <p className="truncate text-sm font-medium">{r.name}</p>
                  <p className={`text-xs ${s.cls}`}>{s.text}</p>
                </div>
                {days.map((d) => {
                  const b = r.bookings.find((x) => d.iso >= x.start && d.iso <= x.end);
                  const away = !b && r.away_until && d.iso >= data.today && d.iso < r.away_until;
                  const past = d.iso < data.today;
                  const first = b && (d.iso === b.start || d.dow === 1 || d.iso === data.start);
                  let cls = "bg-guild-soft/50";
                  if (r.state === "off") cls = "bg-paper";
                  if (away) cls = "bg-paper";
                  if (b) cls = "bg-seal-soft text-seal";
                  return (
                    <div
                      key={d.iso}
                      role="cell"
                      title={
                        b
                          ? `${b.client}: ${usd(b.work_cents)} of work, about ${b.days} day${b.days === 1 ? "" : "s"} (${short(b.start)} to ${short(b.end)})`
                          : away
                            ? `${r.name} is away`
                            : "Free"
                      }
                      className={`relative my-1.5 border-l border-white text-[10px] leading-[1.75rem] ${cls} ${d.weekend ? "opacity-40" : ""} ${past ? "opacity-30" : ""} ${d.today ? "ring-1 ring-inset ring-ink/30" : ""}`}
                    >
                      {first && (
                        <Link
                          href={`/jobs/view/?id=${b!.job_id}`}
                          className="absolute inset-y-0 left-1 z-10 max-w-[6rem] truncate font-medium hover:underline"
                        >
                          {b!.client}
                        </Link>
                      )}
                      {away && d.iso === data.today && <span className="pl-1 text-muted">Away</span>}
                      &nbsp;
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-seal-soft" /> Booked (estimate)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-guild-soft/50" /> Free
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm border border-line bg-paper" /> Away or not taking work
        </span>
      </div>
    </Panel>
  );
}
