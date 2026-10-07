export const usd = (cents: number) =>
  (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });

/** Same math as the backend split engine, for previews only. */
export function splitCents(amount: number, workerPct: number, referrerPct: number, poolPct: number, hasReferrer: boolean) {
  if (!hasReferrer) { workerPct = 100 - poolPct; referrerPct = 0; }
  let worker = Math.floor((amount * workerPct) / 100);
  const referrer = Math.floor((amount * referrerPct) / 100);
  const pool = Math.floor((amount * poolPct) / 100);
  worker += amount - (worker + referrer + pool);
  return { worker, referrer, pool };
}

export const timeAgo = (iso: string) => {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
};

export const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);