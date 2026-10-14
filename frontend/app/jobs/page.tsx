"use client";

import useSWR from "swr";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { useMe } from "@/lib/useMe";
import { useMembers } from "@/lib/useGuild";
import { JobsGrid, type Job } from "@/components/JobsGrid";
import { PageHeader, Panel, buttonCls } from "@/components/ui";

export default function JobsPage() {
  const { me } = useMe();
  const { data: members } = useMembers(me?.guild_id);
  const { data: jobs } = useSWR<Job[]>("jobs", () => apiGet<Job[]>("/jobs"));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Jobs"
        description="Work the guild is doing for clients. Tap a job to see its milestones and payments."
        actions={<Link href="/jobs/new/" className={buttonCls()}>Post a job</Link>}
      />
      <Panel>
        <JobsGrid jobs={jobs ?? []} members={members ?? []} />
      </Panel>
    </div>
  );
}
