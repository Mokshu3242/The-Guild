"use client";

import { useState } from "react";
import { AgentFeed } from "@/components/AgentFeed";
import { ApiKeysPanel } from "@/components/ApiKeysPanel";
import { MandatePanel } from "@/components/MandatePanel";
import { useMe } from "@/lib/useMe";
import { PageHeader, Panel } from "@/components/ui";

export default function AgentPage() {
  const [limit, setLimit] = useState(50);
  const { me } = useMe();
  return (
    <div className="space-y-6">
      <PageHeader
        title="Activity"
        description="Every decision that moved money or picked a person. AI suggests, rules calculate, people decide."
        actions={
          <label className="flex items-center gap-2 text-sm text-muted">
            Show
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="rounded-lg border border-line bg-white px-2.5 py-2 text-ink focus:outline-none focus:ring-4 focus:ring-guild/10"
            >
              {[25, 50, 100, 200].map((n) => (
                <option key={n} value={n}>last {n}</option>
              ))}
            </select>
          </label>
        }
      />
      {me?.role === "admin" && <MandatePanel />}
      {me?.role === "admin" && <ApiKeysPanel />}
      <Panel>
        <AgentFeed limit={limit} showRaw />
      </Panel>
    </div>
  );
}

