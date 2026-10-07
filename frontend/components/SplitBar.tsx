import { splitCents, usd } from "@/lib/format";

export function SplitBar({ amount, workerPct, referrerPct, poolPct, hasReferrer = true, workerName = "Worker", referrerName = "Referrer" }: {
  amount: number; workerPct: number; referrerPct: number; poolPct: number;
  hasReferrer?: boolean; workerName?: string; referrerName?: string;
}) {
  const s = splitCents(amount, workerPct, referrerPct, poolPct, hasReferrer);
  const parts = [
    { label: workerName, cents: s.worker, color: "bg-guild", dot: "bg-guild" },
    { label: referrerName, cents: s.referrer, color: "bg-ink/70", dot: "bg-ink/70" },
    { label: "Safety pool", cents: s.pool, color: "bg-seal", dot: "bg-seal" },
  ].filter((p) => p.cents > 0);

  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-paper" role="img"
        aria-label={parts.map((p) => `${p.label} ${usd(p.cents)}`).join(", ")}>
        {parts.map((p) => (
          <div key={p.label} className={p.color} style={{ width: `${(p.cents / amount) * 100}%` }} />
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {parts.map((p) => (
          <li key={p.label} className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${p.dot}`} />
            <span className="text-muted">{p.label}</span>
            <span className="font-medium tabular-nums">{usd(p.cents)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}