/** 14B data from GET /capacity. Shared by the Bryntum board and the plain grid fallback. */
export interface Booking {
  job_id: string;
  client: string;
  start: string; // YYYY-MM-DD, first working day
  end: string; // YYYY-MM-DD, last working day (inclusive)
  days: number;
  work_cents: number;
}
export interface CapacityRow {
  id: string;
  name: string;
  skills: string[];
  state: "free" | "busy" | "off";
  free_from: string | null;
  away_until: string | null;
  bookings: Booking[];
}
export interface Capacity {
  today: string;
  start: string;
  days: number;
  hours_per_day: number;
  members: CapacityRow[];
}

export const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
export const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });

export function freeText(r: CapacityRow, today: string) {
  if (r.state === "off") return "Not taking work";
  if (r.state === "free" || !r.free_from || r.free_from <= today) return "Free now";
  return `Free ${shortDate(r.free_from)}`;
}
