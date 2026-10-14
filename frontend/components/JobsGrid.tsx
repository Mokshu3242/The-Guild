"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule, ModuleRegistry, themeQuartz,
  type ColDef, type ICellRendererParams,
} from "ag-grid-community";
import { StatusPill, focusRing } from "./ui";
import type { Me } from "@/lib/useMe";

ModuleRegistry.registerModules([AllCommunityModule]);

const theme = themeQuartz.withParams({
  fontFamily: "inherit",
  foregroundColor: "#15201b",
  accentColor: "#1e6b52",
  borderColor: "#dde3de",
  headerBackgroundColor: "#ffffff",
  headerTextColor: "#5a6762",
  headerFontWeight: 500,
  rowHoverColor: "#f3f5f2",
  wrapperBorderRadius: 10,
  rowVerticalPaddingScale: 1.2,
});

export interface Job {
  id: string;
  client_name: string;
  client_email: string;
  description: string;
  status: string;
  referrer_id: string;
  worker_id: string | null;
  match_reason: string;
  created_at: string;
  client_risk: string;
  client_risk_reason: string;
}

const RISK: Record<string, string> = {
  low: "text-guild",
  medium: "text-seal",
  high: "text-alert",
  unknown: "text-muted",
};

const EMPTY = "No jobs yet. Post one when a client asks for something you can't take.";

export function JobsGrid({ jobs, members }: { jobs: Job[]; members: Me[] }) {
  const router = useRouter();
  const nameOf = (id: string | null) => members.find((m) => m.id === id)?.name ?? "Not assigned";
  const sorted = useMemo(
    () => [...jobs].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [jobs],
  );

  const columnDefs = useMemo<ColDef<Job>[]>(() => [
    { field: "client_name", headerName: "Client", minWidth: 140 },
    { field: "description", headerName: "What they need", flex: 2, minWidth: 240, tooltipField: "description" },
    { headerName: "Posted by", valueGetter: (p) => nameOf(p.data?.referrer_id ?? null), minWidth: 110 },
    { headerName: "Worker", valueGetter: (p) => nameOf(p.data?.worker_id ?? null), minWidth: 120 },
    {
      field: "client_risk", headerName: "Client risk", minWidth: 110,
      cellRenderer: (p: ICellRendererParams<Job, string>) =>
        p.value ? <span className={`text-sm font-medium capitalize ${RISK[p.value] ?? "text-muted"}`}>{p.value}</span> : null,
    },
    {
      field: "status", headerName: "Status", minWidth: 130,
      cellRenderer: (p: ICellRendererParams<Job, string>) => <StatusPill status={p.value ?? "open"} />,
    },
    {
      field: "created_at", headerName: "Posted", minWidth: 110, sort: "desc",
      valueFormatter: (p) => (p.value ? new Date(p.value).toLocaleDateString() : ""),
    },
  ], [members]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      {/* Phones and small tablets: a simple list you can tap. */}
      <div className="md:hidden">
        {sorted.length === 0 ? (
          <p className="text-sm text-muted">{EMPTY}</p>
        ) : (
          <ul className="-mx-1 divide-y divide-line">
            {sorted.slice(0, 20).map((j) => (
              <li key={j.id}>
                <Link
                  href={`/jobs/view/?id=${j.id}`}
                  className={`block rounded-lg px-1 py-3.5 hover:bg-paper ${focusRing}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="min-w-0 truncate font-medium">{j.client_name}</p>
                    <StatusPill status={j.status} />
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-muted">{j.description}</p>
                  <p className="mt-1.5 text-xs text-muted">
                    Worker: {nameOf(j.worker_id)}
                    {j.client_risk && (
                      <span className={`ml-2 capitalize ${RISK[j.client_risk] ?? ""}`}>{j.client_risk} risk</span>
                    )}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Larger screens: the sortable table. */}
      <div className="hidden w-full md:block">
        <AgGridReact<Job>
          theme={theme}
          rowData={jobs}
          columnDefs={columnDefs}
          defaultColDef={{ flex: 1, sortable: true, filter: true, resizable: true }}
          domLayout="autoHeight"
          pagination
          paginationPageSize={10}
          paginationPageSizeSelector={false}
          rowStyle={{ cursor: "pointer" }}
          onRowClicked={(e) => e.data && router.push(`/jobs/view/?id=${e.data.id}`)}
          overlayNoRowsTemplate={EMPTY}
        />
      </div>
    </>
  );
}
