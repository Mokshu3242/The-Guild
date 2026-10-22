"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";

/** Admin-only invite code on the dashboard. Click the code to copy it; the arrow makes a new one. */
export function InviteCode({ guildId, code, onChange }: { guildId: string; code: string; onChange: () => void }) {
  const [copied, setCopied] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setErr("Couldn't copy. Select the code and copy it yourself.");
    }
  }

  async function refresh() {
    setBusy(true);
    setErr(null);
    try {
      await apiPost(`/guilds/${guildId}/invite`);
      onChange();
      setConfirm(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't make a new code");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span className="inline-flex items-stretch overflow-hidden rounded-lg border border-white/15 text-sm text-white/80">
        <button
          type="button"
          onClick={copy}
          title="Copy the invite code"
          className="px-3 py-2 text-left transition-colors hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white/50"
        >
          {copied ? (
            <span className="font-semibold text-seal-bright">Copied</span>
          ) : (
            <>
              Invite code <span className="ml-1 font-semibold tracking-wide text-white">{code}</span>
            </>
          )}
        </button>
        <button
          type="button"
          onClick={() => setConfirm(!confirm)}
          disabled={busy}
          title="Make a new invite code"
          aria-label="Make a new invite code"
          className="border-l border-white/15 px-2.5 transition-colors hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white/50 disabled:opacity-50"
        >
          <svg viewBox="0 0 20 20" className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} aria-hidden="true">
            <path
              d="M15.5 8A6 6 0 0 0 4.6 6.4M4.5 12a6 6 0 0 0 10.9 1.6M4.3 3.5v3.2h3.2M15.7 16.5v-3.2h-3.2"
              stroke="currentColor"
              strokeWidth="1.6"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </span>
      {confirm && (
        <span className="inline-flex items-center gap-2 text-sm text-white/80">
          The old code stops working.
          <button
            type="button"
            onClick={refresh}
            disabled={busy}
            className="rounded-md bg-white px-2.5 py-1 font-medium text-guild-deep hover:bg-seal-bright disabled:opacity-50"
          >
            {busy ? "Making…" : "New code"}
          </button>
          <button type="button" onClick={() => setConfirm(false)} className="text-white/70 hover:text-white">
            Cancel
          </button>
        </span>
      )}
      {err && <span className="w-full text-xs text-seal-bright">{err}</span>}
    </span>
  );
}
