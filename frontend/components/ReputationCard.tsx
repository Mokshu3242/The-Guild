"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import { AiThinking } from "./AiThinking";
import { Button, ErrorText } from "./ui";

interface RepResult {
  summary: string;
  written_by: "ai" | "template";
}

export function ReputationCard({ memberId, name }: { memberId: string; name: string }) {
  const [data, setData] = useState<RepResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      setData(await apiPost<RepResult>(`/members/${memberId}/reputation`));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't write the summary");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          A short summary of {name}&apos;s record in the guild, written from the badges above.
        </p>
        {!busy && (
          <Button variant="quiet" onClick={run}>
            {data ? "Write it again" : "Write a summary"}
          </Button>
        )}
      </div>
      {busy && (
        <div className="mt-3">
          <AiThinking label={`Reading ${name}'s record in the guild…`} />
        </div>
      )}
      {!busy && data && (
        <p className="mt-3 rounded-lg bg-paper p-4 text-sm leading-relaxed">
          {data.summary}
          {data.written_by === "template" && (
            <span className="ml-2 text-xs text-muted">(written without AI)</span>
          )}
        </p>
      )}
      <ErrorText>{err}</ErrorText>
    </div>
  );
}