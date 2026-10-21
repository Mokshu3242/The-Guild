"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Button, ErrorText, Panel, inputCls } from "@/components/ui";

interface Key {
  id: string;
  name: string;
  prefix: string;
  active: boolean;
  request_count: number;
  last_used_at: string | null;
  created_at: string;
  hires: number;
  key?: string;
}

const API = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

/** 13A. Admins make keys a client's AI agent uses to quote and hire the guild. */
export function ApiKeysPanel() {
  const { data, mutate } = useSWR<Key[]>("api-keys", () => apiGet<Key[]>("/api-keys"));
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState<Key | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const k = await apiPost<Key>("/api-keys", { name: name.trim() });
      setFresh(k);
      setCopied(false);
      setName("");
      await mutate();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't make the key");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    setBusy(true);
    setErr(null);
    try {
      await apiDelete(`/api-keys/${id}`);
      setConfirm(null);
      if (fresh?.id === id) setFresh(null);
      await mutate();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't turn off the key");
    } finally {
      setBusy(false);
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const config = fresh?.key
    ? JSON.stringify(
        {
          mcpServers: {
            guild: {
              command: "python",
              args: ["C:/path/to/The-Guild/mcp/guild_mcp.py"],
              env: { GUILD_API_KEY: fresh.key, GUILD_API_URL: API || "https://your-backend" },
            },
          },
        },
        null,
        2,
      )
    : "";

  return (
    <Panel title="Hire by agent">
      <p className="text-sm text-muted">
        Give a client&apos;s AI assistant a key, and it can ask the guild for a quote and hire it, all by itself. Every
        job still goes through the normal steps: the client accepts the agreement and pays each milestone through PayPal.
        Jobs that come in this way list you as the referrer.
      </p>

      <form onSubmit={create} className="mt-4 flex flex-col gap-2 sm:flex-row">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
          placeholder="Who is it for? Like: Anna's assistant"
          className={inputCls}
        />
        <Button disabled={busy || name.trim().length < 2} className="shrink-0">
          {busy ? "Making…" : "Make a key"}
        </Button>
      </form>
      <ErrorText>{err}</ErrorText>

      {fresh?.key && (
        <div className="mt-4 rounded-lg border border-seal/30 bg-seal-soft p-4 text-sm">
          <p className="font-medium text-seal">Copy this key now. You won&apos;t see it again.</p>
          <code className="mt-2 block break-all rounded bg-white px-2.5 py-2 font-mono text-xs">{fresh.key}</code>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button variant="quiet" onClick={() => copy(fresh.key!)}>
              {copied ? "Copied" : "Copy key"}
            </Button>
            <Button variant="quiet" onClick={() => setFresh(null)}>
              I saved it
            </Button>
          </div>
          <details className="mt-3">
            <summary className="cursor-pointer text-muted hover:text-ink">Set it up in Claude Desktop</summary>
            <p className="mt-2 text-muted">
              Add this to <code className="font-mono text-xs">claude_desktop_config.json</code>, fix the path to{" "}
              <code className="font-mono text-xs">guild_mcp.py</code>, then restart Claude Desktop.
            </p>
            <pre className="mt-2 overflow-x-auto rounded bg-white p-3 font-mono text-xs leading-relaxed">{config}</pre>
          </details>
        </div>
      )}

      {data && data.length > 0 && (
        <ul className="mt-4 divide-y divide-line">
          {data.map((k) => (
            <li key={k.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
              <div className="min-w-0">
                <p className="font-medium">
                  {k.name}{" "}
                  <span className={`text-xs font-normal ${k.active ? "text-guild" : "text-muted"}`}>
                    {k.active ? "on" : "turned off"}
                  </span>
                </p>
                <p className="text-xs text-muted">
                  <code className="font-mono">{k.prefix}…</code> · {k.hires} {k.hires === 1 ? "hire" : "hires"} ·{" "}
                  {k.request_count} {k.request_count === 1 ? "request" : "requests"}
                  {k.last_used_at ? ` · last used ${timeAgo(k.last_used_at)}` : " · not used yet"}
                </p>
              </div>
              {k.active &&
                (confirm === k.id ? (
                  <div className="flex gap-2">
                    <Button variant="danger" disabled={busy} onClick={() => revoke(k.id)}>
                      Yes, turn it off
                    </Button>
                    <Button variant="quiet" onClick={() => setConfirm(null)}>
                      Keep it
                    </Button>
                  </div>
                ) : (
                  <Button variant="quiet" onClick={() => setConfirm(k.id)}>
                    Turn off
                  </Button>
                ))}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
