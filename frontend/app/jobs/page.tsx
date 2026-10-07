"use client";

import useSWR from "swr";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { useMe } from "@/lib/useMe";
import { useMembers } from "@/lib/useGuild";
import { JobsGrid, type Job } from "@/components/JobsGrid";

export default function JobsPage() {
  const { me } = useMe();
  const { data: members } = useMembers(me?.guild_id);
  const { data: jobs } = useSWR<Job[]>("jobs", () => apiGet<Job[]>("/jobs"));
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-3xl font-bold">Jobs</h1>
        <Link href="/jobs/new" className="rounded-md bg-guild px-3.5 py-2 text-sm font-medium text-white hover:bg-guild/90">Post a job</Link>
      </div>
      <JobsGrid jobs={jobs ?? []} members={members ?? []} />
    </div>
  );
}