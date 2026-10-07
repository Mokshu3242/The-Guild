"use client";

import { useState } from "react";
import { AgentFeed } from "@/components/AgentFeed";
import { Panel } from "@/components/ui";

export default function AgentPage() {
  const [limit, setLimit] = useState(50);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-bold">Agent log</h1>
          <p className="mt-2 max-w-prose text-muted">
            Every decision that moved money or picked a person. AI suggests, rules calculate, humans approve.
          </p>
        </div>
        <label className="text-sm text-muted">
          Show{" "}
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}
            className="rounded-md border border-line bg-white px-2 py-1 text-ink">
            {[25, 50, 100, 200].map((n) => <option key={n} value={n}>last {n}</option>)}
          </select>
        </label>
      </div>
      <Panel><AgentFeed limit={limit} showRaw /></Panel>
    </div>
  );
}