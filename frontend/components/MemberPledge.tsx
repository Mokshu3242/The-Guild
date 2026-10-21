"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet, apiPost } from "@/lib/api";
import { Button, ErrorText, Panel, inputCls } from "@/components/ui";

interface Pledge {
  signed: boolean;
  signed_at: string | null;
  signer: string;
  text: string;
  hash: string;
}

export function MemberPledge({ defaultName }: { defaultName: string }) {
  const { data, mutate } = useSWR<Pledge>("pledge", () => apiGet<Pledge>("/me/pledge"));
  const [name, setName] = useState("");
  const [read, setRead] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!data) return null;

  async function sign() {
    setBusy(true);
    setErr(null);
    try {
      await mutate(await apiPost<Pledge>("/me/pledge", { name: name.trim(), hash: data!.hash, agree: read }), {
        revalidate: false,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't sign the pledge");
    } finally {
      setBusy(false);
    }
  }

  if (data.signed) {
    return (
      <Panel title="Member Pledge">
        <p className="text-sm">
          <span className="font-medium text-guild">Signed</span>
          <span className="text-muted">
            {" "}
            by {data.signer}
            {data.signed_at ? ` on ${new Date(data.signed_at).toLocaleDateString()}` : ""}. You can file claims and get
            covered by the safety pool.
          </span>
        </p>
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-muted hover:text-ink">Read what you signed</summary>
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-paper p-3 font-sans text-xs leading-relaxed">
            {data.text}
          </pre>
          <p className="mt-1 break-all text-xs text-muted">Fingerprint (SHA-256): {data.hash}</p>
        </details>
      </Panel>
    );
  }

  return (
    <Panel title="Sign the Member Pledge">
      <p className="text-sm text-muted">
        The safety pool is everyone&apos;s money, so every member makes the same short promise. You need it before you can
        file a claim.
      </p>
      <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-paper p-4 font-sans text-sm leading-relaxed">
        {data.text}
      </pre>
      <label className="mt-4 flex items-start gap-2.5 text-sm">
        <input
          type="checkbox"
          checked={read}
          onChange={(e) => setRead(e.target.checked)}
          className="mt-0.5 h-4 w-4 accent-guild"
        />
        <span>I&apos;ve read the pledge and I agree to it.</span>
      </label>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
          placeholder={`Type your full name, like ${defaultName || "Sara Lee"}`}
          className={inputCls}
        />
        <Button disabled={busy || !read || name.trim().length < 2} onClick={sign} className="shrink-0">
          {busy ? "Signing…" : "Sign the pledge"}
        </Button>
      </div>
      <ErrorText>{err}</ErrorText>
    </Panel>
  );
}
