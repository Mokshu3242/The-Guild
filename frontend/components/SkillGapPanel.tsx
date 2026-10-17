"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import { AiThinking } from "./AiThinking";
import { Button, ErrorText, Panel } from "./ui";

export interface SkillGapResult {
  coverage: "full" | "partial" | "none";
  required_skills: string[];
  covered_by: { skill: string; members: string[]; available?: string[] }[];
  uncovered_skills: string[];
  proposed_role: string;
  member_count: number;
}

const BADGE: Record<SkillGapResult["coverage"], { label: string; cls: string; line: string }> = {
  full: {
    label: "The guild can do this",
    cls: "bg-guild-soft text-guild",
    line: "Every skill this job needs is already in the guild. Ask the AI for a match.",
  },
  partial: {
    label: "Partly covered",
    cls: "bg-seal-soft text-seal",
    line: "The guild covers part of this job, but not all of it.",
  },
  none: {
    label: "Nobody has these skills",
    cls: "bg-alert-soft text-alert",
    line: "Nobody in the guild has the skills this job needs yet.",
  },
};

export function SkillGapPanel({
  jobId,
  clientName,
  guildName,
  inviteCode,
  initial,
  onChange,
}: {
  jobId: string;
  clientName: string;
  guildName?: string;
  inviteCode?: string;
  initial: SkillGapResult | null;
  onChange: () => void;
}) {
  const [result, setResult] = useState<SkillGapResult | null>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function run() {
    setBusy(true);
    setErr(null);
    setCopied(false);
    try {
      setResult(await apiPost<SkillGapResult>(`/jobs/${jobId}/skill-gap`));
      onChange();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't check the skills");
    } finally {
      setBusy(false);
    }
  }

  async function copyInvite(r: SkillGapResult) {
    const skills = r.uncovered_skills;
    const list = skills.length > 1 ? `${skills.slice(0, -1).join(", ")} and ${skills[skills.length - 1]}` : skills[0];
    const role = r.proposed_role.charAt(0).toLowerCase() + r.proposed_role.slice(1);
    const msg =
      `Hi! ${guildName ?? "Our guild"} is a small group of freelancers who share work and split pay fairly through PayPal. ` +
      `We have a client job that needs ${list}, and we're looking for ${role}. ` +
      (inviteCode ? `Join with invite code ${inviteCode} at ${window.location.origin}/login/` : "");
    try {
      await navigator.clipboard.writeText(msg.trim());
      setCopied(true);
    } catch {
      setErr("Couldn't copy. Select the text and copy it yourself.");
    }
  }

  const b = result ? BADGE[result.coverage] : null;

  return (
    <Panel title="Can the guild do this?">
      {!result && !busy && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-prose text-sm text-muted">
            The AI lists the skills {clientName} needs. Then the app checks who in the guild has them, and who to invite if nobody does.
          </p>
          <Button className="shrink-0" onClick={run}>Check the skills</Button>
        </div>
      )}

      {busy && <AiThinking label="Reading the job and checking every member's skills…" />}

      {!busy && result && b && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className={`rounded-full px-3 py-1 text-sm font-medium ${b.cls}`}>{b.label}</span>
            <Button variant="quiet" onClick={run}>Check again</Button>
          </div>
          <p className="mt-3 text-sm">{b.line}</p>

          <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Skills this job needs">
            {result.required_skills.map((s) => {
              const missing = result.uncovered_skills.includes(s);
              return (
                <li
                  key={s}
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${missing ? "bg-alert-soft text-alert" : "bg-guild-soft text-guild"}`}
                >
                  {missing ? "Missing: " : ""}{s}
                </li>
              );
            })}
          </ul>

          {result.covered_by.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm text-muted">
              {result.covered_by.map((c) => (
                <li key={c.skill}>
                  <span className="font-medium text-ink">{c.skill}:</span> {c.members.join(", ")}
                  {c.available && c.available.length === 0 && " (nobody free right now)"}
                </li>
              ))}
            </ul>
          )}

          {result.coverage !== "full" && (
            <div className="mt-4 rounded-lg bg-paper p-4 text-sm">
              <p>
                <span className="font-medium">Who to invite:</span> {result.proposed_role}
              </p>
              <Button variant="quiet" className="mt-3" onClick={() => copyInvite(result)}>
                {copied ? "Copied" : "Copy an invite message"}
              </Button>
            </div>
          )}
        </>
      )}
      <ErrorText>{err}</ErrorText>
    </Panel>
  );
}