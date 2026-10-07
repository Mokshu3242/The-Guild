"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { mutate } from "swr";
import { apiPost } from "@/lib/api";
import { Button, ErrorText, inputCls } from "@/components/ui";

export default function NewJobPage() {
  const router = useRouter();
  const [f, setF] = useState({ client_name: "", client_email: "", description: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const job = await apiPost<{ id: string }>("/jobs", f);
      mutate("jobs");
      router.push(`/jobs/view?id=${job.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't post the job");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-display text-3xl font-bold">Post a job you can't take</h1>
      <p className="mt-2 text-muted">You'll earn a referral fee when the client pays whoever does it.</p>
      <form onSubmit={submit} className="mt-6 space-y-4 rounded-lg border border-line bg-white p-6">
        <label className="block text-sm font-medium">Client name
          <input required value={f.client_name} onChange={(e) => setF({ ...f, client_name: e.target.value })} className={`${inputCls} mt-1`} />
        </label>
        <label className="block text-sm font-medium">Client email
          <input required type="email" value={f.client_email} onChange={(e) => setF({ ...f, client_email: e.target.value })} className={`${inputCls} mt-1`} />
          <span className="mt-1 block text-xs font-normal text-muted">Invoices go here. In the demo, use a PayPal sandbox client email.</span>
        </label>
        <label className="block text-sm font-medium">What does the client need?
          <textarea required minLength={10} rows={5} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })}
            className={`${inputCls} mt-1`} placeholder="Skills, scope, and timeline. The AI uses this to pick the right member." />
        </label>
        <ErrorText>{err}</ErrorText>
        <Button disabled={busy} className="w-full">{busy ? "Posting…" : "Post job"}</Button>
      </form>
    </div>
  );
}