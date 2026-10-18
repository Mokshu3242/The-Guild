"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet, apiPost } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Button, ErrorText, Panel } from "@/components/ui";

interface Digest {
  id: string;
  period_start: string;
  period_end: string;
  narrative: string;
  stats: Record<string, number>;
  written_by: "ai" | "template";
  created_at: string;
}

const KEY = "digest-latest";

function range(a: string, b: string) {
  const o: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${new Date(a).toLocaleDateString(undefined, o)} to ${new Date(b).toLocaleDateString(undefined, o)}`;
}

export function DigestCard({ isAdmin }: { isAdmin: boolean }) {
  const { data, mutate } = useSWR<{ digest: Digest | null }>(KEY, () => apiGet("/digests/latest"), {
    revalidateOnFocus: false,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function runNow() {
    setBusy(true);
    setErr(null);
    try {
      const r = await apiPost<{ digest: Digest }>("/digests/run", {});
      await mutate({ digest: r.digest }, { revalidate: false });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not write the digest");
    } finally {
      setBusy(false);
    }
  }

  if (!data) return null;
  const d = data.digest;
  if (!d && !isAdmin) return null;   // members see nothing until the first Monday

  return (
    <Panel
      title="This week in the guild"
      action={
        isAdmin ? (
          <Button variant={d ? "quiet" : "primary"} disabled={busy} onClick={runNow}>
            {busy ? "Writing…" : d ? "Write again" : "Write this week's digest"}
          </Button>
        ) : undefined
      }
    >
      {d ? (
        <>
          <p className="text-[15px] leading-relaxed">{d.narrative}</p>
          <p className="mt-2 text-xs text-muted">
            {range(d.period_start, d.period_end)} · {d.written_by === "ai" ? "written by AI" : "plain summary"} ·{" "}
            {timeAgo(d.created_at)}
          </p>
        </>
      ) : (
        <p className="text-sm text-muted">Every Monday the guild gets a short note about the week. None yet.</p>
      )}
      <ErrorText>{err}</ErrorText>
    </Panel>
  );
}
